"""Controlled, manual OSM ingest. Never called by map requests."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import httpx

BBOX = (18.45, 73.77, 18.60, 73.96)  # south, west, north, east
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FACILITY_QUERY = f'''[out:json][timeout:90];(
  nwr["amenity"~"^(hospital|school|fire_station|police)$"]{BBOX};
  nwr["emergency"="ambulance_station"]{BBOX};
  nwr["emergency"="shelter"]{BBOX};
);out center tags;'''
ROAD_QUERY = f'''[out:json][timeout:90];(
  way["highway"~"^(primary|secondary|tertiary)$"]{BBOX};
);out geom tags;'''


def kind_from_tags(tags: dict) -> str | None:
    if tags.get("emergency") == "shelter":
        return "mapped_shelter"
    if tags.get("emergency") == "ambulance_station":
        return "ambulance_station"
    if tags.get("amenity") in {"hospital", "school", "fire_station", "police"}:
        return tags["amenity"]
    return None


def normalize_facilities(payload: dict) -> list[dict]:
    features, seen = [], set()
    for element in payload.get("elements", []):
        osm_type, osm_id, tags = element.get("type"), element.get("id"), element.get("tags", {})
        kind = kind_from_tags(tags)
        center = element.get("center", element)
        lat, lng = center.get("lat"), center.get("lon")
        if osm_type not in {"node", "way", "relation"} or not isinstance(osm_id, int) or not kind or not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)) or not tags.get("name"):
            continue
        if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lng <= BBOX[3]) or (osm_type, osm_id) in seen:
            continue
        seen.add((osm_type, osm_id))
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": {"osm_type": osm_type, "osm_id": osm_id, "name": tags["name"], "kind": kind, "source": "OpenStreetMap", "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}", "verified": False, "tags": tags}})
    return features


def normalize_roads(payload: dict) -> list[dict]:
    features = []
    for element in payload.get("elements", []):
        tags, points = element.get("tags", {}), element.get("geometry", [])
        coords = [[point["lon"], point["lat"]] for point in points if "lat" in point and "lon" in point]
        if element.get("type") != "way" or tags.get("highway") not in {"primary", "secondary", "tertiary"} or len(coords) < 2:
            continue
        features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords}, "properties": {"osm_type": "way", "osm_id": element["id"], "name": tags.get("name"), "highway_class": tags["highway"], "source": "OpenStreetMap", "tags": tags}})
    return features


def fetch(query: str, endpoint: str = OVERPASS_URL) -> dict:
    with httpx.Client(timeout=httpx.Timeout(100.0), headers={"User-Agent": "CLIMAGUARD-AI/0.3 (manual Pune OSM import; contact project maintainer)"}) as client:
        response = client.post(endpoint, data={"data": query})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
            raise ValueError("Invalid Overpass response")
        return payload


def import_database(facilities: list[dict], roads: list[dict], database_url: str, provenance: dict | None = None) -> None:
    import psycopg  # optional: install requirements-geo.txt
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for feature in facilities:
                props, (lng, lat) = feature["properties"], feature["geometry"]["coordinates"]
                cursor.execute("""insert into public.infrastructure(name,kind,location,source,osm_type,osm_id,osm_tags)
                    values (%s,%s,st_setsrid(st_makepoint(%s,%s),4326),'OpenStreetMap',%s,%s,%s::jsonb)
                    on conflict (osm_type,osm_id) where osm_type is not null do nothing""",
                    (props["name"], props["kind"], lng, lat, props["osm_type"], props["osm_id"], json.dumps(props["tags"])))
            for feature in roads:
                props = feature["properties"]
                cursor.execute("""insert into public.osm_roads(osm_type,osm_id,name,highway_class,geometry,osm_tags)
                    values (%s,%s,%s,%s,st_setsrid(st_geomfromgeojson(%s),4326),%s::jsonb)
                    on conflict (osm_type,osm_id) do nothing""",
                    (props["osm_type"], props["osm_id"], props["name"], props["highway_class"], json.dumps(feature["geometry"]), json.dumps(props["tags"])))
            cursor.execute("""insert into public.osm_import_runs(facility_count,road_count,provenance)
                values (%s,%s,%s::jsonb)""", (len(facilities), len(roads), json.dumps(provenance or {})))
        connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch one controlled Pune OSM snapshot and optionally import it into PostGIS")
    parser.add_argument("--fetch", action="store_true", help="Make one facilities and one roads Overpass request")
    parser.add_argument("--input", type=Path, help="Use a saved normalized snapshot")
    parser.add_argument("--output", type=Path, default=Path("data/osm_pune_snapshot.json"))
    parser.add_argument("--import-db", action="store_true", help="Import into DATABASE_URL after migration 003")
    parser.add_argument("--overpass-url", default=OVERPASS_URL, help="Overpass interpreter endpoint used only with --fetch")
    args = parser.parse_args()
    if args.fetch:
        facilities = normalize_facilities(fetch(FACILITY_QUERY, args.overpass_url))
        roads = normalize_roads(fetch(ROAD_QUERY, args.overpass_url))
        snapshot = {"type": "FeatureCollection", "metadata": {"source": "OpenStreetMap via Overpass", "endpoint": args.overpass_url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "bbox": BBOX, "license": "ODbL", "officially_verified": False}, "features": facilities, "roads": roads}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        print(f"Saved {len(facilities)} mapped facilities and {len(roads)} road segments to {args.output}")
    elif args.input:
        snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        parser.error("Choose --fetch or --input")
    if args.import_db:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            parser.error("DATABASE_URL is required for --import-db")
        import_database(snapshot["features"], snapshot["roads"], database_url, snapshot.get("metadata"))
        print("Imported OSM records into PostGIS")


if __name__ == "__main__":
    main()
