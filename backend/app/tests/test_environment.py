"""DEMO provider payloads used only to verify normalization, never served as live data."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
import httpx
from app.services.open_meteo import OpenMeteo, ProviderUnavailable
from app.services.environment import EnvironmentService
from app.services.zones import grid_zones, find_zone
from app.api.geography import zone_geojson
from app.schemas.environment import StreamError
from scripts.ingest_osm import normalize_facilities, normalize_roads

DEMO_WEATHER = {
    "current": {"time": "2026-10-28T12:00", "temperature_2m": 31.0, "relative_humidity_2m": 58, "precipitation": 0.2},
    "current_units": {"temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm"},
    "hourly": {"time": ["2026-10-28T12:00", "2026-10-28T13:00"], "precipitation": [0.2, 1.0], "precipitation_probability": [20, 60]},
    "hourly_units": {"precipitation": "mm", "precipitation_probability": "%"},
    "daily": {"time": ["2026-10-28", "2026-10-29"], "temperature_2m_max": [33, 32], "temperature_2m_min": [24, 23], "precipitation_sum": [2.0, 5.0]},
    "daily_units": {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm"},
}
DEMO_AIR = {"current": {"time": "2026-10-28T12:00", "us_aqi": 72, "pm2_5": 18.2, "pm10": 32.1, "nitrogen_dioxide": 8.0, "ozone": 22.0, "sulphur_dioxide": 3.0, "carbon_monoxide": 280.0}, "current_units": {"us_aqi": "USAQI", "pm2_5": "μg/m³", "pm10": "μg/m³", "nitrogen_dioxide": "μg/m³", "ozone": "μg/m³", "sulphur_dioxide": "μg/m³", "carbon_monoxide": "μg/m³"}}
DEMO_HISTORY = {"daily": {"time": ["2026-09-26", "2026-09-27"], "precipitation_sum": [1.2, 3.4], "temperature_2m_mean": [25.0, 27.0]}, "daily_units": {"precipitation_sum": "mm", "temperature_2m_mean": "°C"}}


def test_provider_normalizes_units_times_and_caches():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        payload = DEMO_WEATHER if request.url.path.endswith("forecast") else DEMO_AIR if request.url.path.endswith("air-quality") else DEMO_HISTORY
        return httpx.Response(200, json=payload)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenMeteo(client)
            weather = await provider.weather(18.52, 73.85)
            air = await provider.air(18.52, 73.85)
            history = await provider.history(18.52, 73.85, today=datetime.fromisoformat("2026-10-28T12:00:00+05:30"))
            await provider.weather(18.52, 73.85)
            return weather, air, history
    weather, air, history = asyncio.run(run())
    assert len(calls) == 3
    assert weather.current.valid_at.utcoffset().total_seconds() == 19800
    assert weather.hourly[1].precipitation_probability_percent == 60
    assert air.units["pm2_5"] == "μg/m³"
    assert air.us_aqi == 72
    assert history.total_precipitation_mm == 4.6
    assert history.mean_temperature_c == 26.0


def test_past_days_are_not_mislabeled_as_daily_forecasts():
    payload = {**DEMO_WEATHER, "daily": {**DEMO_WEATHER["daily"], "time": ["2026-10-27", "2026-10-28", "2026-10-29"], "temperature_2m_max": [30, 33, 32], "temperature_2m_min": [23, 24, 23], "precipitation_sum": [1, 2, 5]}}
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
            return await OpenMeteo(client).weather(18.52, 73.85)
    weather = asyncio.run(run())
    assert [item.date.isoformat() for item in weather.daily] == ["2026-10-28", "2026-10-29"]


def test_provider_rejects_unexpected_units():
    payload = {**DEMO_AIR, "current_units": {**DEMO_AIR["current_units"], "us_aqi": "Indian AQI"}}
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
            return await OpenMeteo(client).air(18.52, 73.85)
    try:
        asyncio.run(run())
    except ProviderUnavailable:
        pass
    else:
        assert False, "Unexpected AQI scale must be rejected"


def test_grid_geojson_is_reproducible_and_closed():
    zones = grid_zones()
    assert len(zones) == 9
    assert len({zone.id for zone in zones}) == 9
    assert find_zone("pune-grid-r2-c2").centroid == zones[4].centroid
    assert all(zone.geometry["coordinates"][0][0] == zone.geometry["coordinates"][0][-1] for zone in zones)
    collection = asyncio.run(zone_geojson())
    assert collection["metadata"]["official_boundary"] is False
    assert len(collection["features"]) == 9


def test_persistence_upserts_selected_estimates_only_once():
    class FakeDatabase:
        settings = SimpleNamespace(configured=True, supabase_secret_key="server-only")
        calls = []
        async def table(self, table, method="GET", **kwargs):
            self.calls.append((table, method, kwargs))
            return [{"id": str(uuid4())}] if table == "zones" else None
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=DEMO_WEATHER if request.url.path.endswith("forecast") else DEMO_AIR))) as client:
            provider = OpenMeteo(client)
            weather = await provider.weather(18.52, 73.85)
            air = await provider.air(18.52, 73.85)
            database = FakeDatabase()
            service = EnvironmentService(provider, database)
            first = await service.persist("pune", weather, air)
            second = await service.persist("pune", weather, air)
            return first, second, database.calls
    first, second, calls = asyncio.run(run())
    assert first == second == "stored"
    assert [table for table, method, _ in calls if method == "POST"] == ["climate_observations", "air_quality_observations"]
    assert all(kwargs["privileged"] for table, method, kwargs in calls if method == "POST")


def test_provider_failure_has_no_live_reading():
    class FailedProvider:
        async def weather(self, *_): raise ProviderUnavailable("Forecast", "offline")
        async def air(self, *_): raise ProviderUnavailable("Air", "offline")
        async def history(self, *_): raise ProviderUnavailable("Archive", "offline")
    class NoDatabase:
        settings = SimpleNamespace(configured=False, supabase_secret_key=None)
    bundle = asyncio.run(EnvironmentService(FailedProvider(), NoDatabase()).bundle("pune"))
    assert isinstance(bundle.weather, StreamError)
    assert isinstance(bundle.air_quality, StreamError)
    assert isinstance(bundle.history, StreamError)
    assert bundle.persistence == "not_configured"


def test_osm_import_only_accepts_mapped_named_facilities_and_road_geometry():
    payload = {"elements": [
        {"type": "node", "id": 101, "lat": 18.52, "lon": 73.85, "tags": {"amenity": "hospital", "name": "DEMO mapped hospital"}},
        {"type": "node", "id": 102, "lat": 18.52, "lon": 73.85, "tags": {"emergency": "shelter"}},
        {"type": "node", "id": 103, "lat": 18.52, "lon": 73.85, "tags": {"name": "DEMO generic place"}},
    ]}
    features = normalize_facilities(payload)
    assert len(features) == 1
    assert features[0]["properties"]["kind"] == "hospital"
    assert features[0]["properties"]["verified"] is False
    roads = normalize_roads({"elements": [{"type": "way", "id": 201, "tags": {"highway": "primary", "name": "DEMO road"}, "geometry": [{"lat": 18.51, "lon": 73.84}, {"lat": 18.52, "lon": 73.85}]}]})
    assert roads[0]["geometry"]["type"] == "LineString"
