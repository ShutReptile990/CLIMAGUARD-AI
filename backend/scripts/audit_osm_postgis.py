"""Read-only Supabase/PostGIS OSM import audit; prints counts and safe metadata only."""

import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway

BOUNDS = {"p_west": 73.77, "p_south": 18.45, "p_east": 73.96, "p_north": 18.60}


async def count(gateway: SupabaseGateway, table: str, filters: dict, privileged: bool) -> dict:
    settings = gateway.settings
    key = settings.supabase_secret_key if privileged else settings.supabase_publishable_key
    if not key:
        return {"status": "not_configured", "count": None}
    headers = {"apikey": key, "Prefer": "count=exact", "Range": "0-0"}
    if privileged and key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    response = await gateway.client.head(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}",
        params={"select": "id", **filters}, headers=headers,
    )
    content_range = response.headers.get("content-range", "")
    value = content_range.rsplit("/", 1)[-1]
    return {"status": response.status_code, "count": int(value) if value.isdigit() else None}


async def main() -> None:
    settings = get_settings()
    output = {"supabase_configured": settings.configured, "privileged_configured": bool(settings.supabase_secret_key),
              "database_url_configured": bool(os.getenv("DATABASE_URL"))}
    if not settings.configured:
        print(json.dumps(output, indent=2))
        return
    gateway = SupabaseGateway(settings)
    try:
        output["tables"] = {}
        for table, filters in [
            ("infrastructure", {"source": "eq.OpenStreetMap", "kind": "eq.hospital"}),
            ("infrastructure", {"source": "eq.OpenStreetMap", "kind": "eq.school"}),
            ("infrastructure", {"source": "eq.OpenStreetMap", "kind": "eq.fire_station"}),
            ("osm_roads", {"source": "eq.OpenStreetMap"}),
            ("osm_import_runs", {}),
        ]:
            label = filters.get("kind", "roads" if table == "osm_roads" else "import_runs").removeprefix("eq.")
            output["tables"][label] = {
                "public": await count(gateway, table, filters, False),
                "privileged": await count(gateway, table, filters, True),
            }
        output["geometry_coverage"] = {}
        for label, table, filters in [
            ("facility_points", "infrastructure", {"source": "eq.OpenStreetMap", "location": "not.is.null"}),
            ("facility_osm_geometries", "infrastructure", {"source": "eq.OpenStreetMap", "osm_geometry": "not.is.null"}),
            ("road_lines", "osm_roads", {"source": "eq.OpenStreetMap", "geometry": "not.is.null"}),
        ]:
            output["geometry_coverage"][label] = await count(gateway, table, filters, True)
        output["rpc"] = {}
        for name in ("map_infrastructure_bbox", "map_roads_bbox"):
            try:
                rows = await gateway.request("POST", f"/rest/v1/rpc/{name}", json=BOUNDS)
                rows = rows if isinstance(rows, list) else []
                output["rpc"][name] = {"status": 200, "returned": len(rows),
                                       "sample_osm_id_present": bool(rows and rows[0].get("osm_id")),
                                       "sample_geometry_present": bool(rows and rows[0].get("geometry")) if "roads" in name else None,
                                       "sample_lat_lng_valid": bool(rows and 18.2 <= rows[0].get("lat", 0) <= 18.9 and
                                                                    73.5 <= rows[0].get("lng", 0) <= 74.2) if "infrastructure" in name else None}
            except Exception as exc:
                output["rpc"][name] = {"status": "error", "type": type(exc).__name__}
        print(json.dumps(output, indent=2))
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
