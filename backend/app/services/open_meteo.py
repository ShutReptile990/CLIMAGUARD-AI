"""Open-Meteo normalization. Current values are model estimates, not station readings."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import httpx
from app.schemas.environment import AirQuality, AirHour, CurrentWeather, DailyForecast, HistoricalData, HistoricalDay, HourlyForecast, WeatherData

TZ = ZoneInfo("Asia/Kolkata")
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


class ProviderUnavailable(Exception):
    def __init__(self, provider: str, reason: str):
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider}: {reason}")


def local_time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    return value if value.tzinfo else value.replace(tzinfo=TZ)


def require_units(actual: dict, expected: dict[str, str], provider: str) -> None:
    for field, unit in expected.items():
        if actual.get(field) != unit:
            raise ProviderUnavailable(provider, f"Unexpected unit for {field}")


def aligned(data: dict, *fields: str) -> list[tuple]:
    times = data.get("time")
    if not isinstance(times, list) or any(not isinstance(data.get(field), list) or len(data[field]) != len(times) for field in fields):
        raise ProviderUnavailable("Open-Meteo", "Incomplete time series")
    return list(zip(times, *(data[field] for field in fields)))


class OpenMeteo:
    def __init__(self, client: httpx.AsyncClient | None = None, *, timeout_seconds: float = 8.0):
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds), headers={"User-Agent": "CLIMAGUARD-AI/0.3 (Pune climate data)"})
        self.owns_client = client is None
        self.cache: dict[str, tuple[float, dict | list]] = {}
        self.lock = asyncio.Lock()

    async def close(self):
        if self.owns_client:
            await self.client.aclose()

    async def _get(self, url: str, params: dict, ttl: int) -> dict | list:
        key = f"{url}?{urlencode(sorted(params.items()))}"
        now = time.monotonic()
        cached = self.cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        async with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            for attempt in range(3):
                try:
                    response = await self.client.get(url, params=params)
                    logging.getLogger("climaguard.provider").info("provider=open-meteo endpoint=%s status=%s", url.rsplit("/", 1)[-1], response.status_code)
                    if response.status_code in (429, 502, 503, 504) and attempt < 2:
                        await asyncio.sleep(0.25 * 2**attempt)
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, (dict, list)) or isinstance(payload, dict) and payload.get("error"):
                        raise ProviderUnavailable("Open-Meteo", str(payload.get("reason", "Invalid response")) if isinstance(payload, dict) else "Invalid response")
                    self.cache[key] = (time.monotonic() + ttl, payload)
                    return payload
                except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                    if attempt == 2 or isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (429, 502, 503, 504):
                        raise ProviderUnavailable("Open-Meteo", "Provider request failed") from exc
                    await asyncio.sleep(0.25 * 2**attempt)
        raise ProviderUnavailable("Open-Meteo", "Provider retry exhausted")

    async def weather(self, lat: float, lng: float) -> WeatherData:
        data = await self._get(FORECAST_URL, {"latitude": lat, "longitude": lng, "current": "temperature_2m,relative_humidity_2m,precipitation", "hourly": "precipitation,precipitation_probability", "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "past_days": 4, "forecast_days": 7, "timezone": "Asia/Kolkata"}, 600)
        if not isinstance(data, dict):
            raise ProviderUnavailable("Forecast API", "Unexpected response type")
        current, hourly, daily = data.get("current", {}), data.get("hourly", {}), data.get("daily", {})
        require_units(data.get("current_units", {}), {"temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm"}, "Forecast API")
        require_units(data.get("hourly_units", {}), {"precipitation": "mm", "precipitation_probability": "%"}, "Forecast API")
        require_units(data.get("daily_units", {}), {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm"}, "Forecast API")
        if not current.get("time"):
            raise ProviderUnavailable("Forecast API", "Missing current timestamp")
        hourly_rows = aligned(hourly, "precipitation", "precipitation_probability")
        daily_rows = aligned(daily, "temperature_2m_max", "temperature_2m_min", "precipitation_sum")
        current_date = local_time(current["time"]).date()
        return WeatherData(current=CurrentWeather(temperature_c=current.get("temperature_2m"), humidity_percent=current.get("relative_humidity_2m"), precipitation_mm=current.get("precipitation"), valid_at=local_time(current["time"]), units={"temperature_c": "°C", "humidity_percent": "%", "precipitation_mm": "mm"}), hourly=[HourlyForecast(valid_at=local_time(t), precipitation_mm=p, precipitation_probability_percent=prob) for t, p, prob in hourly_rows], daily=[DailyForecast(date=datetime.fromisoformat(t).date(), temperature_max_c=mx, temperature_min_c=mn, precipitation_sum_mm=p) for t, mx, mn, p in daily_rows if datetime.fromisoformat(t).date() >= current_date], timezone="Asia/Kolkata", units={"precipitation_mm": "mm", "precipitation_probability_percent": "%", "temperature_c": "°C"})

    async def air(self, lat: float, lng: float) -> AirQuality:
        data = await self._get(AIR_URL, {"latitude": lat, "longitude": lng, "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide", "hourly": "us_aqi,pm2_5,pm10", "past_days": 2, "forecast_days": 2, "timezone": "Asia/Kolkata"}, 1200)
        if not isinstance(data, dict):
            raise ProviderUnavailable("Air Quality API", "Unexpected response type")
        current = data.get("current", {})
        if not current.get("time"):
            raise ProviderUnavailable("Air Quality API", "Missing current timestamp")
        units = data.get("current_units", {})
        require_units(units, {"us_aqi": "USAQI", "pm2_5": "μg/m³", "pm10": "μg/m³"}, "Air Quality API")
        hourly = data.get("hourly", {})
        hourly_rows = aligned(hourly, "us_aqi", "pm2_5", "pm10") if hourly else []
        if hourly_rows:
            require_units(data.get("hourly_units", {}), {"us_aqi": "USAQI", "pm2_5": "μg/m³", "pm10": "μg/m³"}, "Air Quality API")
        return AirQuality(valid_at=local_time(current["time"]), us_aqi=current.get("us_aqi"), pm2_5=current.get("pm2_5"), pm10=current.get("pm10"), nitrogen_dioxide=current.get("nitrogen_dioxide"), ozone=current.get("ozone"), sulphur_dioxide=current.get("sulphur_dioxide"), carbon_monoxide=current.get("carbon_monoxide"), units={key: units[key] for key in ("us_aqi", "pm2_5", "pm10", "nitrogen_dioxide", "ozone", "sulphur_dioxide", "carbon_monoxide") if key in units}, hourly=[AirHour(valid_at=local_time(t), us_aqi=aqi, pm2_5=pm25, pm10=pm10) for t, aqi, pm25, pm10 in hourly_rows])

    async def history(self, lat: float, lng: float, *, today: datetime | None = None) -> HistoricalData:
        local_today = (today or datetime.now(TZ)).astimezone(TZ).date()
        end = local_today - timedelta(days=3)
        start = end - timedelta(days=29)
        data = await self._get(ARCHIVE_URL, {"latitude": lat, "longitude": lng, "start_date": start.isoformat(), "end_date": end.isoformat(), "daily": "precipitation_sum,temperature_2m_mean", "timezone": "Asia/Kolkata"}, 86400)
        if not isinstance(data, dict):
            raise ProviderUnavailable("Archive API", "Unexpected response type")
        daily = data.get("daily", {})
        require_units(data.get("daily_units", {}), {"precipitation_sum": "mm", "temperature_2m_mean": "°C"}, "Archive API")
        rows = aligned(daily, "precipitation_sum", "temperature_2m_mean")
        days = [HistoricalDay(date=datetime.fromisoformat(t).date(), precipitation_sum_mm=p, temperature_mean_c=temp) for t, p, temp in rows]
        rain = [day.precipitation_sum_mm for day in days if day.precipitation_sum_mm is not None]
        temps = [day.temperature_mean_c for day in days if day.temperature_mean_c is not None]
        return HistoricalData(days=days, total_precipitation_mm=round(sum(rain), 2) if rain else None, mean_temperature_c=round(sum(temps) / len(temps), 2) if temps else None, timezone="Asia/Kolkata", units={"precipitation_sum_mm": "mm", "temperature_mean_c": "°C"})
