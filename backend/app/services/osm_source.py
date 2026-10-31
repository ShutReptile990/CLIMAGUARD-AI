"""Read-only preview of the validated local OSM file when PostGIS is unavailable."""

from functools import lru_cache
from pathlib import Path
from shapely.geometry import Point, box, shape
from scripts.import_pune_infrastructure import DEFAULT_INPUT, ImportBatch, parse_geojson

Bounds = tuple[float, float, float, float]  # west, south, east, north


@lru_cache(maxsize=2)
def _snapshot(path: str, mtime_ns: int, size: int) -> tuple[ImportBatch, list[tuple[dict, object]], list[tuple[dict, object]]]:
    batch = parse_geojson(Path(path))
    return batch, [(item, shape(item["geometry"])) for item in batch.facilities], [(item, shape(item["geometry"])) for item in batch.roads]


def preview(bounds: Bounds, kind: str) -> dict:
    path = DEFAULT_INPUT
    if not path.is_file():
        return {"status": "unavailable", "storage": "none", "features": [], "detail": "PostGIS is unavailable and no local OSM GeoJSON is present."}
    stat = path.stat()
    batch, facilities, roads = _snapshot(str(path), stat.st_mtime_ns, stat.st_size)
    viewport = box(*bounds)
    if kind == "facilities":
        matches = [item for item, _geometry in facilities if viewport.covers(Point(item["marker"]))]
        limit = 1000
        selected = matches[:limit]
        features = [{"id": f"{item['osm_type']}:{item['osm_id']}", "name": item["name"], "kind": item["kind"], "lat": item["marker"][1], "lng": item["marker"][0], "source": "OpenStreetMap", "source_url": item["source_url"], "verified_at": None, "osm_type": item["osm_type"], "osm_id": item["osm_id"]} for item in selected]
        counts = {key: sum(item["kind"] == key for item in selected) for key in ("hospital", "school", "fire_station")}
    elif kind == "roads":
        matches = [item for item, geometry in roads if geometry.intersects(viewport)]
        limit = 2500
        selected = matches[:limit]
        features = [{"id": f"{item['osm_type']}:{item['osm_id']}", "name": item["name"], "highway_class": item["highway_class"], "geometry": item["geometry"], "osm_type": item["osm_type"], "osm_id": item["osm_id"], "source_url": item["source_url"]} for item in selected]
        counts = {}
    else:
        raise ValueError("Unknown OSM preview kind")
    return {"status": "available", "storage": "local_geojson_preview", "features": features, "counts": counts, "total_count": len(matches), "returned_count": len(features), "truncated": len(matches) > limit, "source": "OpenStreetMap GeoJSON (ODbL), local source preview; not imported into PostGIS", "osm_timestamp": batch.metadata.get("osm_timestamp"), "attribution": batch.metadata.get("copyright"), "validation_failed_records": len(batch.failures), "detail": "PostGIS records unavailable; showing validated local GeoJSON features."}
