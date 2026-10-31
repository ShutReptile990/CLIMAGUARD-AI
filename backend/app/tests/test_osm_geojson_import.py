"""DEMO fixtures verify OSM import behavior; real source counts are reported by CLI."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from app.core.errors import ServiceUnavailable
from app.integrations.supabase import get_gateway
from app.main import app
from scripts.import_pune_infrastructure import import_database, parse_geojson


def feature(ref, properties, geometry):
    return {"type": "Feature", "id": ref, "properties": {"@id": ref, **properties}, "geometry": geometry}


def demo_source(path: Path):
    point = {"type": "Point", "coordinates": [73.85, 18.52]}
    polygon = {"type": "Polygon", "coordinates": [[[73.84, 18.51], [73.86, 18.51], [73.86, 18.53], [73.84, 18.53], [73.84, 18.51]]]}
    line = {"type": "LineString", "coordinates": [[73.84, 18.52], [73.86, 18.52]]}
    features = [
        feature("way/1", {"amenity": "hospital", "name": "DEMO hospital"}, polygon),
        feature("node/2", {"amenity": "school", "name": "DEMO school"}, point),
        feature("node/3", {"amenity": "fire_station", "name": "DEMO fire station"}, point),
        feature("way/4", {"highway": "primary", "name": "DEMO road"}, line),
        feature("way/4", {"highway": "primary", "name": "DEMO duplicate"}, line),
        feature("node/5", {"amenity": "hospital"}, point),
        feature("way/6", {"highway": "secondary", "name": "DEMO invalid road"}, polygon),
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "timestamp": "2026-10-29T00:00:00Z", "features": features}), encoding="utf-8")


def test_parser_classifies_preserves_footprint_and_reports_failures(tmp_path):
    path = tmp_path / "demo.geojson"
    demo_source(path)
    batch = parse_geojson(path)
    assert {item["kind"] for item in batch.facilities} == {"hospital", "school", "fire_station"}
    assert len(batch.roads) == 1
    assert batch.facilities[0]["geometry"]["type"] == "Polygon"
    assert batch.facilities[0]["marker"] == pytest.approx([73.85, 18.52])
    assert batch.duplicate_ids == ["way/4"]
    assert {item["reason"] for item in batch.failures} == {"facility_missing_source_name", "unsupported_road_geometry: Polygon"}
    assert all(item["source_url"].startswith("https://www.openstreetmap.org/") for item in batch.facilities)


def test_import_is_insert_only_and_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "demo.geojson"
    demo_source(path)
    batch = parse_geojson(path)
    stored = set()
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=None):
            statements.append(sql.lower())
            if "information_schema.columns" in sql:
                self.result = (3,)
            elif "to_regclass" in sql:
                self.result = ("osm_roads", "osm_import_runs")
            elif "insert into public.infrastructure" in sql:
                key = ("facility", params[5], params[6]); self.result = None if key in stored else ("new",); stored.add(key)
            elif "insert into public.osm_roads" in sql:
                key = ("road", params[0], params[1]); self.result = None if key in stored else ("new",); stored.add(key)
            else:
                self.result = None
        def fetchone(self): return self.result
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def cursor(self): return Cursor()
        def commit(self): pass
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda _: Connection()))
    first = import_database(batch, "DEMO database URL")
    second = import_database(batch, "DEMO database URL")
    assert (first["database_inserted_facilities"], first["database_inserted_roads"]) == (3, 1)
    assert (second["database_inserted_facilities"], second["database_inserted_roads"]) == (0, 0)
    assert second["database_existing_facilities"] == 3
    assert all("do nothing" in sql for sql in statements if "insert into public.infrastructure" in sql or "insert into public.osm_roads" in sql)
    assert not any(" update " in sql or " delete " in sql for sql in statements)


def test_map_api_uses_validated_local_preview_when_database_unconfigured():
    class NoDatabase:
        async def request(self, *_args, **_kwargs):
            raise ServiceUnavailable("not configured")
    app.dependency_overrides[get_gateway] = lambda: NoDatabase()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            facilities = await client.get("/api/map/infrastructure")
            roads = await client.get("/api/map/roads")
            invalid = await client.get("/api/map/roads?bbox=0,0,1,1")
            return facilities, roads, invalid
    try:
        facilities, roads, invalid = asyncio.run(run())
        assert facilities.status_code == 200 and roads.status_code == 200
        assert facilities.json()["storage"] == "local_geojson_preview"
        assert facilities.json()["counts"]["hospital"] > 0
        assert roads.json()["features"][0]["geometry"]["type"] == "LineString"
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
