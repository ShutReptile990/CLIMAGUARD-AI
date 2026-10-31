"""Fetch sourced WorldPop v2 polygon totals for the disjoint Pune grid."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import httpx
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.zones import grid_zones
from scripts.import_pune_terrain_population import upsert_metrics

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://api.worldpop.org/v2"


async def request_json(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> dict:
    for attempt in range(3):
        try:
            response = await client.request(method, f"{BASE}{path}", **kwargs)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("WorldPop returned a non-object response")
            return data
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * 2**attempt)
    raise RuntimeError("WorldPop retry exhausted")


async def population_for_zone(client: httpx.AsyncClient, zone, *, year: int, resolution: str,
                              cache_dir: Path, poll_seconds: float = 2, max_polls: int = 30) -> dict:
    geometry = zone.geometry
    key = sha256(json.dumps({"geometry": geometry, "year": year, "resolution": resolution}, sort_keys=True).encode()).hexdigest()
    cache_file = cache_dir / f"{key}.json"
    if cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("source") == "WorldPop Global2 API v2" and cached.get("zone_slug") == zone.slug:
            return cached
    submitted = await request_json(client, "POST", "/population", json={"geojson": geometry, "year": year, "resolution": resolution})
    task_id = submitted.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("WorldPop did not return a task_id")
    for _ in range(max_polls):
        response = await request_json(client, "GET", f"/tasks/{task_id}")
        if response.get("status") == "success":
            result = response.get("result") or {}
            total = result.get("total_population")
            if not isinstance(total, (int, float)) or not 0 <= total < 1e10:
                raise ValueError("WorldPop result has no valid total_population")
            if result.get("data_year") not in (None, year):
                raise ValueError("WorldPop returned a different dataset year")
            record = {"zone_id": str(zone.id), "zone_slug": zone.slug, "population_estimate": round(total),
                      "source": "WorldPop Global2 API v2", "source_url": BASE, "dataset_year": year,
                      "spatial_resolution": resolution, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                      "task_id": task_id, "geometry_sha256": key}
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
            return record
        if response.get("status") in ("failure", "failed", "error"):
            raise ValueError("WorldPop task failed")
        await asyncio.sleep(poll_seconds)
    raise TimeoutError("WorldPop task did not finish before polling limit")


async def collect(year: int, resolution: str, cache_dir: Path, client: httpx.AsyncClient) -> dict:
    zones = grid_zones()
    polygons = [shape(zone.geometry) for zone in zones]
    if any(p.intersection(q).area > 1e-12 for i, p in enumerate(polygons) for q in polygons[:i]):
        raise ValueError("Zones overlap; API totals could double-count people")
    records, errors = [], []
    for zone in zones:
        try:
            records.append(await population_for_zone(client, zone, year=year, resolution=resolution, cache_dir=cache_dir))
        except (httpx.HTTPError, OSError, ValueError, TimeoutError) as exc:
            errors.append({"zone_slug": zone.slug, "type": type(exc).__name__, "detail": str(exc)[:160]})
    return {"source": "WorldPop Global2 API v2", "dataset_year": year, "spatial_resolution": resolution,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "zones_covered": len(records),
            "zones_missing": len(zones) - len(records), "records": records, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True, choices=range(2015, 2031))
    parser.add_argument("--resolution", choices=("100m", "1km"), default="100m")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/processed/worldpop_cache")
    parser.add_argument("--report", type=Path, default=ROOT / "data/processed/pune_worldpop_validation.json")
    parser.add_argument("--dataset-version", default="pune-terrain-population-v1")
    parser.add_argument("--import-db", action="store_true")
    args = parser.parse_args()
    headers = {"User-Agent": "CLIMAGUARD-AI/0.4 (Pune analysis grid)"}
    if os.getenv("WORLDPOP_API_KEY"):
        headers["X-API-Key"] = os.environ["WORLDPOP_API_KEY"]
    async def run():
        async with httpx.AsyncClient(timeout=httpx.Timeout(15), headers=headers) as client:
            return await collect(args.year, args.resolution, args.cache_dir, client)
    report = asyncio.run(run())
    report["database_status"] = "not_attempted"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.import_db:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            parser.error("DATABASE_URL is required for --import-db; API results remain cached")
        rows = [{"zone_id": item["zone_id"], "population_estimate": item["population_estimate"],
                 "provenance": {"population": {key: value for key, value in item.items() if key != "population_estimate"}}}
                for item in report["records"]]
        report["database_rows_upserted"] = upsert_metrics(rows, database_url, args.dataset_version)
        report["database_status"] = "committed"
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("zones_covered", "zones_missing", "errors", "database_status")}))


if __name__ == "__main__":
    main()
