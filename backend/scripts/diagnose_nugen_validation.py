"""Diagnose live Nugen validation without printing prompts, model text, or secrets."""

import asyncio
import json
from pathlib import Path
import sys

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.main import app
from app.services.nugen_guidance import analysis_context, locality_name, prompt_for


async def main() -> None:
    area = sys.argv[1] if len(sys.argv) > 1 else "pune"
    attempts = min(int(sys.argv[2]), 5) if len(sys.argv) > 2 else 1
    settings = get_settings()
    print("configured:", bool(settings.nugen_api_key and settings.nugen_model_id),
          "model_id:", settings.nugen_model_id,
          "endpoint_host:", settings.nugen_inference_url.split("/")[2])
    async with app.router.lifespan_context(app):
        analysis = await app.state.analysis.zone(area)
        geography = (await app.state.analysis.context_all()).get(area, {})
        context = analysis_context(analysis, geography=geography)
        prompt = prompt_for("citizen", locality_name(area), context)
        print("area:", area, "analysis_mode:", analysis.mode,
              "available_hazards:", [item.hazard for item in analysis.assessments if item.status == "available"],
              "prompt_length:", len(prompt))
        async def response_metadata(response):
            await response.aread()
            try:
                provider = response.json()
                choice = (provider.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content")
                parsed = json.loads(content) if isinstance(content, str) else None
                print("provider_metadata:", {"http_status": response.status_code,
                    "finish_reason": choice.get("finish_reason"),
                    "prompt_tokens": (provider.get("usage") or {}).get("prompt_tokens"),
                    "completion_tokens": (provider.get("usage") or {}).get("completion_tokens"),
                    "content_length": len(content) if isinstance(content, str) else None,
                    "json_fields": sorted(parsed) if isinstance(parsed, dict) else None})
            except (ValueError, TypeError, AttributeError):
                print("provider_metadata: response body is not a JSON object with JSON text content")
        app.state.nugen.client.event_hooks["response"].append(response_metadata)
        failures = 0
        for attempt in range(attempts):
            try:
                inference = await app.state.nugen.generate(prompt, allowed_numbers=set())
            except ServiceUnavailable as exc:
                failures += 1
                cause = exc.__cause__
                print("attempt:", attempt + 1, "result: rejected", "reason:", str(exc), "cause_type:", type(cause).__name__)
                if isinstance(cause, ValidationError):
                    print("validation_errors:", [{"field": list(error["loc"]), "type": error["type"],
                        "reason": str(error.get("ctx", {}).get("error", ""))}
                        for error in cause.errors()])
                elif isinstance(cause, (ValueError, TypeError, KeyError)):
                    print("parse_reason:", str(cause))
                continue
            print("attempt:", attempt + 1, "result: validated", "model_matches:", inference.model_id == settings.nugen_model_id,
                  "action_count:", len(inference.guidance.actions))
        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
