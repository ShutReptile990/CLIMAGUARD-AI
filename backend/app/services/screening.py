"""Display bins for weather outlooks; never a flood-inundation or calibrated risk model."""

from datetime import timedelta
from app.services.open_meteo import OpenMeteo, ProviderUnavailable, FORECAST_URL, AIR_URL, local_time, require_units, aligned
from app.services.zones import grid_zones


def band(value: float | None, cuts: tuple[float, float, float]) -> str:
    if value is None:
        return "unavailable"
    if value < cuts[0]:
        return "low"
    if value < cuts[1]:
        return "moderate"
    if value < cuts[2]:
        return "high"
    return "severe"


async def grid_screening(provider: OpenMeteo) -> dict:
    zones = grid_zones()
    latitudes = ",".join(f"{z.centroid[0]:.6f}" for z in zones)
    longitudes = ",".join(f"{z.centroid[1]:.6f}" for z in zones)
    values = {zone.slug: {"rainfall_24h_mm": None, "temperature_max_2d_c": None, "us_aqi": None} for zone in zones}
    errors = []
    try:
        weather = await provider._get(FORECAST_URL, {"latitude": latitudes, "longitude": longitudes, "current": "temperature_2m", "hourly": "precipitation", "daily": "temperature_2m_max", "forecast_days": 2, "timezone": "Asia/Kolkata"}, 600)
        if not isinstance(weather, list) or len(weather) != len(zones):
            raise ProviderUnavailable("Forecast API", "Unexpected multi-location response")
        for zone, item in zip(zones, weather):
            require_units(item.get("hourly_units", {}), {"precipitation": "mm"}, "Forecast API")
            require_units(item.get("daily_units", {}), {"temperature_2m_max": "°C"}, "Forecast API")
            current_time = local_time(item["current"]["time"])
            rain = [p for t, p in aligned(item["hourly"], "precipitation") if current_time <= local_time(t) < current_time + timedelta(hours=24) and p is not None]
            highs = [v for v in item["daily"].get("temperature_2m_max", [])[:2] if v is not None]
            values[zone.slug]["rainfall_24h_mm"] = round(sum(rain), 1) if rain else None
            values[zone.slug]["temperature_max_2d_c"] = max(highs) if highs else None
    except (ProviderUnavailable, KeyError, TypeError, ValueError):
        errors.append("Weather screening unavailable")
    try:
        air = await provider._get(AIR_URL, {"latitude": latitudes, "longitude": longitudes, "current": "us_aqi", "timezone": "Asia/Kolkata"}, 1200)
        if not isinstance(air, list) or len(air) != len(zones):
            raise ProviderUnavailable("Air Quality API", "Unexpected multi-location response")
        for zone, item in zip(zones, air):
            require_units(item.get("current_units", {}), {"us_aqi": "USAQI"}, "Air Quality API")
            values[zone.slug]["us_aqi"] = item.get("current", {}).get("us_aqi")
    except (ProviderUnavailable, KeyError, TypeError, ValueError):
        errors.append("US AQI screening unavailable")
    for item in values.values():
        item["bands"] = {"rainfall": band(item["rainfall_24h_mm"], (10, 30, 60)), "temperature": band(item["temperature_max_2d_c"], (35, 40, 45)), "us_aqi": band(item["us_aqi"], (51, 101, 151))}
    return {"kind": "derived_screening", "status": "partial" if errors else "live", "source": "Open-Meteo model outlooks", "timezone": "Asia/Kolkata", "thresholds": {"rainfall_24h_mm": [10, 30, 60], "temperature_max_2d_c": [35, 40, 45], "us_aqi": [51, 101, 151]}, "zones": values, "errors": errors, "disclaimer": "These are display bins from model outlooks, not validated flood-inundation or impact boundaries."}
