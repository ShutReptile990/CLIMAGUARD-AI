"""Insert validated WorldPop polygon totals into existing Supabase zone metrics.

Run from backend: python scripts/persist_worldpop_supabase.py --import-db
Existing non-null estimates are never replaced.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway
from app.services.local_population import REPORT, local_population_context
from app.services.zones import grid_zones

DATASET_VERSION = "pune-terrain-population-v1"


def validated_rows() -> dict[str, dict]:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if report.get("zones_covered") != len(grid_zones()) or report.get("zones_missing") != 0 or report.get("errors"):
        raise ValueError("WorldPop validation report has missing zones or provider errors.")
    rows = local_population_context()
    if len(rows) != len(grid_zones()) or set(rows) != {zone.slug for zone in grid_zones()}:
        raise ValueError("Validated WorldPop report does not cover all disjoint Pune grid cells.")
    return rows


async def persist(gateway: SupabaseGateway, *, write: bool) -> dict:
    rows = validated_rows()
    zones = await gateway.table("zones", privileged=True, params={"select": "id,slug", "limit": 100})
    zone_ids = {row["slug"]: row["id"] for row in zones if row.get("slug") in rows}
    if len(zone_ids) != len(rows) or any(zone_ids[zone.slug] != str(zone.id) for zone in grid_zones()):
        raise ValueError("Supabase zone IDs do not match the validated grid; no estimates were written.")
    existing = await gateway.table("zone_dataset_metrics", privileged=True,
        params={"select": "id,zone_id,dataset_version,population_estimate,provenance",
                "dataset_version": f"eq.{DATASET_VERSION}", "limit": 100})
    by_zone = {row["zone_id"]: row for row in existing}
    result = {"validated_zones": len(rows), "inserted": 0, "filled_null": 0, "already_present": 0,
              "conflicts": [], "write_requested": write}
    for slug, row in rows.items():
        zone_id = zone_ids[slug]
        estimate = row["population_estimate"]
        previous = by_zone.get(zone_id)
        if previous and previous["population_estimate"] is not None:
            if previous["population_estimate"] == estimate:
                result["already_present"] += 1
            else:
                result["conflicts"].append(slug)
            continue
        provenance = {**((previous.get("provenance") or {}) if previous else {}),
                      "population": {**row["provenance"]["population"], "storage": "supabase_postgis"}}
        if not write:
            continue
        if previous:
            await gateway.table("zone_dataset_metrics", "PATCH", privileged=True,
                params={"id": f"eq.{previous['id']}", "population_estimate": "is.null"},
                json={"population_estimate": estimate, "provenance": provenance}, prefer="return=minimal")
            result["filled_null"] += 1
        else:
            await gateway.table("zone_dataset_metrics", "POST", privileged=True,
                params={"on_conflict": "zone_id,dataset_version"},
                json={"zone_id": zone_id, "dataset_version": DATASET_VERSION,
                      "population_estimate": estimate, "provenance": provenance},
                prefer="resolution=ignore-duplicates,return=minimal")
            result["inserted"] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-db", action="store_true", help="Write validated estimates to Supabase")
    args = parser.parse_args()

    async def run():
        gateway = SupabaseGateway(get_settings())
        try:
            return await persist(gateway, write=args.import_db)
        finally:
            await gateway.close()

    result = asyncio.run(run())
    if args.import_db and not result["conflicts"]:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        report["database_status"] = "committed"
        report.pop("database_rows_inserted", None)
        report.pop("database_rows_already_present", None)
        report["database_rows_present"] = result["inserted"] + result["filled_null"] + result["already_present"]
        report["database_rows_inserted_last_run"] = result["inserted"]
        report["database_checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
