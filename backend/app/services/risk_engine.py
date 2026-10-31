"""Transparent screening rules. None of these outputs are calibrated event probabilities."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from app.schemas.analysis import Contribution, HazardAssessment, ZoneMetrics
from app.schemas.environment import AirQuality, WeatherData
from app.core.config import get_settings

FLOOD_VERSION = "flood-rainfall-index-v1"
HEAT_VERSION = "heat-index-rules-v1"
AIR_VERSION = "us-aqi-categories-v1"


@dataclass(frozen=True)
class RiskRules:
    flood_moderate: float = 25.0
    flood_high: float = 50.0
    flood_severe: float = 75.0
    heat_moderate_c: float = 32.0
    heat_high_c: float = 40.0
    heat_severe_c: float = 50.0


def configured_rules() -> RiskRules:
    settings = get_settings()
    rules = RiskRules(settings.flood_moderate_index, settings.flood_high_index, settings.flood_severe_index, settings.heat_moderate_c, settings.heat_high_c, settings.heat_severe_c)
    if not (rules.flood_moderate < rules.flood_high < rules.flood_severe and rules.heat_moderate_c < rules.heat_high_c < rules.heat_severe_c):
        raise ValueError("Risk thresholds must be strictly increasing")
    return rules


def _level(score: float, limits: tuple[float, float, float]) -> str:
    return "low" if score < limits[0] else "moderate" if score < limits[1] else "high" if score < limits[2] else "severe"


def _clamp(value: float, cap: float) -> float:
    return min(max(value / cap, 0.0), 1.0)


def _valid(value: float | None) -> bool:
    return value is not None and isfinite(value)


def heat_index_c(temperature_c: float | None, humidity_percent: float | None) -> float | None:
    """NWS Rothfusz regression, only in its usual warm/humid domain."""
    if not _valid(temperature_c) or not _valid(humidity_percent) or temperature_c < 26.7 or not 0 <= humidity_percent <= 100:
        return None
    t = temperature_c * 9 / 5 + 32
    r = humidity_percent
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + r * 0.094)
    if (simple + t) / 2 < 80:
        return None
    hi = (-42.379 + 2.04901523*t + 10.14333127*r - 0.22475541*t*r
          - 0.00683783*t*t - 0.05481717*r*r + 0.00122874*t*t*r
          + 0.00085282*t*r*r - 0.00000199*t*t*r*r)
    if r < 13 and 80 <= t <= 112:
        hi -= ((13-r)/4) * ((17-abs(t-95))/17)**0.5
    elif r > 85 and 80 <= t <= 87:
        hi += ((r-85)/10) * ((87-t)/5)
    return round((hi - 32) * 5 / 9, 1)


def _unavailable(hazard: str, method: str, version: str, warning: str, now: datetime) -> HazardAssessment:
    return HazardAssessment(hazard=hazard, status="unavailable", method=method, level="unavailable", warnings=[warning], assessed_at=now, rules_version=version)


def flood_assessment(weather: WeatherData | None, metrics: ZoneMetrics | None = None, *, now: datetime | None = None, rules: RiskRules = RiskRules(), rainfall_intensity_mm_h: float | None = None, rainfall_duration_hours: int = 6, drainage_assumption: float | None = None) -> HazardAssessment:
    now = now or datetime.now(timezone.utc)
    simulated = rainfall_intensity_mm_h is not None or drainage_assumption is not None
    if weather is None and rainfall_intensity_mm_h is None:
        return _unavailable("flood", "heuristic_index", FLOOD_VERSION, "Forecast rainfall is unavailable.", now)
    current_time = weather.current.valid_at if weather else now
    recent: list[float] = []
    future: list[float] = []
    if weather:
        recent = [hour.precipitation_mm for hour in weather.hourly if current_time - timedelta(hours=72) <= hour.valid_at < current_time and _valid(hour.precipitation_mm)]
        future = [hour.precipitation_mm for hour in weather.hourly if current_time <= hour.valid_at < current_time + timedelta(hours=24) and _valid(hour.precipitation_mm)]
    if rainfall_intensity_mm_h is not None:
        forecast_total = rainfall_intensity_mm_h * rainfall_duration_hours
        peak_hour = rainfall_intensity_mm_h
    elif future:
        forecast_total, peak_hour = sum(future), max(future)
    else:
        return _unavailable("flood", "heuristic_index", FLOOD_VERSION, "The next 24 hours of rainfall forecast are unavailable.", now)
    drainage = drainage_assumption if drainage_assumption is not None else metrics.drainage_index if metrics else None
    candidates = [
        ("Forecast 24-hour rainfall", forecast_total, "mm", .35, _clamp(forecast_total, 100), "Hypothetical input" if rainfall_intensity_mm_h is not None else "Open-Meteo Forecast API"),
        ("Peak hourly rainfall", peak_hour, "mm/h", .20, _clamp(peak_hour, 30), "Hypothetical input" if rainfall_intensity_mm_h is not None else "Open-Meteo Forecast API"),
        ("Prior 72-hour model rainfall", sum(recent) if recent else None, "mm", .20, _clamp(sum(recent), 150) if recent else None, "Open-Meteo Forecast API past_days"),
        ("Flat-terrain indicator", metrics.slope_mean_degrees if metrics else None, "degrees", .05, 1-_clamp(metrics.slope_mean_degrees, 10) if metrics and _valid(metrics.slope_mean_degrees) else None, "Sourced DEM"),
        ("Drainage deficiency", drainage, "0–1 capacity", .10, 1-drainage if drainage is not None else None, "Hypothetical input" if drainage_assumption is not None else "Sourced drainage dataset"),
        ("Historical flood exposure", metrics.historical_flood_exposure if metrics else None, "0–1", .10, metrics.historical_flood_exposure if metrics else None, "Sourced flood records"),
    ]
    included = [row for row in candidates if row[4] is not None]
    weight_sum = sum(row[3] for row in included)
    score = round(100 * sum(row[3] * row[4] for row in included) / weight_sum, 1)
    warnings = [f"{row[0]} unavailable; remaining weights renormalized." for row in candidates if row[4] is None]
    warnings.append("Screening index only; no labeled flood events, calibrated probability, or inundation model.")
    if weather and len(future) < 24 and rainfall_intensity_mm_h is None:
        warnings.append(f"Only {len(future)} forecast hours supplied for the 24-hour window.")
    return HazardAssessment(hazard="flood", status="available", method="heuristic_index", level=_level(score, (rules.flood_moderate, rules.flood_high, rules.flood_severe)), score=score, score_unit="index points / 100", category="Rainfall-led flood screening", factors=[Contribution(name=name, value=round(value, 2) if value is not None else None, unit=unit, contribution_points=round(100*weight*normalized/weight_sum, 1), source=source) for name, value, unit, weight, normalized, source in included], warnings=warnings, sources=sorted({row[5] for row in included}), assessed_at=now, data_valid_at=current_time if weather else None, forecast_horizon_hours=24, rules_version=FLOOD_VERSION, simulated=simulated)


def heat_assessment(weather: WeatherData | None, *, now: datetime | None = None, rules: RiskRules = RiskRules(), temperature_c: float | None = None, humidity_percent: float | None = None) -> HazardAssessment:
    now = now or datetime.now(timezone.utc)
    simulated = temperature_c is not None or humidity_percent is not None
    temp = temperature_c if temperature_c is not None else weather.current.temperature_c if weather else None
    humidity = humidity_percent if humidity_percent is not None else weather.current.humidity_percent if weather else None
    if not _valid(temp):
        return _unavailable("heat", "rule_based", HEAT_VERSION, "Temperature is unavailable.", now)
    apparent = heat_index_c(temp, humidity)
    highs = [day.temperature_max_c for day in weather.daily[:3] if _valid(day.temperature_max_c)] if weather and not simulated else []
    screening_temp = max([apparent or temp, *highs])
    warnings = ["Future humidity is unavailable; forecast highs are air temperature, not forecast heat index."] if highs else []
    if apparent is None:
        warnings.append("Heat index outside the NWS regression domain or humidity unavailable; air temperature used.")
    warnings.append("This is a screening category, not an officially issued heatwave warning.")
    factors = [Contribution(name="Air temperature", value=round(temp, 1), unit="°C", source="Hypothetical input" if temperature_c is not None else "Open-Meteo Forecast API"), Contribution(name="Relative humidity", value=humidity, unit="%", source="Hypothetical input" if humidity_percent is not None else "Open-Meteo Forecast API")]
    if apparent is not None:
        factors.append(Contribution(name="NWS heat index estimate", value=apparent, unit="°C", source="NWS Rothfusz equation"))
    if highs:
        factors.append(Contribution(name="Highest 3-day forecast temperature", value=max(highs), unit="°C", source="Open-Meteo Forecast API"))
    return HazardAssessment(hazard="heat", status="available", method="rule_based", level=_level(screening_temp, (rules.heat_moderate_c, rules.heat_high_c, rules.heat_severe_c)), score=round(screening_temp, 1), score_unit="°C screening temperature", category="Heat exposure screening", factors=factors, warnings=warnings, sources=sorted({factor.source for factor in factors}), assessed_at=now, data_valid_at=weather.current.valid_at if weather else None, forecast_horizon_hours=72 if highs else 0, rules_version=HEAT_VERSION, simulated=simulated)


def air_assessment(air: AirQuality | None, *, now: datetime | None = None) -> HazardAssessment:
    now = now or datetime.now(timezone.utc)
    if air is None or air.us_aqi is None:
        return _unavailable("air_quality", "us_aqi_category", AIR_VERSION, "US AQI is unavailable; no category inferred from PM values.", now)
    aqi = air.us_aqi
    category = ("Good" if aqi <= 50 else "Moderate" if aqi <= 100 else "Unhealthy for Sensitive Groups" if aqi <= 150 else "Unhealthy" if aqi <= 200 else "Very Unhealthy" if aqi <= 300 else "Hazardous")
    level = "low" if aqi <= 50 else "moderate" if aqi <= 100 else "high" if aqi <= 200 else "severe"
    precautions = (["Follow current official air-quality advice."] if aqi <= 100 else ["People with heart or lung conditions, older adults and children should check official activity guidance.", "Consider reducing prolonged outdoor exertion; follow current local advisories."])
    return HazardAssessment(hazard="air_quality", status="available", method="us_aqi_category", level=level, score=float(aqi), score_unit="US AQI", category=category, factors=[Contribution(name="US AQI", value=aqi, unit="USAQI", source=air.source), Contribution(name="PM2.5", value=air.pm2_5, unit="μg/m³", source=air.source), Contribution(name="PM10", value=air.pm10, unit="μg/m³", source=air.source)], warnings=["US AQI is not Indian AQI; provider values are model estimates."], precautions=precautions, sources=[air.source], assessed_at=now, data_valid_at=air.valid_at, forecast_horizon_hours=0, rules_version=AIR_VERSION)
