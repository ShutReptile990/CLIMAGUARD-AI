"""Validate a local OSM GeoJSON and insert only new records into PostGIS.

Validation is the default. Database writes require --import-db and DATABASE_URL,
or --import-supabase with server-side Supabase credentials.
Existing rows are never updated or deleted.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import NAMESPACE_URL, uuid5

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.errors import GEOSException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
DEFAULT_INPUT = ROOT / "data" / "raw" / "pune_infrastructure.geojson"
DEFAULT_REPORT = ROOT / "data" / "processed" / "pune_infrastructure_validation.json"
# Broad Pune file sanity envelope, not an administrative boundary.
PUNE_BOUNDS = (73.50, 18.20, 74.20, 18.90)  # west, south, east, north
FACILITY_KINDS = {"hospital", "school", "fire_station"}
MAJOR_ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
OSM_ID = re.compile(r"^(node|way|relation)/([1-9][0-9]*)$")


@dataclass
class ImportBatch:
    facilities: list[dict] = field(default_factory=list)
    roads: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    ignored_unclassified: int = 0
    metadata: dict = field(default_factory=dict)
    feature_count: int = 0

    def summary(self) -> dict:
        return {
            "source": "OpenStreetMap GeoJSON",
            "source_file": self.metadata.get("source_file"),
            "source_sha256": self.metadata.get("sha256"),
            "osm_timestamp": self.metadata.get("osm_timestamp"),
            "source_copyright": self.metadata.get("copyright"),
            "feature_count": self.feature_count,
            "facility_candidates": len(self.facilities),
            "facility_counts": dict(sorted(Counter(item["kind"] for item in self.facilities).items())),
            "road_candidates": len(self.roads),
            "road_counts": dict(sorted(Counter(item["highway_class"] for item in self.roads).items())),
            "ignored_unclassified": self.ignored_unclassified,
            "duplicate_osm_ids": len(self.duplicate_ids),
            "failed_records": len(self.failures),
            "database_status": "not_attempted",
            "database_inserted_facilities": 0,
            "database_inserted_roads": 0,
            "database_existing_facilities": None,
            "database_existing_roads": None,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _failure(batch: ImportBatch, index: int, osm_ref: object, reason: str) -> None:
    batch.failures.append({"feature_index": index, "osm_ref": str(osm_ref) if osm_ref is not None else None, "reason": reason})


def _validated_geometry(raw: dict, index: int, osm_ref: object, batch: ImportBatch) -> BaseGeometry | None:
    try:
        geometry = shape(raw)
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("empty or invalid geometry")
        west, south, east, north = geometry.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("coordinates outside EPSG:4326 bounds")
        if not (PUNE_BOUNDS[0] <= west <= east <= PUNE_BOUNDS[2] and PUNE_BOUNDS[1] <= south <= north <= PUNE_BOUNDS[3]):
            raise ValueError("geometry outside declared Pune source envelope")
        return geometry
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, GEOSException) as exc:
        _failure(batch, index, osm_ref, f"invalid_geometry: {exc}")
        return None


def parse_geojson(path: Path) -> ImportBatch:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Expected a GeoJSON FeatureCollection")
    crs = payload.get("crs")
    if crs is not None and crs not in ("EPSG:4326", {"type": "name", "properties": {"name": "EPSG:4326"}}):
        raise ValueError("Only EPSG:4326 GeoJSON is supported; reproject the source before import")
    batch = ImportBatch(feature_count=len(payload["features"]), metadata={"source_file": str(path.resolve()), "sha256": _sha256(path), "osm_timestamp": payload.get("timestamp"), "copyright": payload.get("copyright"), "generator": payload.get("generator"), "validated_at_utc": datetime.now(timezone.utc).isoformat(), "crs": "EPSG:4326"})
    seen: set[tuple[str, int]] = set()
    for index, feature in enumerate(payload["features"]):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            _failure(batch, index, None, "invalid_feature")
            continue
        tags = feature.get("properties") or {}
        if not isinstance(tags, dict):
            _failure(batch, index, feature.get("id"), "invalid_properties")
            continue
        osm_ref = tags.get("@id") or feature.get("id")
        match = OSM_ID.fullmatch(str(osm_ref)) if osm_ref is not None else None
        if match is None or (feature.get("id") and tags.get("@id") and feature["id"] != tags["@id"]):
            _failure(batch, index, osm_ref, "invalid_or_conflicting_osm_id")
            continue
        osm_type, osm_id = match.group(1), int(match.group(2))
        key = (osm_type, osm_id)
        if key in seen:
            batch.duplicate_ids.append(str(osm_ref))
            continue
        raw_geometry = feature.get("geometry")
        geometry = _validated_geometry(raw_geometry, index, osm_ref, batch)
        if geometry is None:
            continue
        amenity = tags.get("amenity")
        facility_kind = amenity if amenity in FACILITY_KINDS else "hospital" if tags.get("healthcare") == "hospital" else None
        highway_class = tags.get("highway") if tags.get("highway") in MAJOR_ROADS else None
        common = {"osm_type": osm_type, "osm_id": osm_id, "osm_ref": str(osm_ref), "geometry": raw_geometry, "tags": tags, "source": "OpenStreetMap", "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}"}
        classified = False
        accepted = False
        if facility_kind:
            classified = True
            name = next((value.strip() for key_name in ("name", "name:en", "name:mr") if isinstance((value := tags.get(key_name)), str) and value.strip()), None)
            if not name:
                _failure(batch, index, osm_ref, "facility_missing_source_name")
            elif geometry.geom_type not in ("Point", "Polygon", "MultiPolygon"):
                _failure(batch, index, osm_ref, f"unsupported_facility_geometry: {geometry.geom_type}")
            else:
                marker = geometry if geometry.geom_type == "Point" else geometry.representative_point()
                batch.facilities.append({**common, "name": name, "kind": facility_kind, "marker": [marker.x, marker.y]})
                accepted = True
        if highway_class:
            classified = True
            if geometry.geom_type != "LineString" or geometry.length == 0:
                _failure(batch, index, osm_ref, f"unsupported_road_geometry: {geometry.geom_type}")
            else:
                batch.roads.append({**common, "name": tags.get("name") if isinstance(tags.get("name"), str) else None, "highway_class": highway_class})
                accepted = True
        if not classified:
            batch.ignored_unclassified += 1
        if accepted:
            seen.add(key)
    return batch


FACILITY_INSERT = """insert into public.infrastructure
    (name,kind,location,osm_geometry,source,osm_type,osm_id,osm_tags)
    values (%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),
      'OpenStreetMap',%s,%s,%s::jsonb)
    on conflict (osm_type,osm_id) where osm_type is not null do nothing returning id"""
ROAD_INSERT = """insert into public.osm_roads
    (osm_type,osm_id,name,highway_class,geometry,osm_tags,source)
    values (%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s::jsonb,'OpenStreetMap')
    on conflict (osm_type,osm_id) do nothing returning id"""


def import_database(batch: ImportBatch, database_url: str) -> dict:
    import psycopg
    inserted_facilities = inserted_roads = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select count(*) from information_schema.columns
                where table_schema='public' and table_name='infrastructure'
                and column_name in ('osm_type','osm_id','osm_geometry')""")
            if cursor.fetchone()[0] != 3:
                raise RuntimeError("Apply migrations 001–005 before importing; infrastructure.osm_geometry is missing")
            cursor.execute("select to_regclass('public.osm_roads'), to_regclass('public.osm_import_runs')")
            if any(value is None for value in cursor.fetchone()):
                raise RuntimeError("Apply migrations 001–005 before importing; OSM tables are missing")
            for item in batch.facilities:
                lng, lat = item["marker"]
                cursor.execute(FACILITY_INSERT, (item["name"], item["kind"], lng, lat, json.dumps(item["geometry"], ensure_ascii=False), item["osm_type"], item["osm_id"], json.dumps(item["tags"], ensure_ascii=False)))
                inserted_facilities += int(cursor.fetchone() is not None)
            for item in batch.roads:
                cursor.execute(ROAD_INSERT, (item["osm_type"], item["osm_id"], item["name"], item["highway_class"], json.dumps(item["geometry"], ensure_ascii=False), json.dumps(item["tags"], ensure_ascii=False)))
                inserted_roads += int(cursor.fetchone() is not None)
            provenance = {**batch.metadata, "candidate_facilities": len(batch.facilities), "candidate_roads": len(batch.roads), "existing_facilities_skipped": len(batch.facilities) - inserted_facilities, "existing_roads_skipped": len(batch.roads) - inserted_roads, "failed_record_count": len(batch.failures)}
            cursor.execute("""insert into public.osm_import_runs(facility_count,road_count,provenance)
                values (%s,%s,%s::jsonb)""", (inserted_facilities, inserted_roads, json.dumps(provenance, ensure_ascii=False)))
        connection.commit()
    return {"database_status": "committed", "database_inserted_facilities": inserted_facilities, "database_inserted_roads": inserted_roads, "database_existing_facilities": len(batch.facilities) - inserted_facilities, "database_existing_roads": len(batch.roads) - inserted_roads}


async def import_supabase(batch: ImportBatch) -> dict:
    """Resume-safe insert-only import using the configured server-side credential."""
    from app.core.config import get_settings
    from app.integrations.supabase import SupabaseGateway

    settings = get_settings()
    if not (settings.configured and settings.supabase_secret_key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for --import-supabase")
    gateway = SupabaseGateway(settings)

    async def existing_keys(table: str) -> set[tuple[str, int]]:
        found: set[tuple[str, int]] = set()
        offset = 0
        while True:
            rows = await gateway.table(table, privileged=True, params={
                "select": "osm_type,osm_id", "source": "eq.OpenStreetMap",
                "order": "osm_type,osm_id", "limit": 1000, "offset": offset,
            })
            if not isinstance(rows, list):
                raise RuntimeError(f"Unexpected {table} readback")
            found.update((row["osm_type"], int(row["osm_id"])) for row in rows if row.get("osm_type") and row.get("osm_id") is not None)
            if len(rows) < 1000:
                return found
            offset += len(rows)

    def facility_row(item: dict) -> dict:
        lng, lat = item["marker"]
        return {
            "id": str(uuid5(NAMESPACE_URL, f"climaguard-osm/{item['osm_ref']}")),
            "name": item["name"], "kind": item["kind"],
            "location": f"SRID=4326;POINT({lng} {lat})",
            "osm_geometry": f"SRID=4326;{shape(item['geometry']).wkt}",
            "source": "OpenStreetMap", "osm_type": item["osm_type"], "osm_id": item["osm_id"],
            "osm_tags": item["tags"],
        }

    def road_row(item: dict) -> dict:
        return {
            "id": str(uuid5(NAMESPACE_URL, f"climaguard-osm/{item['osm_ref']}")),
            "name": item["name"], "highway_class": item["highway_class"],
            "geometry": f"SRID=4326;{shape(item['geometry']).wkt}",
            "source": "OpenStreetMap", "osm_type": item["osm_type"], "osm_id": item["osm_id"],
            "osm_tags": item["tags"],
        }

    try:
        before_facilities = await existing_keys("infrastructure")
        before_roads = await existing_keys("osm_roads")
        missing_facilities = [item for item in batch.facilities if (item["osm_type"], item["osm_id"]) not in before_facilities]
        missing_roads = [item for item in batch.roads if (item["osm_type"], item["osm_id"]) not in before_roads]
        for table, items, converter in (
            ("infrastructure", missing_facilities, facility_row),
            ("osm_roads", missing_roads, road_row),
        ):
            for start in range(0, len(items), 100):
                rows = [converter(item) for item in items[start:start + 100]]
                await gateway.table(table, "POST", privileged=True, params={"select": "id"},
                    json=rows, prefer="resolution=ignore-duplicates,return=minimal")
        after_facilities = await existing_keys("infrastructure")
        after_roads = await existing_keys("osm_roads")
        facility_keys = {(item["osm_type"], item["osm_id"]) for item in batch.facilities}
        road_keys = {(item["osm_type"], item["osm_id"]) for item in batch.roads}
        if not facility_keys <= after_facilities or not road_keys <= after_roads:
            raise RuntimeError("Supabase readback is missing one or more validated OSM IDs; rerun the insert-only import")
        inserted_facilities = len(after_facilities - before_facilities)
        inserted_roads = len(after_roads - before_roads)
        provenance = {**batch.metadata, "candidate_facilities": len(batch.facilities),
            "candidate_roads": len(batch.roads), "existing_facilities_skipped": len(batch.facilities) - inserted_facilities,
            "existing_roads_skipped": len(batch.roads) - inserted_roads, "failed_record_count": len(batch.failures),
            "import_method": "Supabase REST insert-only EPSG:4326 EWKT"}
        await gateway.table("osm_import_runs", "POST", privileged=True,
            json={"facility_count": inserted_facilities, "road_count": inserted_roads, "provenance": provenance},
            prefer="return=minimal")
        return {"database_status": "committed_and_verified",
                "database_inserted_facilities": inserted_facilities, "database_inserted_roads": inserted_roads,
                "database_existing_facilities": len(batch.facilities) - inserted_facilities,
                "database_existing_roads": len(batch.roads) - inserted_roads}
    finally:
        await gateway.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Pune OSM GeoJSON; optionally insert only missing records into PostGIS")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    import_mode = parser.add_mutually_exclusive_group()
    import_mode.add_argument("--import-db", action="store_true", help="Insert new rows using DATABASE_URL; existing rows are left untouched")
    import_mode.add_argument("--import-supabase", action="store_true", help="Insert new rows using the server-side Supabase credential; existing rows are left untouched")
    args = parser.parse_args()
    batch = parse_geojson(args.input)
    summary = batch.summary()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    def save_report() -> None:
        args.report.write_text(json.dumps({"summary": summary, "failed_records": batch.failures, "duplicate_osm_ids": batch.duplicate_ids}, indent=2, ensure_ascii=False), encoding="utf-8")
    save_report()
    if args.import_db:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise SystemExit("DATABASE_URL is required for --import-db; validation can run without it")
        summary.update(import_database(batch, database_url))
        save_report()
    if args.import_supabase:
        try:
            summary.update(asyncio.run(import_supabase(batch)))
        except Exception as exc:
            summary.update({"database_status": "incomplete", "database_error_type": type(exc).__name__})
            save_report()
            raise
        save_report()
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
