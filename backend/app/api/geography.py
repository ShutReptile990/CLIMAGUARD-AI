import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.integrations.supabase import SupabaseGateway, get_gateway
from app.core.errors import ServiceUnavailable, UpstreamError
from app.services.zones import GRID_VERSION, grid_zones
from app.services.screening import grid_screening
from app.services.osm_source import preview

router = APIRouter(tags=["geography"])


@router.get("/zones/geojson")
async def zone_geojson():
    return {"type": "FeatureCollection", "features": [zone.feature() for zone in grid_zones()], "metadata": {"grid_version": GRID_VERSION, "official_boundary": False, "description": "Reproducible WGS84 Pune pilot analysis grid; not municipal wards."}}


@router.get("/map/screening")
async def screening(request: Request):
    return await grid_screening(request.app.state.open_meteo)


DEFAULT_BOUNDS = (73.77, 18.45, 73.96, 18.60)


def _bounds(raw: str | None) -> tuple[float, float, float, float]:
    if raw is None:
        return DEFAULT_BOUNDS
    try:
        west, south, east, north = (float(value) for value in raw.split(","))
    except (TypeError, ValueError):
        raise HTTPException(422, "bbox must be west,south,east,north in EPSG:4326")
    if not (73.5 <= west < east <= 74.2 and 18.2 <= south < north <= 18.9):
        raise HTTPException(422, "bbox must lie within the Pune source envelope")
    return west, south, east, north


async def _mapped_features(gateway: SupabaseGateway, function: str, kind: str, bounds: tuple[float, float, float, float]) -> dict:
    try:
        west, south, east, north = bounds
        rows = await gateway.request("POST", f"/rest/v1/rpc/{function}", json={"p_west": west, "p_south": south, "p_east": east, "p_north": north})
        if isinstance(rows, list) and rows:
            total_count = int(rows[0].get("total_count") or len(rows))
            features = []
            for row in rows:
                item = {key: value for key, value in row.items() if key != "total_count"}
                if item.get("osm_type") in ("node", "way", "relation") and isinstance(item.get("osm_id"), int):
                    item["source_url"] = f"https://www.openstreetmap.org/{item['osm_type']}/{item['osm_id']}"
                features.append(item)
            counts = {key: sum(item.get("kind") == key for item in features) for key in ("hospital", "school", "fire_station")} if kind == "facilities" else {}
            return {"status": "available", "storage": "postgis", "features": features, "counts": counts, "total_count": total_count, "returned_count": len(features), "truncated": len(features) < total_count, "source": "PostGIS mapped features; per-record source retained", "detail": None}
    except (ServiceUnavailable, UpstreamError, HTTPException, ValueError, TypeError) as exc:
        logging.getLogger("climaguard.geography").warning("mapped_features_unavailable function=%s type=%s", function, type(exc).__name__)
    try:
        return await asyncio.to_thread(preview, bounds, kind)
    except (OSError, ValueError, TypeError) as exc:
        logging.getLogger("climaguard.geography").warning("local_osm_unavailable type=%s", type(exc).__name__)
        return {"status": "unavailable", "storage": "none", "features": [], "detail": "PostGIS and validated local OSM data are unavailable."}


@router.get("/map/infrastructure")
async def infrastructure(bbox: str | None = Query(default=None, max_length=80), gateway: SupabaseGateway = Depends(get_gateway)):
    return await _mapped_features(gateway, "map_infrastructure_bbox", "facilities", _bounds(bbox))


@router.get("/map/roads")
async def roads(bbox: str | None = Query(default=None, max_length=80), gateway: SupabaseGateway = Depends(get_gateway)):
    return await _mapped_features(gateway, "map_roads_bbox", "roads", _bounds(bbox))
