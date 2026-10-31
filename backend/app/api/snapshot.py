from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from app.core.errors import ServiceUnavailable
from app.integrations.supabase import SupabaseGateway, get_gateway
from app.repositories.supabase import Repository
from app.schemas.alerts import Alert
from app.api.alerts import public_alerts
from app.services.environment import EnvironmentService, get_environment_service
from app.schemas.environment import WeatherData, AirQuality
from app.services.zones import coordinates_for, find_zone
from app.services.analysis import AnalysisService, assess_bundle
import logging

router = APIRouter(tags=["snapshot"])


class Locality(BaseModel):
    id: str
    name: str
    city: str
    center: tuple[float, float]


class Weather(BaseModel):
    temperatureC: float | None
    humidityPercent: float | None
    rainfallMm: float | None
    aqi: int | None
    observedAt: str | None
    source: str | None
    status: str
    dataKind: str = "current_model_estimate"
    aqiScale: str = "US AQI"
    airValidAt: str | None = None
    pm2_5: float | None = None
    pm10: float | None = None


class Risk(BaseModel):
    hazard: str
    level: str
    score: float | None
    factors: list[str]
    assessedAt: str | None
    source: str
    status: str
    method: str | None = None
    scoreUnit: str | None = None
    category: str | None = None
    warnings: list[str] = []
    rulesVersion: str | None = None


class Snapshot(BaseModel):
    locality: Locality
    weather: Weather
    risks: list[Risk]
    alerts: list[Alert]
    facilities: list[dict]
    updatedAt: str | None
    status: str


@router.get("/localities/{locality_id}/snapshot", response_model=Snapshot)
async def snapshot(locality_id: str = Path(pattern="^[a-z0-9-]+$"), gateway: SupabaseGateway = Depends(get_gateway), environment: EnvironmentService = Depends(get_environment_service)):
    coords = coordinates_for(locality_id)
    if coords is None:
        raise ServiceUnavailable("This Pune locality is not configured.")
    bundle = await environment.bundle(locality_id, include_history=False)
    weather_data = bundle.weather if isinstance(bundle.weather, WeatherData) else None
    air_data = bundle.air_quality if isinstance(bundle.air_quality, AirQuality) else None
    if weather_data is None and air_data is None:
        raise ServiceUnavailable("Open-Meteo weather and air quality are unavailable for this locality.")
    zone = find_zone(locality_id)
    name = zone.name if zone else locality_id.replace("-", " ").title()
    weather = Weather(temperatureC=weather_data.current.temperature_c if weather_data else None, humidityPercent=weather_data.current.humidity_percent if weather_data else None, rainfallMm=weather_data.current.precipitation_mm if weather_data else None, aqi=air_data.us_aqi if air_data else None, observedAt=weather_data.current.valid_at.isoformat() if weather_data else None, airValidAt=air_data.valid_at.isoformat() if air_data else None, pm2_5=air_data.pm2_5 if air_data else None, pm10=air_data.pm10 if air_data else None, source="Open-Meteo model estimates", status="live")
    metrics = None
    if zone:
        analysis_service = AnalysisService(environment, gateway)
        context = await analysis_service.context_all()
        metrics = analysis_service.metrics_from_context(context.get(locality_id))
    risks = [Risk(hazard=item.hazard, level=item.level, score=item.score, factors=[factor.name + (f": {factor.value:g} {factor.unit}" if factor.value is not None and factor.unit else "") for factor in item.factors], assessedAt=item.assessed_at.isoformat(), source="; ".join(item.sources) if item.sources else "Input unavailable", status="live" if item.status == "available" else "unavailable", method=item.method, scoreUnit=item.score_unit, category=item.category, warnings=item.warnings, rulesVersion=item.rules_version) for item in assess_bundle(bundle, metrics).assessments]
    alerts = []
    if gateway.settings.configured:
        try:
            alerts = await public_alerts(gateway, locality_id, 20)
        except Exception as exc:
            logging.getLogger("climaguard.snapshot").warning("alerts_unavailable type=%s", type(exc).__name__)
    return Snapshot(locality=Locality(id=locality_id, name=name, city="Pune, Maharashtra", center=coords), weather=weather, risks=risks, alerts=alerts, facilities=[], updatedAt=weather_data.current.valid_at.isoformat() if weather_data else air_data.valid_at.isoformat(), status="live")
