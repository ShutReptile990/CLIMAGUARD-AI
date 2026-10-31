"""Offline geometry checks; production exposure queries use PostGIS migration 004."""

import geopandas as gpd
from shapely.geometry import shape


def intersect_mapped_assets(zone_geojson: dict, facilities: list[dict], roads: list[dict]) -> dict:
    """Count OSM features co-located with a cell; never infer physical damage."""
    zone = shape(zone_geojson)
    if not zone.is_valid or zone.is_empty:
        raise ValueError("Invalid zone geometry")
    facility_rows = [{"kind": feature["properties"]["kind"], "geometry": shape(feature["geometry"])} for feature in facilities]
    road_rows = [{"geometry": shape(feature["geometry"])} for feature in roads]
    facility_frame = gpd.GeoDataFrame(facility_rows, geometry="geometry", crs="EPSG:4326") if facility_rows else None
    road_frame = gpd.GeoDataFrame(road_rows, geometry="geometry", crs="EPSG:4326") if road_rows else None
    counts = {"hospital": 0, "school": 0, "emergency": 0}
    if facility_frame is not None:
        for _, row in facility_frame[facility_frame.intersects(zone)].iterrows():
            key = row["kind"] if row["kind"] in ("hospital", "school") else "emergency"
            counts[key] += 1
    road_km = 0.0
    if road_frame is not None:
        clipped = road_frame.geometry.intersection(zone)
        road_km = float(gpd.GeoSeries(clipped, crs="EPSG:4326").to_crs("EPSG:32643").length.sum() / 1000)
    return {"mapped_hospitals": counts["hospital"], "mapped_schools": counts["school"], "mapped_emergency_services": counts["emergency"], "road_length_km": round(road_km, 3), "method": "GeoPandas/Shapely cell intersection; UTM 43N road length", "physical_damage_inferred": False}
