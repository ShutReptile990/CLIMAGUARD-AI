"""DEMO raster and provider fixtures; no synthetic values are served as live data."""

import asyncio
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from app.services.zone_rasters import inspect_raster, potential_population_exposure, zonal_raster_metrics
from app.services.local_population import local_population_context
from app.services.zones import grid_zones
from scripts.import_pune_terrain_population import build_report, import_dem_supabase, validate_dem_import_metadata
from scripts.import_worldpop import collect
from scripts.persist_worldpop_supabase import DATASET_VERSION, persist


def zone_records():
    return [{"id": str(z.id), "slug": z.slug, "geometry": z.geometry} for z in grid_zones()]


def write_demo_tiff(path: Path, values: np.ndarray, *, unit: str):
    with rasterio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                       dtype="float32", crs="EPSG:4326", transform=from_bounds(73.77, 18.45, 73.96, 18.60,
                                                                                values.shape[1], values.shape[0]),
                       nodata=-9999) as ds:
        ds.write(values.astype("float32"), 1)
        ds.update_tags(1, UNITTYPE=unit)


def test_invalid_raster_files_are_rejected_without_invented_coverage(tmp_path):
    dem_path = tmp_path / "invalid_dem.tif"
    population_path = tmp_path / "invalid_population.tif"
    dem_path.write_text("not a GeoTIFF", encoding="utf-8")
    population_path.write_text("not a GeoTIFF", encoding="utf-8")
    report = build_report(dem_path, population_path,
                          {"dataset_version": "validation-only", "sources": {"dem": "unverified", "population": "unverified"},
                           "elevation_unit": "metres", "population_unit": "people_per_pixel", "population_year": 2025,
                           "population_resolution": "100m"})
    assert report["status"] == "invalid_sources"
    assert report["dem_zones_covered"] == report["population_zones_covered"] == 0
    assert len(report["errors"]) == 2


def test_complete_dem_without_nodata_requires_declared_units_and_source_metadata(tmp_path):
    dem_path = tmp_path / "demo_complete_dem.tif"
    with rasterio.open(dem_path, "w", driver="GTiff", width=90, height=90, count=1,
                       dtype="float32", crs="EPSG:4326", transform=from_bounds(73.77, 18.45, 73.96, 18.60, 90, 90)) as ds:
        ds.write(np.full((90, 90), 550, dtype="float32"), 1)
    provenance = inspect_raster(dem_path, kind="dem", declared_unit="metres")
    assert provenance["nodata_validation"] == "all_pixels_finite_no_nodata_marker"
    assert provenance["unit_basis"] == "declared_metadata"
    report = build_report(dem_path, None, {"dataset_version": "DEMO", "sources": {"dem": "Replace with citation"},
                                           "elevation_unit": "metres"})
    assert report["status"] == "requires_source_metadata"
    assert report["dem_zones_covered"] == report["slope_zones_covered"] == 9


def test_dem_import_requires_actual_product_metadata():
    metadata = {"sources": {"dem": "Replace with citation"}, "dem_source": "Replace with product",
                "dem_licence": "Replace with licence", "retrieved_at_utc": None}
    with pytest.raises(ValueError, match="dem_source"):
        validate_dem_import_metadata(metadata)
    metadata.update({"sources": {"dem": "DEMO Copernicus product citation"},
                     "dem_source": "DEMO Copernicus DEM", "dem_licence": "DEMO licence",
                     "retrieved_at_utc": "2026-10-30T10:00:00Z"})
    validate_dem_import_metadata(metadata)


def test_supabase_dem_import_preserves_population_and_drainage_and_is_idempotent():
    zones = zone_records()
    report = {"status": "validated", "dataset_version": "DEMO-version", "dem_zones_covered": 9,
              "slope_zones_covered": 9, "sources": {"dem": {"sha256": "DEMO-hash", "file": "DEMO.tif",
                                                         "source": "DEMO source"}},
              "zones": [{"zone_id": zone["id"], "zone_slug": zone["slug"], "dem_mean_m": 550,
                         "slope_mean_degrees": 3.5} for zone in zones]}

    class Gateway:
        def __init__(self):
            self.rows = [{"id": str(i), "zone_id": zone["id"], "dataset_version": "DEMO-version",
                          "population_estimate": 1000 + i, "dem_mean_m": None, "slope_mean_degrees": None,
                          "mapped_drain_distance_m": 200 + i,
                          "provenance": {"population": {"source": "DEMO WorldPop"}}}
                         for i, zone in enumerate(zones)]

        async def table(self, table, method="GET", **kwargs):
            if table == "zones":
                return [{"id": zone["id"], "slug": zone["slug"]} for zone in zones]
            if method == "PATCH":
                row = next(row for row in self.rows if row["id"] == kwargs["params"]["id"][3:])
                row.update(kwargs["json"])
                return None
            return self.rows

    async def run():
        gateway = Gateway()
        first = await import_dem_supabase(report, gateway)
        second = await import_dem_supabase(report, gateway)
        assert first["database_rows_upserted"] == 9 and first["database_rows_verified"] == 9
        assert second["database_rows_upserted"] == 0
        assert [row["population_estimate"] for row in gateway.rows] == [1000 + i for i in range(9)]
        assert [row["mapped_drain_distance_m"] for row in gateway.rows] == [200 + i for i in range(9)]
        assert all(row["provenance"]["dem"]["sha256"] == "DEMO-hash" for row in gateway.rows)
    asyncio.run(run())


def test_raster_zonal_counts_slope_and_nodata(tmp_path):
    dem_path, pop_path = tmp_path / "demo_dem.tif", tmp_path / "demo_population.tif"
    dem = np.full((90, 90), 550, dtype="float32")
    dem[:, 45:] += 10
    pop = np.ones((90, 90), dtype="float32")
    pop[:30, :30] = -9999
    write_demo_tiff(dem_path, dem, unit="metres")
    write_demo_tiff(pop_path, pop, unit="people_per_pixel")
    assert inspect_raster(dem_path, kind="dem")["crs"] == "EPSG:4326"
    dem_rows = zonal_raster_metrics(dem_path, zone_records(), kind="dem", slope=True)
    pop_rows = zonal_raster_metrics(pop_path, zone_records(), kind="population")
    assert len(dem_rows) == len(pop_rows) == 9
    assert all(row["mean_m"] is not None for row in dem_rows)
    assert any(row["slope_mean_degrees"] is not None for row in dem_rows)
    assert pop_rows[6]["population_estimate"] is None
    assert sum(row["population_estimate"] or 0 for row in pop_rows) == 7200


def test_population_unit_validation_and_zone_overlap(tmp_path):
    path = tmp_path / "demo.tif"
    write_demo_tiff(path, np.ones((9, 9)), unit="people_per_pixel")
    with pytest.raises(ValueError, match="units"):
        inspect_raster(path, kind="dem")
    duplicate = zone_records()[:1] * 2
    with pytest.raises(ValueError, match="overlap"):
        zonal_raster_metrics(path, duplicate, kind="population")


def test_potential_exposure_requires_footprint_and_population_coverage(tmp_path):
    path = tmp_path / "demo_population.tif"
    write_demo_tiff(path, np.ones((90, 90)), unit="people_per_pixel")
    zone = zone_records()[0]["geometry"]
    assert potential_population_exposure(path, zone, None) is None
    assert potential_population_exposure(None, zone, zone) is None
    assert potential_population_exposure(path, zone, zone) == 900


def test_worldpop_api_task_result_is_cached(tmp_path):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/population"):
            assert request.method == "POST"
            return httpx.Response(200, json={"task_id": "DEMO-task"})
        return httpx.Response(200, json={"status": "success", "result": {"total_population": 1234.4, "data_year": 2025}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            first = await collect(2025, "100m", tmp_path, client)
            second = await collect(2025, "100m", tmp_path, client)
            return first, second
    first, second = asyncio.run(run())
    assert first["zones_covered"] == second["zones_covered"] == 9
    assert len(calls) == 18
    assert first["records"][0]["population_estimate"] == 1234
    assert first["records"][0]["source"] == "WorldPop Global2 API v2"


def test_real_worldpop_cache_covers_disjoint_grid_and_labels_preview():
    context = local_population_context()
    assert set(context) == {zone.slug for zone in grid_zones()}
    assert all(row["population_estimate"] >= 0 for row in context.values())
    assert all(row["provenance"]["population"]["storage"] == "local_api_cache_preview" for row in context.values())


def test_worldpop_supabase_import_does_not_duplicate_or_replace_estimates():
    estimates = local_population_context()

    class Gateway:
        writes = 0

        async def table(self, table, method="GET", **kwargs):
            if method != "GET":
                self.writes += 1
                return None
            if table == "zones":
                return [{"id": str(zone.id), "slug": zone.slug} for zone in grid_zones()]
            return [{"zone_id": str(zone.id), "dataset_version": DATASET_VERSION,
                     "population_estimate": estimates[zone.slug]["population_estimate"], "provenance": {}}
                    for zone in grid_zones()]

    async def run():
        gateway = Gateway()
        result = await persist(gateway, write=True)
        assert result["already_present"] == 9 and result["inserted"] == 0
        assert gateway.writes == 0
    asyncio.run(run())
