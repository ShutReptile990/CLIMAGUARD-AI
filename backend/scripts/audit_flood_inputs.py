"""Read-only Supabase and FastAPI audit of Pune flood-screening inputs."""

import asyncio
import json
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.services.zones import grid_zones


async def main() -> None:
    async with app.router.lifespan_context(app):
        gateway = app.state.supabase
        rows = await gateway.table("zone_dataset_metrics", privileged=True, params={
            "select": "zone_id,dem_mean_m,slope_mean_degrees,drainage_index,mapped_drain_distance_m,historical_flood_exposure,provenance"})
        waterways = await gateway.table("waterways", privileged=True, params={"select": "id", "limit": 1000})
        labels = await gateway.request("GET", "/rest/v1/verified_flood_labels", privileged=True, params={"select": "id", "limit": 1000})
        context = await app.state.analysis.context_all()
        cells = [zone.slug for zone in grid_zones()]
        output = {
            "database": {
                "zone_metric_rows": len(rows),
                "distinct_metric_zones": len({row["zone_id"] for row in rows}),
                "dem_elevation_rows": sum(row.get("dem_mean_m") is not None for row in rows),
                "slope_rows": sum(row.get("slope_mean_degrees") is not None for row in rows),
                "mapped_drain_distance_rows": sum(row.get("mapped_drain_distance_m") is not None for row in rows),
                "drainage_capacity_index_rows": sum(row.get("drainage_index") is not None for row in rows),
                "historical_exposure_rows": sum(row.get("historical_flood_exposure") is not None for row in rows),
                "waterway_rows": len(waterways),
                "verified_flood_label_rows": len(labels),
            },
            "context": {slug: {
                "slope": context.get(slug, {}).get("slope_mean_degrees"),
                "slope_source": (context.get(slug, {}).get("provenance") or {}).get("dem", {}).get("source"),
                "mapped_drain_distance_m": context.get(slug, {}).get("mapped_drain_distance_m"),
                "drainage_index": context.get(slug, {}).get("drainage_index"),
            } for slug in cells},
        }
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=90) as client:
            output["api"] = {}
            for slug in ("pune", "pune-grid-r2-c2"):
                response = await client.get(f"/api/v1/analysis/{slug}")
                data = response.json()
                flood = next((item for item in data.get("assessments", []) if item["hazard"] == "flood"), {})
                snapshot_response = await client.get(f"/api/v1/localities/{slug}/snapshot")
                snapshot_flood = next((item for item in snapshot_response.json().get("risks", []) if item["hazard"] == "flood"), {})
                output["api"][slug] = {
                    "http_status": response.status_code,
                    "snapshot_http_status": snapshot_response.status_code,
                    "snapshot_matches_analysis_score": snapshot_flood.get("score") == flood.get("score"),
                    "snapshot_has_dem_source": "Sourced DEM" in snapshot_flood.get("source", ""),
                    "metrics_slope": (data.get("metrics") or {}).get("slope_mean_degrees"),
                    "metrics_drain_distance": (data.get("metrics") or {}).get("mapped_drain_distance_m"),
                    "flood_factors": [item["name"] for item in flood.get("factors", [])],
                    "missing_flood_inputs": [item for item in flood.get("warnings", []) if "unavailable" in item],
                    "feature_status": {item["name"]: item["status"] for item in data.get("feature_availability", [])},
                }
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
