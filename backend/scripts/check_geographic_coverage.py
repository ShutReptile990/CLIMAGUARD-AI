"""Read-only Supabase coverage audit for the nine Pune analysis cells."""

import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway


async def main() -> None:
    gateway = SupabaseGateway(get_settings())
    try:
        context = await gateway.request("POST", "/rest/v1/rpc/analysis_zone_context_all", json={})
        flood = await gateway.request("POST", "/rest/v1/rpc/analysis_zone_flood_features_all", json={})
        waterways = await gateway.table("waterways", params={"select": "id", "limit": 1000})
        runs = await gateway.table("osm_import_runs", params={"select": "id", "limit": 100})
        context = context if isinstance(context, list) else []
        flood = flood if isinstance(flood, list) else []
        output = {
            "analysis_cells": len(context),
            "population_with_source": sum(row.get("population_estimate") is not None and bool((row.get("provenance") or {}).get("population", {}).get("source")) for row in context),
            "slope_with_source": sum(row.get("slope_mean_degrees") is not None and bool((row.get("provenance") or {}).get("dem", {}).get("source")) for row in context),
            "drain_distance_cells": sum(row.get("mapped_drain_distance_m") is not None for row in flood),
            "historical_exposure_cells": sum(row.get("historical_flood_exposure") is not None for row in context),
            "mapped_waterways_rows": len(waterways) if isinstance(waterways, list) else None,
            "osm_import_runs": len(runs) if isinstance(runs, list) else None,
            "database_infrastructure_cells": sum(row.get("mapped_hospitals") is not None for row in context),
        }
        print(json.dumps(output, indent=2))
        if len(context) != 9 or len(flood) != 9:
            raise SystemExit(1)
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
