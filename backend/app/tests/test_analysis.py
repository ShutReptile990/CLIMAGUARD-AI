"""DEMO inputs are synthetic test fixtures only; never served as observations."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import pytest
from app.schemas.analysis import ScenarioRequest, ZoneMetrics
from app.schemas.environment import AirQuality, CurrentWeather, EnvironmentBundle, HourlyForecast, DailyForecast, StreamError, WeatherData
from app.services.analysis import assess_bundle, priority_result
from app.services.geospatial import intersect_mapped_assets
from app.services.model_registry import EXPECTED_FEATURES, load_flood_model
from app.services.risk_engine import RiskRules, air_assessment, flood_assessment, heat_assessment, heat_index_c

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def demo_weather(rain: float = 2.0) -> WeatherData:
    return WeatherData(current=CurrentWeather(temperature_c=35, humidity_percent=60, precipitation_mm=0, valid_at=NOW, units={}), hourly=[HourlyForecast(valid_at=NOW + timedelta(hours=h), precipitation_mm=rain if h >= 0 else 1, precipitation_probability_percent=50) for h in range(-72, 24)], daily=[DailyForecast(date=(NOW + timedelta(days=i)).date(), temperature_max_c=37+i, temperature_min_c=24, precipitation_sum_mm=10) for i in range(3)], timezone="Asia/Kolkata", units={})


def demo_air(aqi: int = 151) -> AirQuality:
    return AirQuality(valid_at=NOW, us_aqi=aqi, pm2_5=56, pm10=98, nitrogen_dioxide=None, ozone=None, sulphur_dioxide=None, carbon_monoxide=None, units={"us_aqi": "USAQI"})


def demo_bundle(weather=None, air=None) -> EnvironmentBundle:
    return EnvironmentBundle(zone_id="pune-grid-r2-c2", coordinate=(18.525, 73.865), weather=weather or demo_weather(), air_quality=air or demo_air(), history=StreamError(detail="not requested"), persistence="not_configured", retrieved_at=NOW)


def test_flood_index_is_monotonic_bounded_and_explains_missing_terrain():
    low = flood_assessment(demo_weather(.2), now=NOW)
    high = flood_assessment(demo_weather(8), now=NOW)
    assert 0 <= low.score < high.score <= 100
    assert high.method == "heuristic_index" and high.score_unit == "index points / 100"
    assert any("terrain" in warning.lower() for warning in high.warnings)
    assert sum(factor.contribution_points for factor in high.factors) == pytest.approx(high.score, abs=.3)
    assert flood_assessment(None, now=NOW).status == "unavailable"


def test_sourced_drainage_and_historical_exposure_change_index():
    weather = demo_weather(2)
    good = flood_assessment(weather, ZoneMetrics(drainage_index=1, historical_flood_exposure=0, slope_mean_degrees=8), now=NOW)
    poor = flood_assessment(weather, ZoneMetrics(drainage_index=0, historical_flood_exposure=1, slope_mean_degrees=0), now=NOW)
    assert poor.score > good.score


def test_dem_slope_enters_cell_index_without_treating_mapped_drain_distance_as_capacity():
    weather = demo_weather(2)
    overview = flood_assessment(weather, now=NOW)
    cell = flood_assessment(weather, ZoneMetrics(slope_mean_degrees=3.525,
        mapped_drain_distance_m=2431.64), now=NOW)
    assert "Flat-terrain indicator" not in {item.name for item in overview.factors}
    assert "Flat-terrain indicator" in {item.name for item in cell.factors}
    assert "Drainage deficiency" not in {item.name for item in cell.factors}
    assert any("mapped drain proximity does not establish drainage capacity" in warning for warning in cell.warnings)
    assert any("Historical flood exposure unavailable" in warning for warning in cell.warnings)
    assert cell.score != overview.score  # The missing slope is renormalized, never imputed as zero.


def test_heat_index_domain_categories_and_missing_temperature():
    assert heat_index_c(35, 60) > 35
    assert heat_index_c(20, 60) is None
    assert heat_assessment(demo_weather(), now=NOW).level in {"moderate", "high", "severe"}
    assert heat_assessment(None, now=NOW).status == "unavailable"
    rule = RiskRules(25, 50, 75, 30, 35, 40)
    assert heat_assessment(demo_weather(), now=NOW, rules=rule).level == "severe"


def test_air_uses_us_aqi_categories_without_recomputing_indian_aqi():
    assert air_assessment(demo_air(50), now=NOW).category == "Good"
    assert air_assessment(demo_air(151), now=NOW).category == "Unhealthy"
    assert air_assessment(demo_air(301), now=NOW).level == "severe"
    assert air_assessment(None, now=NOW).status == "unavailable"
    assert air_assessment(demo_air(), now=NOW).score_unit == "US AQI"


def test_simulation_changes_only_supported_rules_and_keeps_baseline():
    bundle = demo_bundle()
    baseline = assess_bundle(bundle)
    scenario = ScenarioRequest(zone_id=bundle.zone_id, rainfall_intensity_mm_h=20, rainfall_duration_hours=12, temperature_c=42, humidity_percent=65, drainage_index=0)
    changed = assess_bundle(bundle, scenario=scenario)
    assert changed.mode == "simulation"
    assert changed.assessments[0].score > baseline.assessments[0].score
    assert changed.assessments[1].score > baseline.assessments[1].score
    assert changed.assessments[2].score == baseline.assessments[2].score
    assert bundle.weather.current.temperature_c == 35
    assert priority_result(changed).status == "provisional"
    assert priority_result(changed).warnings


def test_geopandas_shapely_intersection_counts_colocation_not_damage():
    zone = {"type": "Polygon", "coordinates": [[[73.8, 18.5], [73.9, 18.5], [73.9, 18.6], [73.8, 18.6], [73.8, 18.5]]]}
    facilities = [{"geometry": {"type": "Point", "coordinates": [73.85, 18.55]}, "properties": {"kind": "hospital"}}, {"geometry": {"type": "Point", "coordinates": [74.1, 18.55]}, "properties": {"kind": "school"}}]
    roads = [{"geometry": {"type": "LineString", "coordinates": [[73.75, 18.55], [73.85, 18.55], [74.0, 18.55]]}}]
    result = intersect_mapped_assets(zone, facilities, roads)
    assert result["mapped_hospitals"] == 1 and result["mapped_schools"] == 0
    assert result["road_length_km"] > 0
    assert result["physical_damage_inferred"] is False


def test_model_loader_fails_closed_without_evaluated_artifact(tmp_path: Path):
    assert not load_flood_model(tmp_path).available
    (tmp_path / "manifest.json").write_text(json.dumps({"algorithm": "XGBoost", "feature_names": EXPECTED_FEATURES, "evaluation": {}}), encoding="utf-8")
    (tmp_path / "model.json").write_text("{}", encoding="utf-8")
    assert not load_flood_model(tmp_path).available


def test_simulation_schema_rejects_invalid_units_and_ranges():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ScenarioRequest(zone_id="pune-grid-r2-c2", rainfall_intensity_mm_h=-1, rainfall_duration_hours=25)
    with pytest.raises(ValidationError):
        ScenarioRequest(zone_id="pune-grid-r2-c2", humidity_percent=110)


def test_api_schema_exposes_typed_analysis_contracts():
    from app.main import app
    schema = app.openapi()
    assert "/api/analysis/{zone_id}" in schema["paths"]
    assert "/api/analysis/simulate" in schema["paths"]
    assert schema["paths"]["/api/analysis/simulate"]["post"]["requestBody"]
    assert "/api/analysis/demo/extreme-rainfall" in schema["paths"]


def test_extreme_demo_reuses_nugen_inputs_and_sourced_cell_context(monkeypatch):
    import asyncio
    from app.services.analysis import AnalysisService
    from app.services.nugen_guidance import SCENARIOS
    from app.services.zones import grid_zones
    service = AnalysisService(None, None)
    async def context():
        return {zone.slug: {"slope_mean_degrees": index,
                "mapped_drain_distance_m": 100 + index,
                "provenance": {"dem": {"source": "TEST sourced DEM"},
                               "mapped_waterways": {"source": "TEST OSM"}}}
                for index, zone in enumerate(grid_zones())}
    monkeypatch.setattr(service, "context_all", context)
    result = asyncio.run(service.extreme_flood_demo())
    assert len(result.zones) == 9
    assert result.rainfall_intensity_mm_h == SCENARIOS["extreme_rainfall"].rainfall_intensity_mm_h
    scores = []
    for zone_id, analysis in result.zones.items():
        flood = analysis.assessments[0]
        scores.append(flood.score)
        assert analysis.mode == "simulation" and flood.simulated
        assert flood.factors[0].value == result.rainfall_intensity_mm_h * result.rainfall_duration_hours
        assert "Drainage deficiency" not in {factor.name for factor in flood.factors}
        assert analysis.metrics.mapped_drain_distance_m is not None
    assert len(set(scores)) > 1
    assert result.overview.metrics is None
    assert 0 <= result.overview.assessments[0].score <= 100
