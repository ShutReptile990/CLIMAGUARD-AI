"""Import sourced DEM and population rasters into zone-level PostGIS metrics.

Population raster values must represent people per pixel, not density. No
values are generated when a cell has no raster coverage.
"""

import argparse
import csv
import json
import os
from pathlib import Path


def raster_values(dataset, geometry: dict):
    from rasterio.mask import mask
    from rasterio.warp import transform_geom
    if dataset.crs is None:
        raise ValueError("Raster CRS is missing")
    shape = transform_geom("EPSG:4326", dataset.crs, geometry)
    try:
        pixels, _ = mask(dataset, [shape], crop=True, filled=False, all_touched=False)
    except ValueError:
        return None
    valid = pixels[0].compressed()
    return valid if valid.size else None


def load_attributes(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {row["zone_slug"]: row for row in rows}


def compute_metrics(zones: list[dict], dem_path: Path | None, population_path: Path | None, attributes: dict[str, dict], slope_path: Path | None = None) -> list[dict]:
    import rasterio
    from contextlib import ExitStack
    result = []
    with ExitStack() as stack:
        dem = stack.enter_context(rasterio.open(dem_path)) if dem_path else None
        slope = stack.enter_context(rasterio.open(slope_path)) if slope_path else None
        population = stack.enter_context(rasterio.open(population_path)) if population_path else None
        for zone in zones:
            geom = zone["geometry"]
            dem_pixels = raster_values(dem, geom) if dem else None
            slope_pixels = raster_values(slope, geom) if slope else None
            population_pixels = raster_values(population, geom) if population else None
            attrs = attributes.get(zone["slug"], {})
            row = {"zone_id": zone["id"], "zone_slug": zone["slug"], "dem_mean_m": round(float(dem_pixels.mean()), 2) if dem_pixels is not None else None, "slope_mean_degrees": round(float(slope_pixels.mean()), 3) if slope_pixels is not None else None, "population_estimate": round(float(population_pixels.sum())) if population_pixels is not None else None, "drainage_index": float(attrs["drainage_index"]) if attrs.get("drainage_index") else None, "historical_flood_exposure": float(attrs["historical_flood_exposure"]) if attrs.get("historical_flood_exposure") else None, "vulnerability_index": float(attrs["vulnerability_index"]) if attrs.get("vulnerability_index") else None}
            if any(row[key] is not None for key in ("dem_mean_m", "slope_mean_degrees", "population_estimate", "drainage_index", "historical_flood_exposure", "vulnerability_index")):
                result.append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description="Compute sourced zone metrics from local rasters and optional CSV")
    parser.add_argument("--dem", type=Path)
    parser.add_argument("--slope", type=Path, help="Sourced slope raster in degrees (0–90)")
    parser.add_argument("--population", type=Path)
    parser.add_argument("--attributes-csv", type=Path)
    parser.add_argument("--metadata", type=Path, required=True, help="JSON with dataset_version and source/licence/units/processing provenance")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not any((args.dem, args.slope, args.population, args.attributes_csv)):
        parser.error("Provide at least one dataset")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    if not metadata.get("dataset_version") or not metadata.get("sources"):
        parser.error("Metadata must contain dataset_version and sources")
    if args.population and metadata.get("population_unit") != "people_per_pixel":
        parser.error("Population raster must be documented as people_per_pixel")
    if args.slope and metadata.get("slope_unit") != "degrees":
        parser.error("Slope raster must be documented in degrees")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required to read PostGIS analysis zones")
    import psycopg
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select id,slug,st_asgeojson(boundary)::jsonb from public.zones
                where metadata->>'kind' = 'analysis_grid' and boundary is not null order by slug""")
            zones = [{"id": row[0], "slug": row[1], "geometry": row[2]} for row in cursor.fetchall()]
            metrics = compute_metrics(zones, args.dem, args.population, load_attributes(args.attributes_csv), args.slope)
            if args.dry_run:
                print(json.dumps({"zones_with_data": len(metrics), "metrics": metrics}, default=str, indent=2))
                return
            for item in metrics:
                cursor.execute("""insert into public.zone_dataset_metrics
                    (zone_id,dataset_version,dem_mean_m,slope_mean_degrees,population_estimate,drainage_index,historical_flood_exposure,vulnerability_index,provenance)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    on conflict (zone_id,dataset_version) do update set dem_mean_m=excluded.dem_mean_m,
                    slope_mean_degrees=excluded.slope_mean_degrees,vulnerability_index=excluded.vulnerability_index,
                    population_estimate=excluded.population_estimate,drainage_index=excluded.drainage_index,
                    historical_flood_exposure=excluded.historical_flood_exposure,provenance=excluded.provenance,
                    computed_at=now()""", (item["zone_id"], metadata["dataset_version"], item["dem_mean_m"], item["slope_mean_degrees"], item["population_estimate"], item["drainage_index"], item["historical_flood_exposure"], item["vulnerability_index"], json.dumps(metadata)))
        connection.commit()
    print(f"Stored sourced metrics for {len(metrics)} zones")


if __name__ == "__main__":
    main()
