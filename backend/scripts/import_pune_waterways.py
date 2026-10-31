"""Validate and insert only new OSM or sourced municipal Pune drainage lines."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys

from shapely.geometry import shape, mapping, box, MultiLineString
from shapely import transform
from shapely.errors import GEOSException
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.zones import grid_zones
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/raw/pune_waterways.geojson"
OSM_REF = re.compile(r"^(node|way|relation)/[1-9][0-9]*$")
OSM_CLASSES = {"river", "stream", "canal", "drain", "ditch"}
PUNE_BOUNDS = (73.5, 18.2, 74.2, 18.9)
TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform


def parse_file(path: Path, *, municipal_metadata: dict | None = None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Expected a GeoJSON FeatureCollection")
    if payload.get("crs") not in (None, "EPSG:4326", {"type": "name", "properties": {"name": "EPSG:4326"}}):
        raise ValueError("Reproject source geometry to EPSG:4326 first")
    municipal = municipal_metadata is not None
    if municipal and (not isinstance(municipal_metadata, dict) or not all(municipal_metadata.get(key) for key in ("authority", "dataset_id", "licence", "capture_date", "source_url"))):
        raise ValueError("Municipal metadata requires authority, dataset_id, licence, capture_date and source_url")
    if municipal:
        try:
            datetime.fromisoformat(municipal_metadata["capture_date"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Municipal capture_date must be ISO 8601") from exc
        if not municipal_metadata["source_url"].startswith("https://"):
            raise ValueError("Municipal source_url must be HTTPS")
    digest = sha256(path.read_bytes()).hexdigest()
    dataset = f"municipal:{municipal_metadata['dataset_id']}" if municipal else "osm:pune-waterways"
    provenance = {"source_kind": "municipal" if municipal else "OpenStreetMap", "source_dataset": dataset,
                  "source_sha256": digest, "source_timestamp": payload.get("timestamp"),
                  "source_copyright": payload.get("copyright"), "metadata": municipal_metadata or {},
                  "validated_at_utc": datetime.now(timezone.utc).isoformat(), "crs": "EPSG:4326"}
    records, failures, duplicates = [], [], []
    seen = set()
    for index, feature in enumerate(payload["features"]):
        props = feature.get("properties") if isinstance(feature, dict) else None
        ref = props.get("external_id") if municipal and isinstance(props, dict) else props.get("@id") if isinstance(props, dict) else None
        if not municipal and isinstance(feature, dict) and feature.get("id") and feature["id"] != ref:
            failures.append({"feature_index": index, "id": ref, "reason": "conflicting_osm_id"}); continue
        if not isinstance(props, dict) or not isinstance(ref, str) or not ref or (not municipal and not OSM_REF.fullmatch(ref)):
            failures.append({"feature_index": index, "id": ref, "reason": "missing_or_invalid_source_id"}); continue
        if ref in seen:
            duplicates.append(ref); continue
        try:
            geometry = shape(feature.get("geometry"))
            if geometry.geom_type not in ("LineString", "MultiLineString") or geometry.is_empty or not geometry.is_valid or geometry.length == 0:
                raise ValueError("geometry must be a valid, nonempty line")
            west, south, east, north = geometry.bounds
            if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90) or not geometry.intersects(box(*PUNE_BOUNDS)):
                raise ValueError("geometry outside Pune source envelope")
            waterway_class = props.get("waterway_class") if municipal else props.get("waterway")
            if not isinstance(waterway_class, str) or (not municipal and waterway_class not in OSM_CLASSES):
                raise ValueError("unsupported or missing waterway class")
            is_culvert = props.get("is_culvert") is True if municipal else props.get("tunnel") == "culvert" or props.get("culvert") == "yes"
            records.append({"source_kind": provenance["source_kind"], "source_dataset": dataset,
                            "external_id": ref, "name": props.get("name") if isinstance(props.get("name"), str) else None,
                            "waterway_class": waterway_class, "is_culvert": is_culvert,
                            "geometry": mapping(geometry), "source_tags": props,
                            "provenance": {**provenance, "record_url": f"https://www.openstreetmap.org/{ref}" if not municipal else municipal_metadata["source_url"]}})
            seen.add(ref)
        except (ValueError, TypeError, KeyError, AttributeError, GEOSException) as exc:
            failures.append({"feature_index": index, "id": ref, "reason": str(exc)})
    return {"records": records, "failures": failures, "duplicate_ids": duplicates, "provenance": provenance,
            "feature_count": len(payload["features"]), "counts": dict(Counter(item["waterway_class"] for item in records)),
            "culvert_count": sum(item["is_culvert"] for item in records)}


def zone_indicators(records: list[dict]) -> list[dict]:
    lines = [(item, transform(shape(item["geometry"]), TO_METRIC, interleaved=False)) for item in records]
    result = []
    for zone in grid_zones():
        polygon = transform(shape(zone.geometry), TO_METRIC, interleaved=False)
        distances = [polygon.centroid.distance(line) for _, line in lines]
        drains = [polygon.centroid.distance(line) for item, line in lines if item["waterway_class"] in ("drain", "ditch")]
        culverts = sum(item["is_culvert"] and polygon.intersects(line) for item, line in lines)
        result.append({"zone_id": str(zone.id), "zone_slug": zone.slug,
                       "mapped_waterway_distance_m": round(min(distances), 2) if distances else None,
                       "mapped_drain_distance_m": round(min(drains), 2) if drains else None,
                       "mapped_culvert_count": culverts if lines else None})
    return result


def import_database(batch: dict, indicators: list[dict], database_url: str) -> dict:
    import psycopg
    if batch["failures"] or batch["duplicate_ids"] or not batch["records"]:
        raise ValueError("Waterway source has invalid or duplicate records; no database writes were made")
    expected_zones = {zone.slug: str(zone.id) for zone in grid_zones()}
    if len(indicators) != len(expected_zones) or any(
        row.get("zone_slug") not in expected_zones or row.get("zone_id") != expected_zones[row["zone_slug"]]
        or row.get("mapped_drain_distance_m") is None or row["mapped_drain_distance_m"] < 0
        for row in indicators
    ):
        raise ValueError("Zone indicators do not cover the validated Pune grid; no database writes were made")
    inserted = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            if cursor.execute("select to_regclass('public.waterways')").fetchone()[0] is None:
                raise RuntimeError("Apply migration 006 before importing waterways")
            # Detect a partial migration before inserting any source geometry.
            cursor.execute("select mapped_waterway_distance_m,mapped_drain_distance_m,mapped_culvert_count from public.zone_dataset_metrics limit 0")
            for item in batch["records"]:
                cursor.execute("""insert into public.waterways
                  (source_kind,source_dataset,external_id,name,waterway_class,is_culvert,geometry,source_tags,provenance)
                  values (%s,%s,%s,%s,%s,%s,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),%s::jsonb,%s::jsonb)
                  on conflict (source_dataset,external_id) do nothing returning id""",
                  (item["source_kind"], item["source_dataset"], item["external_id"], item["name"],
                   item["waterway_class"], item["is_culvert"], json.dumps(item["geometry"]),
                   json.dumps(item["source_tags"]), json.dumps(item["provenance"])))
                inserted += int(cursor.fetchone() is not None)
            # Municipal-only batches must not replace the OSM-derived cell metrics.
            # A combined, reviewed dataset can later be imported as its own version.
            metric_rows = indicators if batch["provenance"]["source_kind"] == "OpenStreetMap" else []
            for row in metric_rows:
                cursor.execute("""insert into public.zone_dataset_metrics
                  (zone_id,dataset_version,mapped_waterway_distance_m,mapped_drain_distance_m,mapped_culvert_count,provenance)
                  values (%s,'pune-terrain-population-v1',%s,%s,%s,%s::jsonb)
                  on conflict (zone_id,dataset_version) do update set
                    mapped_waterway_distance_m=excluded.mapped_waterway_distance_m,
                    mapped_drain_distance_m=excluded.mapped_drain_distance_m,
                    mapped_culvert_count=excluded.mapped_culvert_count,
                    provenance=public.zone_dataset_metrics.provenance || excluded.provenance,
                    computed_at=now()""", (row["zone_id"], row["mapped_waterway_distance_m"],
                    row["mapped_drain_distance_m"], row["mapped_culvert_count"],
                    json.dumps({"mapped_waterways": {**batch["provenance"], "source": "OpenStreetMap", "storage": "postgis"}})))
        connection.commit()
    return {"database_status": "committed", "database_inserted_waterways": inserted,
            "database_existing_waterways": len(batch["records"]) - inserted, "database_zone_metrics_upserted": len(metric_rows)}


async def import_supabase(batch: dict, indicators: list[dict], gateway: SupabaseGateway) -> dict:
    """Insert missing PostGIS lines through the service API and merge mapped metrics only."""
    if batch["failures"] or batch["duplicate_ids"] or not batch["records"]:
        raise ValueError("Waterway source has invalid or duplicate records; no database writes were made")
    expected_zones = {zone.slug: str(zone.id) for zone in grid_zones()}
    if len(indicators) != len(expected_zones) or {row.get("zone_slug") for row in indicators} != set(expected_zones) or any(
        row.get("zone_id") != expected_zones[row["zone_slug"]] or row.get("mapped_drain_distance_m") is None
        for row in indicators
    ):
        raise ValueError("Mapped indicators do not cover the validated grid; no database writes were made")
    zones = await gateway.table("zones", privileged=True, params={"select": "id,slug", "limit": 100})
    found_zones = {row["slug"]: row["id"] for row in zones if row.get("slug") in expected_zones}
    if found_zones != expected_zones:
        raise ValueError("Supabase grid IDs differ from the validated local grid; no writes were made")
    metrics = await gateway.table("zone_dataset_metrics", privileged=True,
        params={"select": "id,zone_id,dataset_version,population_estimate,provenance",
                "dataset_version": "eq.pune-terrain-population-v1", "limit": 100})
    by_zone = {row["zone_id"]: row for row in metrics}
    if len(by_zone) != len(expected_zones):
        raise ValueError("Expected nine existing WorldPop metric rows; no writes were made")
    # These reads also detect a partially applied migration before the first insert.
    await gateway.table("waterways", privileged=True, params={"select": "id", "limit": 1})
    await gateway.table("zone_dataset_metrics", privileged=True,
        params={"select": "mapped_waterway_distance_m,mapped_drain_distance_m,mapped_culvert_count", "limit": 1})
    existing = await gateway.table("waterways", privileged=True,
        params={"select": "external_id", "source_dataset": f"eq.{batch['provenance']['source_dataset']}", "limit": 1000})
    existing_ids = {row["external_id"] for row in existing}
    inserted = 0
    for item in batch["records"]:
        if item["external_id"] in existing_ids:
            continue
        geometry = shape(item["geometry"])
        if geometry.geom_type == "LineString":
            geometry = MultiLineString([geometry])
        payload = {key: item[key] for key in ("source_kind", "source_dataset", "external_id", "name",
                                              "waterway_class", "is_culvert", "source_tags", "provenance")}
        payload["geometry"] = f"SRID=4326;{geometry.wkt}"
        created = await gateway.table("waterways", "POST", privileged=True,
            params={"on_conflict": "source_dataset,external_id"}, json=payload,
            prefer="resolution=ignore-duplicates,return=representation")
        inserted += len(created) if isinstance(created, list) else 0
    indicator_provenance = {**batch["provenance"], "source": "OpenStreetMap", "storage": "postgis"}
    for row in indicators:
        prior = by_zone[row["zone_id"]]
        provenance = {**(prior.get("provenance") or {}), "mapped_waterways": indicator_provenance}
        await gateway.table("zone_dataset_metrics", "PATCH", privileged=True,
            params={"id": f"eq.{prior['id']}"},
            json={"mapped_waterway_distance_m": row["mapped_waterway_distance_m"],
                  "mapped_drain_distance_m": row["mapped_drain_distance_m"],
                  "mapped_culvert_count": row["mapped_culvert_count"], "provenance": provenance,
                  "computed_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
    return {"database_status": "committed", "database_inserted_waterways": inserted,
            "database_existing_waterways": len(batch["records"]) - inserted,
            "database_zone_metrics_upserted": len(indicators)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--municipal-metadata", type=Path, help="JSON metadata for an authoritative municipal GeoJSON")
    parser.add_argument("--report", type=Path, default=ROOT / "data/processed/pune_waterways_validation.json")
    import_mode = parser.add_mutually_exclusive_group()
    import_mode.add_argument("--import-db", action="store_true", help="Import through DATABASE_URL")
    import_mode.add_argument("--import-supabase", action="store_true", help="Import through server-side Supabase credentials")
    args = parser.parse_args()
    metadata = json.loads(args.municipal_metadata.read_text(encoding="utf-8")) if args.municipal_metadata else None
    batch = parse_file(args.input, municipal_metadata=metadata)
    indicators = zone_indicators(batch["records"])
    report = {"source": batch["provenance"], "feature_count": batch["feature_count"],
              "valid_records": len(batch["records"]), "counts": batch["counts"], "culvert_count": batch["culvert_count"],
              "duplicate_ids": batch["duplicate_ids"], "failed_records": batch["failures"], "zones": indicators,
              "database_status": "not_attempted", "database_inserted_waterways": 0}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.import_db:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            parser.error("DATABASE_URL is required for --import-db; validation report is saved")
        report.update(import_database(batch, indicators, database_url))
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.import_supabase:
        async def run():
            gateway = SupabaseGateway(get_settings())
            try:
                return await import_supabase(batch, indicators, gateway)
            finally:
                await gateway.close()
        report.update(asyncio.run(run()))
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("feature_count", "valid_records", "counts", "culvert_count", "duplicate_ids", "failed_records", "database_status", "database_inserted_waterways")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
