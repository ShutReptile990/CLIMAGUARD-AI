"""Reproducible WGS84 analysis grid for the Pune pilot, not official wards."""

from dataclasses import dataclass
from uuid import UUID, uuid5

GRID_VERSION = "pune-core-grid-v1"
GRID_NAMESPACE = UUID("b5574ec3-7af0-4e3d-b1d9-826d6e55c96d")
# Chosen pilot extent around the existing Pune localities. It is an analysis box,
# not a municipal boundary. Rows run south to north; columns west to east.
SOUTH, NORTH, WEST, EAST, ROWS, COLS = 18.45, 18.60, 73.77, 73.96, 3, 3
LEGACY_CENTERS = {
    "pune": (18.5204, 73.8567),
    "shivajinagar": (18.5308, 73.8475),
    "kothrud": (18.5074, 73.8077),
    "hadapsar": (18.4967, 73.9414),
}


@dataclass(frozen=True)
class GridZone:
    id: UUID
    slug: str
    name: str
    centroid: tuple[float, float]  # latitude, longitude
    geometry: dict
    metadata: dict

    def feature(self) -> dict:
        return {"type": "Feature", "id": self.slug, "properties": {"id": str(self.id), "slug": self.slug, "name": self.name, "centroid": list(self.centroid), **self.metadata}, "geometry": self.geometry}


def grid_zones() -> list[GridZone]:
    result = []
    lat_step, lng_step = (NORTH - SOUTH) / ROWS, (EAST - WEST) / COLS
    for row in range(ROWS):
        for col in range(COLS):
            south, north = SOUTH + row * lat_step, SOUTH + (row + 1) * lat_step
            west, east = WEST + col * lng_step, WEST + (col + 1) * lng_step
            slug = f"pune-grid-r{row + 1}-c{col + 1}"
            ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
            result.append(GridZone(id=uuid5(GRID_NAMESPACE, slug), slug=slug, name=f"Pune grid {chr(65 + row)}{col + 1}", centroid=((south + north) / 2, (west + east) / 2), geometry={"type": "Polygon", "coordinates": [ring]}, metadata={"kind": "analysis_grid", "grid_version": GRID_VERSION, "city": "Pune", "official_boundary": False, "bounds": [west, south, east, north]}))
    return result


def find_zone(slug: str) -> GridZone | None:
    return next((zone for zone in grid_zones() if zone.slug == slug), None)


def coordinates_for(slug: str) -> tuple[float, float] | None:
    zone = find_zone(slug)
    return zone.centroid if zone else LEGACY_CENTERS.get(slug)
