"""Read-only, reproducible readback of the extreme-rainfall demo screening."""

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
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/analysis/demo/extreme-rainfall")
        response.raise_for_status()
        from app.schemas.analysis import DemoFloodResponse
        result = DemoFloodResponse.model_validate(response.json())
        output = {
            "inputs": {"rainfall_intensity_mm_h": result.rainfall_intensity_mm_h,
                       "rainfall_duration_hours": result.rainfall_duration_hours},
            "database_configured": app.state.supabase.settings.configured,
            "api_status": response.status_code,
            "cells": {zone.name: {
                "score": result.zones[zone.slug].assessments[0].score,
                "level": result.zones[zone.slug].assessments[0].level,
                "slope_degrees": result.zones[zone.slug].metrics.slope_mean_degrees if result.zones[zone.slug].metrics else None,
                "slope_source": ((result.zones[zone.slug].metrics.provenance or {}).get("dem") or {}).get("source") if result.zones[zone.slug].metrics else None,
            } for zone in grid_zones()},
            "overview_score": result.overview.assessments[0].score,
        }
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
