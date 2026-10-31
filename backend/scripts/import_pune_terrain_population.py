"""Validate and import sourced Pune DEM/population metrics without invented values."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.zone_rasters import inspect_raster, zonal_raster_metrics
from app.services.zones import grid_zones
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway

ROOT = Path(__file__).resolve().parents[2]


def upsert_metrics(rows: list[dict], database_url: str, dataset_version: str) -> int:
    """Merge only supplied fields into the existing dataset version."""
    import psycopg
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for row in rows:
                cursor.execute("""insert into public.zone_dataset_metrics
                  (zone_id,dataset_version,dem_mean_m,slope_mean_degrees,population_estimate,provenance)
                  values (%s,%s,%s,%s,%s,%s::jsonb)
                  on conflict (zone_id,dataset_version) do update set
                    dem_mean_m=coalesce(excluded.dem_mean_m,public.zone_dataset_metrics.dem_mean_m),
                    slope_mean_degrees=coalesce(excluded.slope_mean_degrees,public.zone_dataset_metrics.slope_mean_degrees),
                    population_estimate=coalesce(excluded.population_estimate,public.zone_dataset_metrics.population_estimate),
                    provenance=public.zone_dataset_metrics.provenance || excluded.provenance,
                    computed_at=now()""",
                    (row["zone_id"], dataset_version, row.get("dem_mean_m"), row.get("slope_mean_degrees"), row.get("population_estimate"), json.dumps(row["provenance"])))
        connection.commit()
    return len(rows)


def validate_dem_import_metadata(metadata: dict) -> None:
    """Require real dataset provenance before committing derived terrain values."""
    for key in ("dem_source", "dem_licence", "retrieved_at_utc"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip() or value.lower().startswith("replace"):
            raise ValueError(f"DEM import requires a real {key} value")
    source = (metadata.get("sources") or {}).get("dem")
    if not isinstance(source, str) or not source.strip() or source.lower().startswith("replace"):
        raise ValueError("DEM import requires the exact product citation in sources.dem")
    try:
        retrieved = datetime.fromisoformat(metadata["retrieved_at_utc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("retrieved_at_utc must be an ISO 8601 timestamp") from exc
    if retrieved.tzinfo is None:
        raise ValueError("retrieved_at_utc must include a timezone")


async def import_dem_supabase(report: dict, gateway: SupabaseGateway) -> dict:
    """Patch sourced DEM fields in existing WorldPop rows; never replace population."""
    if report["status"] != "validated" or report["dem_zones_covered"] != 9 or report["slope_zones_covered"] != 9:
        raise ValueError("Nine validated DEM/slope cells are required; no database writes were made")
    if "population" in report["sources"]:
        raise ValueError("Use the SQL importer for a population raster; no database writes were made")
    expected = {zone.slug: str(zone.id) for zone in grid_zones()}
    if len(report["zones"]) != len(expected) or any(
        row["zone_slug"] not in expected or row["zone_id"] != expected[row["zone_slug"]]
        or row["dem_mean_m"] is None or row["slope_mean_degrees"] is None
        for row in report["zones"]
    ):
        raise ValueError("DEM report does not match the Pune analysis grid; no database writes were made")
    zones = await gateway.table("zones", privileged=True, params={"select": "id,slug", "limit": 100})
    if {row["slug"]: row["id"] for row in zones if row.get("slug") in expected} != expected:
        raise ValueError("Supabase zone IDs differ from the validated grid; no database writes were made")
    metrics = await gateway.table("zone_dataset_metrics", privileged=True,
        params={"select": "id,zone_id,dataset_version,population_estimate,dem_mean_m,slope_mean_degrees,mapped_drain_distance_m,provenance",
                "dataset_version": f"eq.{report['dataset_version']}", "limit": 100})
    by_zone = {row["zone_id"]: row for row in metrics}
    if len(metrics) != 9 or set(by_zone) != set(expected.values()) or any(row.get("population_estimate") is None for row in metrics):
        raise ValueError("Expected nine existing WorldPop rows in this dataset version; no database writes were made")
    digest = report["sources"]["dem"]["sha256"]
    for row in metrics:
        prior_dem = (row.get("provenance") or {}).get("dem") or {}
        if (row.get("dem_mean_m") is not None or row.get("slope_mean_degrees") is not None) and prior_dem.get("sha256") != digest:
            raise ValueError("An existing terrain source differs; manual review is required before any writes")
    updated = 0
    for zone in report["zones"]:
        prior = by_zone[zone["zone_id"]]
        if (prior.get("provenance") or {}).get("dem", {}).get("sha256") == digest and prior.get("slope_mean_degrees") is not None:
            continue
        dem_source = {key: value for key, value in report["sources"]["dem"].items() if key != "file"}
        provenance = {**(prior.get("provenance") or {}), "dem": {**dem_source, "file_name": Path(report["sources"]["dem"]["file"]).name,
                                                               "storage": "postgis_zone_metric"}}
        await gateway.table("zone_dataset_metrics", "PATCH", privileged=True,
            params={"id": f"eq.{prior['id']}"},
            json={"dem_mean_m": zone["dem_mean_m"], "slope_mean_degrees": zone["slope_mean_degrees"],
                  "provenance": provenance, "computed_at": datetime.now(timezone.utc).isoformat()},
            prefer="return=minimal")
        updated += 1
    readback = await gateway.table("zone_dataset_metrics", privileged=True,
        params={"select": "zone_id,population_estimate,slope_mean_degrees,mapped_drain_distance_m,provenance",
                "dataset_version": f"eq.{report['dataset_version']}", "limit": 100})
    verified = {row["zone_id"]: row for row in readback}
    if set(verified) != set(expected.values()) or any(
        verified[zone["zone_id"]].get("slope_mean_degrees") is None
        or (verified[zone["zone_id"]].get("provenance") or {}).get("dem", {}).get("sha256") != digest
        or verified[zone["zone_id"]].get("population_estimate") != by_zone[zone["zone_id"]]["population_estimate"]
        or verified[zone["zone_id"]].get("mapped_drain_distance_m") != by_zone[zone["zone_id"]].get("mapped_drain_distance_m")
        for zone in report["zones"]
    ):
        raise RuntimeError("Terrain readback failed; inspect the nine metric rows")
    return {"database_status": "committed", "database_rows_upserted": updated,
            "database_rows_verified": len(verified)}


def build_report(dem_path: Path | None, population_path: Path | None, metadata: dict, *, derive_slope: bool = True) -> dict:
    zones = [{"id": str(z.id), "slug": z.slug, "geometry": z.geometry} for z in grid_zones()]
    report = {"status": "validated", "dataset_version": metadata["dataset_version"], "zone_count": len(zones),
              "generated_at_utc": datetime.now(timezone.utc).isoformat(), "sources": {}, "errors": [], "warnings": [], "zones": []}
    source_results = {}
    for kind, path, unit in (("dem", dem_path, metadata.get("elevation_unit")),
                             ("population", population_path, metadata.get("population_unit"))):
        if path is None:
            continue
        try:
            provenance = inspect_raster(path, kind=kind, declared_unit=unit)
            if kind == "population" and (not isinstance(metadata.get("population_year"), int) or not metadata.get("population_resolution")):
                raise ValueError("Population dataset year and spatial resolution must be declared")
            report["sources"][kind] = {**provenance, "source": metadata.get(f"{kind}_source"),
                                       "licence": metadata.get(f"{kind}_licence"),
                                       "dataset_year": metadata.get("population_year") if kind == "population" else None,
                                       "spatial_resolution": metadata.get("population_resolution") if kind == "population" else None,
                                       "retrieved_at_utc": metadata.get("retrieved_at_utc")}
            source_results[kind] = zonal_raster_metrics(path, zones, kind=kind, slope=derive_slope)
        except (OSError, ValueError, RuntimeError) as exc:
            report["errors"].append({"source": kind, "file": str(path), "reason": str(exc)})
    for i, zone in enumerate(zones):
        dem = source_results.get("dem", [{}] * len(zones))[i]
        population = source_results.get("population", [{}] * len(zones))[i]
        provenance = {kind: report["sources"][kind] for kind in source_results}
        report["zones"].append({"zone_id": zone["id"], "zone_slug": zone["slug"],
                                "dem_mean_m": dem.get("mean_m"), "dem_min_m": dem.get("min_m"),
                                "dem_max_m": dem.get("max_m"), "slope_mean_degrees": dem.get("slope_mean_degrees"),
                                "population_estimate": population.get("population_estimate"),
                                "dem_coverage_pixels": dem.get("coverage_pixels", 0),
                                "population_coverage_pixels": population.get("coverage_pixels", 0),
                                "provenance": provenance})
    report["dem_zones_covered"] = sum(row["dem_mean_m"] is not None for row in report["zones"])
    report["slope_zones_covered"] = sum(row["slope_mean_degrees"] is not None for row in report["zones"])
    report["population_zones_covered"] = sum(row["population_estimate"] is not None for row in report["zones"])
    if report["errors"]:
        report["status"] = "invalid_sources"
    elif "dem" in source_results:
        try:
            validate_dem_import_metadata(metadata)
        except ValueError as exc:
            report["status"] = "requires_source_metadata"
            report["warnings"].append(str(exc))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=ROOT / "data/raw/pune_elevation.tif")
    parser.add_argument("--population", type=Path, default=ROOT / "data/raw/pune_population.tif")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=ROOT / "data/processed/pune_zone_metrics_validation.json")
    import_mode = parser.add_mutually_exclusive_group()
    import_mode.add_argument("--import-db", action="store_true")
    import_mode.add_argument("--import-supabase", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--dem-only", action="store_true")
    selection.add_argument("--population-only", action="store_true")
    parser.add_argument("--no-slope", action="store_true")
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    if not metadata.get("dataset_version") or not metadata.get("sources"):
        parser.error("Metadata requires dataset_version and sources")
    selected = {"dem": not args.population_only, "population": not args.dem_only}
    report = build_report(args.dem if selected["dem"] and args.dem.is_file() else None,
                          args.population if selected["population"] and args.population.is_file() else None,
                          metadata, derive_slope=not args.no_slope)
    for kind, path in (("dem", args.dem), ("population", args.population)):
        if selected[kind] and not path.is_file():
            report["errors"].append({"source": kind, "file": str(path), "reason": "file missing"})
            report["status"] = "invalid_sources"
    report["database_status"] = "not_attempted"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if args.import_db:
        if report["status"] != "validated":
            parser.error("Raster validation or source metadata is incomplete; see report; no database writes were made")
        if selected["dem"]:
            try:
                validate_dem_import_metadata(metadata)
            except ValueError as exc:
                parser.error(str(exc))
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            parser.error("DATABASE_URL is required for --import-db")
        rows = [row for row in report["zones"] if row["dem_mean_m"] is not None or row["population_estimate"] is not None]
        report["database_rows_upserted"] = upsert_metrics(rows, database_url, metadata["dataset_version"])
        report["database_status"] = "committed"
        args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if args.import_supabase:
        if report["status"] != "validated" or not selected["dem"] or selected["population"]:
            parser.error("Select only a validated DEM with --dem-only; no database writes were made")
        async def run():
            gateway = SupabaseGateway(get_settings())
            try:
                return await import_dem_supabase(report, gateway)
            finally:
                await gateway.close()
        report.update(asyncio.run(run()))
        args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "dem_zones_covered", "slope_zones_covered", "population_zones_covered", "errors", "database_status")}, default=str))


if __name__ == "__main__":
    main()
