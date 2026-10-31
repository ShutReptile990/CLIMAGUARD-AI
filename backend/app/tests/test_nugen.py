"""DEMO fixtures exercise guidance contracts; live observations are never mocked in production."""

import json
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ServiceUnavailable
from app.integrations.nugen import NugenClient
from app.integrations.supabase import SupabaseGateway
from app.schemas.nugen import NugenGuidanceText, NugenInference
from datetime import datetime, timezone
from app.services.analysis import assess_bundle
from app.services.nugen_guidance import NugenGuidanceService, analysis_context, prompt_for
from app.tests.test_analysis import demo_bundle, demo_weather, demo_air


def settings() -> Settings:
    return Settings(_env_file=None, nugen_api_key="DEMO-test-key", nugen_model_id="DEMO-model")


def provider_response(summary: str = "Local conditions warrant attention and practical preparedness.") -> dict:
    return {"id": "DEMO-request", "model": "DEMO-model", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
        "summary": summary,
        "actions": ["Follow verified local guidance and check for updates.",
                    "Prepare a safe route and keep essential supplies ready."],
        "limitations": "This is AI guidance, not an official alert or dispatch order."})}}]}


def test_nugen_client_uses_verified_request_shape_and_retries_rate_limit():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer DEMO-test-key"
        return (httpx.Response(429, json={"error": "rate limited"}) if len(calls) == 1
                else httpx.Response(200, json=provider_response()))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            client = NugenClient(settings(), transport)
            result = await client.generate("DEMO prompt", allowed_numbers=set())
            assert result.guidance.actions and result.provider_request_id == "DEMO-request" and client.status().available
            assert len(calls) == 2
            assert calls[0] == {"model": "DEMO-model", "messages": [{"role": "user", "content": "DEMO prompt"}],
                                "temperature": 0.2, "max_tokens": 400, "prompt_truncate_len": 3000, "stream": False}
    asyncio.run(run())


def test_nugen_client_rejects_unsupported_measurements():
    async def run():
        unsafe = provider_response()
        unsafe["choices"][0]["message"]["content"] = unsafe["choices"][0]["message"]["content"].replace(
            "Follow verified local guidance", "Expect 999 millimeters of rain and follow verified local guidance")
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=unsafe))) as transport:
            with pytest.raises(ServiceUnavailable):
                await NugenClient(settings(), transport).generate("DEMO prompt", allowed_numbers={"25"})
    asyncio.run(run())


def test_optional_explanation_with_numeric_claim_is_replaced_safely():
    async def run():
        payload = provider_response()
        content = json.loads(payload["choices"][0]["message"]["content"])
        content["risk_explanation"] = "The model predicts 83 percent flood probability tomorrow."
        payload["choices"][0]["message"]["content"] = json.dumps(content)
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=payload))) as transport:
            result = await NugenClient(settings(), transport).generate("DEMO prompt", allowed_numbers=set())
            assert result.guidance.risk_explanation is None
    asyncio.run(run())


def test_guidance_validation_allows_locality_code_but_not_invented_percent_in_actions():
    guidance = provider_response("Pune grid B2 has a moderate screening level.")["choices"][0]["message"]["content"]
    assert NugenGuidanceText.model_validate_json(guidance, context={"allowed_numbers": set()}).summary.startswith("Pune")
    with pytest.raises(ValidationError):
        NugenGuidanceText.model_validate_json(guidance.replace("Follow verified local guidance", "Expect 75% rain and follow verified local guidance"), context={"allowed_numbers": set()})


def test_prompts_keep_heuristic_and_us_aqi_distinct_across_scenarios():
    for rain, temp, aqi in [(0.2, 35, 50), (12, 35, 151), (3, 43, 301)]:
        bundle = demo_bundle(weather=demo_weather(rain), air=demo_air(aqi))
        bundle.weather.current.temperature_c = temp
        context = analysis_context(assess_bundle(bundle))
        prompt = prompt_for("authority", "Pune grid B2", context)
        assert all(hazard in prompt for hazard in ('"hazard":"flood"', '"hazard":"heat"', '"hazard":"air_quality"'))
        assert "heuristic flood index" in prompt and "US AQI Indian AQI" in prompt
        assert context["hazards"][2]["score"] == aqi


def test_missing_analysis_does_not_call_nugen_or_persist():
    class UnavailableAnalysis:
        async def zone(self, _):
            bundle = demo_bundle()
            bundle.weather = None
            bundle.air_quality = None
            return assess_bundle(bundle)

    class NoCalls:
        def __getattr__(self, _):
            raise AssertionError("Nugen or database was called without live analysis")

    service = NugenGuidanceService(NoCalls(), UnavailableAnalysis(), NoCalls())
    async def run():
        with pytest.raises(ServiceUnavailable):
            await service.generate("pune-grid-r2-c2", "citizen")
    asyncio.run(run())


def test_guidance_persists_draft_with_model_and_source_analysis():
    class Analysis:
        async def zone(self, _):
            return assess_bundle(demo_bundle())

    class Nugen:
        settings = SimpleNamespace(nugen_model_id="DEMO-model")

        async def generate(self, prompt, *, allowed_numbers):
            assert "heuristic flood index" in prompt and allowed_numbers == set()
            text = json.loads(provider_response()["choices"][0]["message"]["content"])
            text["risk_explanation"] = "The heat risk is severe despite the supplied analysis."
            return NugenInference(guidance=NugenGuidanceText.model_validate(text), model_id="DEMO-model", provider_request_id="DEMO-request", inferred_at=datetime.now(timezone.utc))

    class Database:
        settings = SimpleNamespace(configured=True, supabase_secret_key="DEMO-secret")
        draft = None

        async def table(self, table, method="GET", **kwargs):
            if table == "zones":
                return [{"id": "00000000-0000-0000-0000-000000000001"}]
            assert table == "ai_recommendations" and method == "POST" and kwargs["privileged"]
            self.draft = kwargs["json"]

    async def run():
        database = Database()
        result = await NugenGuidanceService(Nugen(), Analysis(), database).generate("pune-grid-r2-c2", "authority")
        assert result.persistence == "stored" and result.model_id == "DEMO-model"
        assert f"{result.source_analysis['hazards'][0]['level']} flood risk" in result.guidance.summary
        assert "severe despite" not in result.guidance.risk_explanation
        assert database.draft["model_id"] == "DEMO-model"
        assert database.draft["source_analysis"]["inference"]["provider_request_id"] == "DEMO-request"
        assert database.draft["source_analysis"]["hazards"][0]["method"] == "heuristic_index"
        assert "approved_at" not in database.draft and "approved_by" not in database.draft
    asyncio.run(run())


def test_authority_route_rejects_unauthenticated_request():
    from app.main import app

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/nugen/authority/pune-grid-r2-c2")
            assert response.status_code == 401
    asyncio.run(run())


def test_ai_alert_draft_requires_distinct_authority_reviewer():
    from fastapi import HTTPException
    from app.api.alerts import review_alert
    from app.schemas.alerts import AlertReview
    from app.core.auth import Principal

    author = uuid4()
    class Database:
        async def table(self, table, method="GET", **kwargs):
            assert table == "alerts" and method == "GET"
            return [{"id": str(uuid4()), "status": "pending_approval", "created_by": str(author)}]

    async def run():
        with pytest.raises(HTTPException) as error:
            await review_alert(uuid4(), AlertReview(approve=True), Principal(id=author, role="authority", token="DEMO-token"), Database())
        assert error.value.status_code == 403
    asyncio.run(run())


def test_legacy_supabase_service_role_uses_bearer_header():
    async def run():
        headers = []

        def handler(request: httpx.Request) -> httpx.Response:
            headers.append(request.headers)
            return httpx.Response(201, json=[])

        gateway = SupabaseGateway(Settings(_env_file=None, supabase_url="https://example.supabase.co",
                                           supabase_publishable_key="DEMO-public", supabase_secret_key="eyJDEMO-service"))
        await gateway.client.aclose()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            gateway.client = transport
            await gateway.request("POST", "/rest/v1/ai_recommendations", privileged=True, json={})
        assert headers[0]["Authorization"] == "Bearer eyJDEMO-service"
        assert headers[0]["apikey"] == "eyJDEMO-service"
    asyncio.run(run())
