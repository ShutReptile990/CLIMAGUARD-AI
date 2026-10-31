"""Validated local WorldPop cache fallback until Supabase is configured."""

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from app.services.zones import grid_zones

REPORT = Path(__file__).resolve().parents[3] / "data/processed/pune_worldpop_validation.json"


@lru_cache(maxsize=2)
def _read(path: str, mtime_ns: int, size: int) -> dict[str, dict]:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if report.get("source") != "WorldPop Global2 API v2" or report.get("spatial_resolution") not in ("100m", "1km"):
        return {}
    year = report.get("dataset_year")
    if not isinstance(year, int) or not 2015 <= year <= 2030:
        return {}
    known = {zone.slug: (str(zone.id), sha256(json.dumps({"geometry": zone.geometry, "year": year,
               "resolution": report["spatial_resolution"]}, sort_keys=True).encode()).hexdigest()) for zone in grid_zones()}
    result = {}
    for item in report.get("records", []):
        slug = item.get("zone_slug")
        estimate = item.get("population_estimate")
        if slug not in known or item.get("zone_id") != known[slug][0] or slug in result:
            return {}
        if item.get("source") != report["source"] or item.get("dataset_year") != year or item.get("spatial_resolution") != report["spatial_resolution"]:
            return {}
        if not isinstance(estimate, int) or estimate < 0 or item.get("geometry_sha256") != known[slug][1]:
            return {}
        result[slug] = {"slug": slug, "dataset_version": f"worldpop-global2-{year}-{report['spatial_resolution']}",
                        "population_estimate": estimate, "provenance": {"population": {"source": report["source"],
                        "dataset_year": year, "spatial_resolution": report["spatial_resolution"],
                        "retrieved_at_utc": item.get("retrieved_at_utc"), "source_url": item.get("source_url"),
                        "task_id": item.get("task_id"), "geometry_sha256": item.get("geometry_sha256"),
                        "storage": "local_api_cache_preview"}}}
    return result


def local_population_context() -> dict[str, dict]:
    if not REPORT.is_file():
        return {}
    stat = REPORT.stat()
    try:
        return _read(str(REPORT), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, TypeError, KeyError):
        return {}
