from uuid import uuid4
import asyncio
import httpx
from datetime import datetime, timezone
from app.main import app
from app.integrations.supabase import get_gateway, SupabaseGateway
from app.core.config import Settings
from app.core.errors import ServiceUnavailable
from app.services.environment import get_environment_service
from app.schemas.environment import EnvironmentBundle, StreamError
from app.tests.test_analysis import demo_weather
from app.services.analysis import AnalysisService
from app.services.risk_engine import flood_assessment
from app.schemas.analysis import ZoneMetrics


class FakeGateway:
    async def user(self, token):
        if token != "valid-token":
            raise ServiceUnavailable("Auth unavailable")
        return {"id": str(USER_ID)}

    async def table(self, table, method="GET", **kwargs):
        if table == "profiles":
            return [{"id": str(USER_ID), "role": "citizen"}]
        return []


class FakePersistenceGateway(FakeGateway):
    async def table(self, table, method="GET", **kwargs):
        if table == "profiles":
            return [{"id": str(USER_ID), "role": "citizen"}]
        if table == "zones":
            return [{"id": str(uuid4())}]
        if table == "incident_reports" and method == "POST":
            payload = kwargs["json"]
            return [{"id": str(uuid4()), **payload, "created_at": datetime.now(timezone.utc).isoformat(), "status": "submitted", "review_note": None}]
        return []


USER_ID = uuid4()


def call(method: str, path: str, **kwargs):
    async def run():
        gateway = SupabaseGateway(Settings(supabase_url=None, supabase_publishable_key=None))
        app.state.supabase = gateway
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await asyncio.wait_for(client.request(method, path, **kwargs), timeout=5)
        finally:
            await gateway.close()
    return asyncio.run(run())


def test_health():
    response = call("GET", "/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_profile_requires_authentication():
    response = call("GET", "/api/profile")
    assert response.status_code == 401


def test_citizen_cannot_assign_roles_or_review():
    app.dependency_overrides[get_gateway] = lambda: FakeGateway()
    try:
        headers = {"Authorization": "Bearer valid-token"}
        role_response = call("PATCH", f"/api/profiles/{uuid4()}/role", json={"role": "admin"}, headers=headers)
        review_response = call("PATCH", f"/api/incidents/{uuid4()}/review", json={"status": "resolved"}, headers=headers)
        assert role_response.status_code == 403
        assert review_response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_incident_rejects_invalid_locality_and_short_description():
    app.dependency_overrides[get_gateway] = lambda: FakeGateway()
    try:
        response = call("POST", "/api/incidents", headers={"Authorization": "Bearer valid-token"}, json={"localityId": "pune,or.role.eq.admin", "category": "flood", "description": "short"})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_unconfigured_snapshot_is_explicit():
    class UnavailableEnvironment:
        async def bundle(self, zone_id, include_history=False):
            unavailable = StreamError(detail="Provider unavailable")
            return EnvironmentBundle(zone_id=zone_id, coordinate=(18.52, 73.85), weather=unavailable, air_quality=unavailable, history=unavailable, persistence="not_configured", retrieved_at=datetime.now(timezone.utc))
    app.dependency_overrides[get_environment_service] = lambda: UnavailableEnvironment()
    try:
        response = call("GET", "/api/localities/pune/snapshot")
        assert response.status_code == 503
        assert response.json()["status"] == "unavailable"
    finally:
        app.dependency_overrides.clear()


def test_public_weather_snapshot_survives_missing_aqi_database_and_geography():
    class PartialEnvironment:
        async def bundle(self, zone_id, include_history=False):
            unavailable = StreamError(detail="Air quality provider unavailable")
            return EnvironmentBundle(zone_id=zone_id, coordinate=(18.52, 73.85), weather=demo_weather(),
                                     air_quality=unavailable, history=unavailable,
                                     persistence="not_configured", retrieved_at=datetime.now(timezone.utc))

    app.dependency_overrides[get_environment_service] = lambda: PartialEnvironment()
    try:
        response = call("GET", "/api/v1/localities/pune/snapshot")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "live" and body["weather"]["temperatureC"] == 35
        assert body["weather"]["aqi"] is None
        assert body["risks"][0]["method"] == "heuristic_index"
    finally:
        app.dependency_overrides.clear()


def test_grid_snapshot_uses_same_sourced_slope_as_analysis(monkeypatch):
    class PartialEnvironment:
        async def bundle(self, zone_id, include_history=False):
            unavailable = StreamError(detail="Air quality provider unavailable")
            return EnvironmentBundle(zone_id=zone_id, coordinate=(18.52, 73.85), weather=demo_weather(),
                                     air_quality=unavailable, history=unavailable,
                                     persistence="not_configured", retrieved_at=datetime.now(timezone.utc))

    async def sourced_context(self):
        return {"pune-grid-r2-c2": {"slope_mean_degrees": 3.5,
                "provenance": {"dem": {"source": "DEMO sourced raster", "storage": "postgis_zone_metric"}}}}

    monkeypatch.setattr(AnalysisService, "context_all", sourced_context)
    app.dependency_overrides[get_environment_service] = lambda: PartialEnvironment()
    try:
        response = call("GET", "/api/v1/localities/pune-grid-r2-c2/snapshot")
        assert response.status_code == 200
        actual = next(item for item in response.json()["risks"] if item["hazard"] == "flood")
        expected = flood_assessment(demo_weather(), ZoneMetrics(slope_mean_degrees=3.5)).score
        assert actual["score"] == expected
        assert any("Sourced DEM" in source for source in [actual["source"]])
    finally:
        app.dependency_overrides.clear()


def test_authenticated_incident_is_persisted_through_repository():
    app.dependency_overrides[get_gateway] = lambda: FakePersistenceGateway()
    try:
        response = call("POST", "/api/incidents", headers={"Authorization": "Bearer valid-token"}, json={"localityId": "pune", "category": "flood", "description": "Water is entering the ground floor near the road."})
        assert response.status_code == 201
        assert response.json()["status"] == "submitted"
        assert response.json()["localityId"] == "pune"
    finally:
        app.dependency_overrides.clear()
