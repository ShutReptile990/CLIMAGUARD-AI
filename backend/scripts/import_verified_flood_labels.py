"""Validate verified event observations; never infer negatives from missing reports."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.zones import grid_zones

REQUIRED = ("event_id", "event_date", "latitude", "longitude", "source", "temporal_resolution_hours",
            "observed_flood_status", "verification_reference", "observation_method")


def validate_labels(path: Path) -> dict:
    zones = [(zone, shape(zone.geometry)) for zone in grid_zones()]
    valid, failures, seen = [], [], set()
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or any(field not in reader.fieldnames for field in REQUIRED):
            raise ValueError(f"CSV requires columns: {', '.join(REQUIRED)}")
        for line_number, row in enumerate(reader, 2):
            try:
                if any(not (row.get(field) or "").strip() for field in REQUIRED):
                    raise ValueError("required field missing")
                event_id = row["event_id"].strip()
                if event_id in seen:
                    raise ValueError("duplicate event_id")
                observed_at = datetime.fromisoformat(row["event_date"].strip().replace("Z", "+00:00"))
                if observed_at.tzinfo is None:
                    raise ValueError("event_date needs an explicit timezone")
                observed_at = observed_at.astimezone(timezone.utc)
                if observed_at > datetime.now(timezone.utc):
                    raise ValueError("future event_date")
                hours = int(row["temporal_resolution_hours"])
                if not 1 <= hours <= 168:
                    raise ValueError("temporal_resolution_hours must be 1..168")
                status = row["observed_flood_status"].strip().lower()
                if status not in ("true", "false", "1", "0"):
                    raise ValueError("observed_flood_status must be explicitly true or false")
                latitude, longitude = float(row["latitude"]), float(row["longitude"])
                point = Point(longitude, latitude)
                matches = [zone for zone, polygon in zones if polygon.covers(point)]
                if len(matches) != 1:
                    raise ValueError("location must belong to exactly one configured analysis zone")
                if len(row["source"].strip()) < 5 or len(row["verification_reference"].strip()) < 5:
                    raise ValueError("source and verification reference must identify evidence")
                record = {"event_id": event_id, "observed_at": observed_at.isoformat(), "latitude": latitude,
                          "longitude": longitude, "temporal_resolution_hours": hours,
                          "observed_flood": status in ("true", "1"), "source": row["source"].strip(),
                          "verification_reference": row["verification_reference"].strip(),
                          "observation_method": row["observation_method"].strip(),
                          "zone_id": str(matches[0].id), "zone_slug": matches[0].slug}
                valid.append(record)
                seen.add(event_id)
            except (ValueError, TypeError, OverflowError) as exc:
                failures.append({"csv_line": line_number, "event_id": row.get("event_id"), "reason": str(exc)})
    return {"valid_records": valid, "failed_records": failures, "positive_labels": sum(x["observed_flood"] for x in valid),
            "verified_negative_labels": sum(not x["observed_flood"] for x in valid)}


def import_database(records: list[dict], database_url: str) -> dict:
    import psycopg
    inserted = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            if cursor.execute("select to_regclass('public.verified_flood_labels')").fetchone()[0] is None:
                raise RuntimeError("Apply migration 006 before importing verified labels")
            for row in records:
                cursor.execute("""insert into public.verified_flood_labels
                  (event_id,observed_at,temporal_resolution_hours,location,zone_id,observed_flood,source,
                   verification_reference,observation_method,provenance)
                  values (%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s,%s,%s,%s,%s,%s::jsonb)
                  on conflict (event_id) do nothing returning id""",
                  (row["event_id"], row["observed_at"], row["temporal_resolution_hours"],
                   row["longitude"], row["latitude"], row["zone_id"], row["observed_flood"],
                   row["source"], row["verification_reference"], row["observation_method"],
                   json.dumps({"import_format": "verified-flood-labels-v1", "zone_slug": row["zone_slug"]})))
                inserted += int(cursor.fetchone() is not None)
        connection.commit()
    return {"database_status": "committed", "database_inserted": inserted,
            "database_existing": len(records) - inserted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parents[2] / "data/processed/flood_labels_validation.json")
    parser.add_argument("--import-db", action="store_true")
    args = parser.parse_args()
    result = validate_labels(args.input)
    report = {"source_file": str(args.input.resolve()), "valid_count": len(result["valid_records"]),
              "positive_labels": result["positive_labels"], "verified_negative_labels": result["verified_negative_labels"],
              "failed_records": result["failed_records"], "database_status": "not_attempted"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.import_db:
        if report["failed_records"]:
            parser.error("Fix all validation failures before importing labels")
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            parser.error("DATABASE_URL is required for --import-db")
        report.update(import_database(result["valid_records"], database_url))
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
