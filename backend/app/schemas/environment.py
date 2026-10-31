from datetime import datetime, date
from typing import Literal
from pydantic import BaseModel, Field


class CurrentWeather(BaseModel):
    kind: Literal["current_model_estimate"] = "current_model_estimate"
    temperature_c: float | None = Field(ge=-90, le=60)
    humidity_percent: float | None = Field(ge=0, le=100)
    precipitation_mm: float | None = Field(ge=0)
    valid_at: datetime
    source: str = "Open-Meteo Forecast API"
    units: dict[str, str]


class HourlyForecast(BaseModel):
    kind: Literal["forecast"] = "forecast"
    valid_at: datetime
    precipitation_mm: float | None = Field(ge=0)
    precipitation_probability_percent: float | None = Field(ge=0, le=100)


class DailyForecast(BaseModel):
    kind: Literal["forecast"] = "forecast"
    date: date
    temperature_max_c: float | None
    temperature_min_c: float | None
    precipitation_sum_mm: float | None = Field(ge=0)


class WeatherData(BaseModel):
    current: CurrentWeather
    hourly: list[HourlyForecast]
    daily: list[DailyForecast]
    timezone: str
    source: str = "Open-Meteo Forecast API"
    units: dict[str, str]


class AirQuality(BaseModel):
    kind: Literal["current_model_estimate"] = "current_model_estimate"
    valid_at: datetime
    us_aqi: int | None = Field(ge=0)
    pm2_5: float | None = Field(ge=0)
    pm10: float | None = Field(ge=0)
    nitrogen_dioxide: float | None = Field(ge=0)
    ozone: float | None = Field(ge=0)
    sulphur_dioxide: float | None = Field(ge=0)
    carbon_monoxide: float | None = Field(ge=0)
    source: str = "Open-Meteo Air Quality API (CAMS model)"
    units: dict[str, str]
    hourly: list["AirHour"] = Field(default_factory=list)


class AirHour(BaseModel):
    kind: Literal["current_model_estimate"] = "current_model_estimate"
    valid_at: datetime
    us_aqi: int | None = Field(ge=0)
    pm2_5: float | None = Field(ge=0)
    pm10: float | None = Field(ge=0)


class HistoricalDay(BaseModel):
    kind: Literal["historical_reanalysis"] = "historical_reanalysis"
    date: date
    precipitation_sum_mm: float | None = Field(ge=0)
    temperature_mean_c: float | None


class HistoricalData(BaseModel):
    days: list[HistoricalDay]
    total_precipitation_mm: float | None
    mean_temperature_c: float | None
    source: str = "Open-Meteo Historical Archive (reanalysis)"
    timezone: str
    units: dict[str, str]


class StreamError(BaseModel):
    status: Literal["unavailable"] = "unavailable"
    detail: str


class EnvironmentBundle(BaseModel):
    zone_id: str
    coordinate: tuple[float, float]
    timezone: str = "Asia/Kolkata"
    weather: WeatherData | StreamError
    air_quality: AirQuality | StreamError
    history: HistoricalData | StreamError
    persistence: Literal["stored", "not_configured", "failed"]
    retrieved_at: datetime
