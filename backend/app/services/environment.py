import asyncio
import logging
from datetime import datetime, timezone
from fastapi import Request
from app.integrations.supabase import SupabaseGateway
from app.schemas.environment import EnvironmentBundle, StreamError, WeatherData, AirQuality, HistoricalData
from app.services.open_meteo import OpenMeteo, ProviderUnavailable
from app.services.zones import coordinates_for
from pydantic import ValidationError


class EnvironmentService:
    def __init__(self, provider: OpenMeteo, database: SupabaseGateway):
        self.provider = provider
        self.database = database
        self.persisted: set[str] = set()

    async def _capture(self, task, label: str):
        try:
            return await task
        except (ProviderUnavailable, ValidationError, KeyError, TypeError, ValueError) as exc:
            logging.getLogger("climaguard.environment").warning("stream=%s unavailable reason=%s", label, type(exc).__name__)
            return StreamError(detail=f"{label} is unavailable from Open-Meteo.")

    async def bundle(self, zone_id: str, include_history: bool = True) -> EnvironmentBundle:
        coords = coordinates_for(zone_id)
        if coords is None:
            from fastapi import HTTPException
            raise HTTPException(404, "Unknown Pune analysis zone or locality.")
        lat, lng = coords
        weather_task = self._capture(self.provider.weather(lat, lng), "Weather")
        air_task = self._capture(self.provider.air(lat, lng), "Air quality")
        history_task = self._capture(self.provider.history(lat, lng), "Historical reanalysis") if include_history else asyncio.sleep(0, result=StreamError(detail="History not requested."))
        weather, air, history = await asyncio.gather(weather_task, air_task, history_task)
        persistence = await self.persist(zone_id, weather, air)
        return EnvironmentBundle(zone_id=zone_id, coordinate=coords, weather=weather, air_quality=air, history=history, persistence=persistence, retrieved_at=datetime.now(timezone.utc))

    async def persist(self, slug: str, weather: WeatherData | StreamError, air: AirQuality | StreamError) -> str:
        if not (self.database.settings.configured and self.database.settings.supabase_secret_key):
            return "not_configured"
        if isinstance(weather, StreamError) and isinstance(air, StreamError):
            return "not_configured"
        try:
            rows = await self.database.table("zones", privileged=True, params={"select": "id", "slug": f"eq.{slug}", "limit": 1})
            if not isinstance(rows, list) or not rows:
                return "failed"
            zone_uuid = rows[0]["id"]
            if isinstance(weather, WeatherData):
                current = weather.current
                key = f"weather:{slug}:{current.valid_at.isoformat()}"
                if key not in self.persisted:
                    await self.database.table("climate_observations", "POST", privileged=True, params={"on_conflict": "zone_id,observed_at,source"}, json={"zone_id": zone_uuid, "observed_at": current.valid_at.isoformat(), "temperature_c": current.temperature_c, "humidity_percent": current.humidity_percent, "rainfall_mm": current.precipitation_mm, "source": current.source, "data_kind": current.kind}, prefer="resolution=merge-duplicates,return=minimal")
                    self.persisted.add(key)
            if isinstance(air, AirQuality):
                key = f"air:{slug}:{air.valid_at.isoformat()}"
                if key not in self.persisted:
                    await self.database.table("air_quality_observations", "POST", privileged=True, params={"on_conflict": "zone_id,valid_at,source"}, json={"zone_id": zone_uuid, "valid_at": air.valid_at.isoformat(), "us_aqi": air.us_aqi, "pm2_5": air.pm2_5, "pm10": air.pm10, "nitrogen_dioxide": air.nitrogen_dioxide, "ozone": air.ozone, "sulphur_dioxide": air.sulphur_dioxide, "carbon_monoxide": air.carbon_monoxide, "source": air.source, "data_kind": air.kind}, prefer="resolution=merge-duplicates,return=minimal")
                    self.persisted.add(key)
            return "stored"
        except Exception as exc:
            logging.getLogger("climaguard.environment").warning("persistence_failed type=%s", type(exc).__name__)
            return "failed"


def get_environment_service(request: Request) -> EnvironmentService:
    return request.app.state.environment
