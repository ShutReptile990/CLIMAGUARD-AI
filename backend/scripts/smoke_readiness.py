"""Read-only public API smoke check with compact, source-aware output.

Run from backend: .venv/Scripts/python.exe scripts/smoke_readiness.py
The environment route may perform its normal selected-observation persistence.
"""

import asyncio
import json
import logging
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
logging.getLogger("httpx").setLevel(logging.WARNING)


async def main() -> None:
    zone = "pune-grid-r2-c2"
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local", timeout=120) as client:
            output: dict = {}
            for name, path in (
                ("health", "/api/v1/health"),
                ("zones", "/api/v1/zones/geojson"),
                ("environment", f"/api/v1/environment/{zone}"),
                ("analysis", f"/api/v1/analysis/{zone}"),
                ("exposure", f"/api/v1/analysis/{zone}/exposure"),
                ("infrastructure", "/api/v1/map/infrastructure"),
                ("roads", "/api/v1/map/roads"),
                ("nugen_status", "/api/v1/nugen/status"),
            ):
                response = await client.get(path)
                body = response.json()
                result: dict = {"http": response.status_code}
                if name == "zones":
                    result.update(count=len(body.get("features", [])), official_boundary=body.get("metadata", {}).get("official_boundary"))
                elif name == "environment":
                    for stream in ("weather", "air_quality", "history"):
                        value = body.get(stream, {})
                        result[stream] = "unavailable" if value.get("status") == "unavailable" else value.get("source")
                        if stream == "weather" and "current" in value:
                            result["weather_valid_at"] = value["current"].get("valid_at")
                            result["weather_units"] = value["current"].get("units")
                            result["hourly_forecast_count"] = len(value.get("hourly", []))
                        if stream == "air_quality" and "valid_at" in value:
                            result["air_valid_at"] = value.get("valid_at")
                            result["air_units"] = value.get("units")
                    result["persistence"] = body.get("persistence")
                elif name == "analysis":
                    result["hazards"] = {item["hazard"]: {"status": item["status"], "method": item["method"]} for item in body.get("assessments", [])}
                    result["features"] = {item["name"]: item["status"] for item in body.get("feature_availability", [])}
                    result["metrics_status"] = body.get("metrics_status")
                elif name == "exposure":
                    result.update(status=body.get("status"), potential_population_exposure=body.get("potential_population_exposure"))
                elif name in ("infrastructure", "roads"):
                    result.update(status=body.get("status"), storage=body.get("storage"), count=body.get("returned_count"))
                elif name == "nugen_status":
                    result.update(configured=body.get("configured"), model_id_present=bool(body.get("model_id")))
                else:
                    result.update(status=body.get("status"), database_configured=body.get("database_configured"))
                output[name] = result
            print(json.dumps(output, ensure_ascii=True, indent=2))
            if output["health"]["http"] != 200 or output["zones"]["count"] != 9:
                raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
