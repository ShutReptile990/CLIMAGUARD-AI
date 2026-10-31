"""Validated, source-preserving raster statistics for the Pune analysis grid."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import math

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_geom
from shapely.geometry import mapping, shape


def inspect_raster(path: Path, *, kind: str, declared_unit: str | None = None) -> dict:
    """Reject mislabeled files and ambiguous units before any zonal calculation."""
    with path.open("rb") as stream:
        if stream.read(4) not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
            raise ValueError(f"{path.name} is not a GeoTIFF (TIFF signature missing)")
    with rasterio.open(path) as ds:
        if ds.driver != "GTiff" or ds.count != 1 or ds.crs is None or ds.transform.is_identity:
            raise ValueError(f"{path.name}: require a georeferenced, single-band GeoTIFF")
        if ds.width * ds.height > 50_000_000:
            raise ValueError(f"{path.name}: clip the raster to Pune before import (over 50 million cells)")
        all_valid_unmasked = ds.nodata is None and all(flag.name == "all_valid" for flag in ds.mask_flag_enums[0])
        if all_valid_unmasked:
            # A DEM without a NoData marker can be complete, but every pixel must
            # be finite. Its provenance records this limitation for review.
            if kind != "dem" or any(not np.isfinite(ds.read(1, window=window)).all()
                                    for _, window in ds.block_windows(1)):
                raise ValueError(f"{path.name}: NoData or a valid-data mask is required")
        if ds.nodata is not None and not math.isfinite(ds.nodata):
            raise ValueError(f"{path.name}: NoData must be finite")
        embedded_unit = ds.units[0] or ds.tags(1).get("UNITTYPE") or ds.tags().get("UNITTYPE")
        unit = embedded_unit or declared_unit
        accepted = ("m", "metre", "meter", "metres", "meters") if kind == "dem" else ("people_per_pixel",)
        if not unit or unit.lower() not in accepted:
            raise ValueError(f"{path.name}: {kind} units must be declared as {'metres' if kind == 'dem' else 'people_per_pixel'}")
        if declared_unit and unit.lower() != declared_unit.lower() and not (kind == "dem" and unit.lower() in accepted and declared_unit.lower() in accepted):
            raise ValueError(f"{path.name}: declared unit conflicts with raster unit")
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"file": str(path.resolve()), "sha256": digest.hexdigest(), "crs": ds.crs.to_string(), "units": unit,
                "nodata": ds.nodata, "resolution": list(ds.res), "bounds": list(ds.bounds), "tags": ds.tags(),
                "band_tags": ds.tags(1), "valid_mask": [str(flag) for flag in ds.mask_flag_enums[0]],
                "unit_basis": "embedded_raster" if embedded_unit else "declared_metadata",
                "nodata_validation": "all_pixels_finite_no_nodata_marker" if all_valid_unmasked else "raster_nodata_or_mask",
                "inspected_at_utc": datetime.now(timezone.utc).isoformat()}


def _zone_masks(ds, zones: list[dict]) -> list[np.ndarray]:
    masks = []
    claimed = np.zeros((ds.height, ds.width), dtype=bool)
    polygons = [shape(zone["geometry"]) for zone in zones]
    if any(not p.is_valid or p.is_empty for p in polygons):
        raise ValueError("Analysis zone geometry is invalid")
    for i, polygon in enumerate(polygons):
        if any(polygon.intersection(other).area > 1e-12 for other in polygons[:i]):
            raise ValueError("Analysis zones overlap; population sums would double-count")
        projected = transform_geom("EPSG:4326", ds.crs, zones[i]["geometry"])
        mask = geometry_mask([projected], out_shape=(ds.height, ds.width), transform=ds.transform, invert=True, all_touched=False)
        mask &= ~claimed
        claimed |= mask
        masks.append(mask)
    return masks


def _mean_slope(dem, zone_masks: list[np.ndarray]) -> list[float | None]:
    """Compute rise/run in metric UTM 43N, then reproject slope to DEM cells."""
    dst_crs = "EPSG:32643"
    transform, width, height = calculate_default_transform(dem.crs, dst_crs, dem.width, dem.height, *dem.bounds, resolution=30)
    if width * height > 25_000_000:
        raise ValueError("DEM too large for in-memory slope calculation; clip it to Pune first")
    source = dem.read(1, masked=True).astype("float32")
    projected = np.full((height, width), np.nan, dtype="float32")
    reproject(source.filled(np.nan), projected, src_transform=dem.transform, src_crs=dem.crs,
              dst_transform=transform, dst_crs=dst_crs, src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.bilinear)
    filled = np.nan_to_num(projected, nan=0.0)
    valid = np.isfinite(projected)
    padded = np.pad(valid, 1, constant_values=False)
    neighbors = np.logical_and.reduce([padded[1+dy:1+dy+height, 1+dx:1+dx+width] for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
    gy, gx = np.gradient(filled, abs(transform.e), abs(transform.a))
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    slope[~neighbors] = np.nan
    back = np.full((dem.height, dem.width), np.nan, dtype="float32")
    reproject(slope, back, src_transform=transform, src_crs=dst_crs, dst_transform=dem.transform,
              dst_crs=dem.crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return [round(float(np.nanmean(back[mask])), 3) if np.isfinite(back[mask]).any() else None for mask in zone_masks]


def zonal_raster_metrics(path: Path, zones: list[dict], *, kind: str, slope: bool = False) -> list[dict]:
    with rasterio.open(path) as ds:
        values = ds.read(1, masked=True)
        masks = _zone_masks(ds, zones)
        slopes = _mean_slope(ds, masks) if kind == "dem" and slope else [None] * len(zones)
        results = []
        for mask, slope_mean in zip(masks, slopes):
            selected = values[mask].compressed()
            selected = selected[np.isfinite(selected)]
            if kind == "population" and (selected < 0).any():
                raise ValueError("Population raster contains negative valid counts")
            results.append({"coverage_pixels": int(selected.size),
                            "mean_m": round(float(selected.mean()), 2) if kind == "dem" and selected.size else None,
                            "min_m": round(float(selected.min()), 2) if kind == "dem" and selected.size else None,
                            "max_m": round(float(selected.max()), 2) if kind == "dem" and selected.size else None,
                            "slope_mean_degrees": slope_mean,
                            "population_estimate": round(float(selected.sum())) if kind == "population" and selected.size else None})
        return results


def potential_population_exposure(path: Path | None, zone_geometry: dict, hazard_geometry: dict | None,
                                  *, declared_unit: str = "people_per_pixel") -> int | None:
    """Count covered population pixels only inside a sourced hazard footprint."""
    if path is None or hazard_geometry is None:
        return None
    inspect_raster(path, kind="population", declared_unit=declared_unit)
    zone, hazard = shape(zone_geometry), shape(hazard_geometry)
    if not zone.is_valid or not hazard.is_valid or zone.is_empty or hazard.is_empty:
        raise ValueError("Zone or hazard exposure geometry is invalid")
    overlap = zone.intersection(hazard)
    if overlap.is_empty:
        return 0
    with rasterio.open(path) as ds:
        projected = transform_geom("EPSG:4326", ds.crs, mapping(overlap))
        mask = geometry_mask([projected], out_shape=(ds.height, ds.width), transform=ds.transform,
                             invert=True, all_touched=False)
        pixels = ds.read(1, masked=True)[mask].compressed()
        pixels = pixels[np.isfinite(pixels)]
        if not pixels.size:
            return None
        if (pixels < 0).any():
            raise ValueError("Population raster contains negative valid counts")
        return round(float(pixels.sum()))
