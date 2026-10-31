"""Read validated OSM waterway indicators as labeled local context."""

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from app.services.zones import grid_zones

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "data/processed/pune_waterways_validation.json"
SOURCE = ROOT / "data/raw/pune_waterways.geojson"


@lru_cache(maxsize=2)
def _read(report_path: str, mtime_ns: int, source_sha256: str) -> dict[str, dict]:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if report.get("source", {}).get("source_sha256") != source_sha256 or report.get("failed_records"):
        return {}
    known = {zone.slug: str(zone.id) for zone in grid_zones()}
    rows = {}
    for item in report.get("zones", []):
        slug = item.get("zone_slug")
        if slug not in known or item.get("zone_id") != known[slug] or slug in rows:
            return {}
        rows[slug] = {key: item.get(key) for key in ("mapped_waterway_distance_m", "mapped_drain_distance_m", "mapped_culvert_count")}
        rows[slug]["provenance"] = {"mapped_waterways": {"source": "OpenStreetMap", "storage": "local_geojson_preview",
                               "source_sha256": source_sha256, "source_timestamp": report["source"].get("source_timestamp"),
                               "limitation": "Proximity and mapped culvert count do not measure capacity or effectiveness."}}
    return rows


def local_waterway_context() -> dict[str, dict]:
    if not REPORT.is_file() or not SOURCE.is_file():
        return {}
    try:
        digest = sha256(SOURCE.read_bytes()).hexdigest()
        return _read(str(REPORT), REPORT.stat().st_mtime_ns, digest)
    except (OSError, ValueError, TypeError, KeyError):
        return {}
