"""Live, explainable screening and explicit simulation; no trained model is present."""

import asyncio
import logging
from datetime import datetime, timezone
from fastapi import Request
from app.integrations.supabase import SupabaseGateway
from app.schemas.analysis import AnalysisResponse, ComparisonResponse, DemoFloodResponse, ExposureResponse, FeatureAvailability, PriorityComponent, PriorityResult, ScenarioRequest, SimulationResponse, ZoneMetrics
from app.schemas.environment import AirQuality, EnvironmentBundle, StreamError, WeatherData
from app.services.environment import EnvironmentService
from app.services.risk_engine import air_assessment, configured_rules, flood_assessment, heat_assessment
from app.services.zones import find_zone, grid_zones
from app.services.local_population import local_population_context
from app.services.local_waterways import local_waterway_context

PRIORITY_VERSION = "emergency-screening-priority-v1"
PRIORITY_WEIGHTS = {"hazard": .4, "population": .3, "critical_infrastructure": .2, "vulnerability": .1}


def _feature_availability(weather: WeatherData | None, metrics: ZoneMetrics | None, zone_id: str | None = None,
                          grid_coverage: dict[str, int] | None = None) -> list[FeatureAvailability]:
    provenance = metrics.provenance or {} if metrics else {}
    population = provenance.get("population") or {}
    waterways = provenance.get("mapped_waterways") or {}
    grid_scope_missing = bool(zone_id and not find_zone(zone_id))
    coverage = grid_coverage or {}
    def scope_status(value: object, source_storage: str | None, coverage_key: str) -> str:
        if grid_scope_missing:
            return "partial" if coverage.get(coverage_key, 0) > 0 else "unavailable"
        if value is None:
            return "unavailable"
        return "partial" if source_storage == "local_api_cache_preview" or source_storage == "local_geojson_preview" else "available"
    def item(name: str, status: str, source: str, limitation: str) -> FeatureAvailability:
        return FeatureAvailability(name=name, status=status, source=source, limitation=limitation)
    return [
        item("Rainfall forecast", "available" if weather and weather.hourly else "unavailable", "Open-Meteo model forecast" if weather and weather.hourly else "Open-Meteo unavailable", "Model estimate; not a rain-gauge observation."),
        item("Terrain slope", scope_status(metrics.slope_mean_degrees if metrics else None, (provenance.get("dem") or {}).get("storage"), "slope"), str((provenance.get("dem") or {}).get("source", f"Copernicus DEM grid-cell coverage: {coverage.get('slope', 0)}/9" if grid_scope_missing else "No sourced DEM slope")), "Select a Pune analysis cell for its mean slope. It is not a drainage or inundation model." if grid_scope_missing else "Zone mean slope is not a drainage or inundation model."),
        item("Mapped drainage proximity", scope_status(metrics.mapped_drain_distance_m if metrics else None, waterways.get("storage"), "drainage"), str(waterways.get("source", f"OpenStreetMap grid-cell coverage: {coverage.get('drainage', 0)}/9" if grid_scope_missing else "No validated mapped drain geometry")), "Select a Pune analysis cell for its proximity value. Proximity does not establish drain capacity, condition, or effectiveness." if grid_scope_missing else "Mapped line proximity does not establish drain capacity, condition, or effectiveness."),
        item("Zone population", scope_status(metrics.population_estimate if metrics else None, population.get("storage"), "population"), (f"{population.get('source', 'WorldPop Global2 API v2')} · {population.get('dataset_year', 'year unknown')} · {population.get('spatial_resolution', 'resolution unknown')}" if metrics and metrics.population_estimate is not None else f"WorldPop grid-cell coverage: {coverage.get('population', 0)}/9" if grid_scope_missing else "No validated population estimate"), "Select a Pune analysis cell; the Pune locality is not a single population polygon." if grid_scope_missing else "Modeled population in the cell is not population exposed to flooding."),
        item("Historical flood exposure", "available" if metrics and metrics.historical_flood_exposure is not None and (provenance.get("historical_flood_exposure") or {}).get("verified") is True else "unavailable", str((provenance.get("historical_flood_exposure") or {}).get("source", "No verified historical flood-event labels")), "Requires verified observed events, event dates, spatial matching and documented temporal resolution."),
        item("Calibrated flood model", "unavailable", "No evaluated model artifact", "Verified positive and negative event labels and held-out calibration are absent; flood score remains a heuristic index."),
    ]


def _local_context() -> dict[str, dict]:
    rows = local_population_context()
    for slug, waterway in local_waterway_context().items():
        prior = rows.get(slug, {})
        rows[slug] = {**prior, **waterway, "provenance": {**(prior.get("provenance") or {}), **waterway["provenance"]}}
    return rows


def assess_bundle(bundle: EnvironmentBundle, metrics: ZoneMetrics | None = None, *, scenario: ScenarioRequest | None = None,
                  grid_coverage: dict[str, int] | None = None) -> AnalysisResponse:
    weather = bundle.weather if isinstance(bundle.weather, WeatherData) else None
    air = bundle.air_quality if isinstance(bundle.air_quality, AirQuality) else None
    now = datetime.now(timezone.utc)
    rules = configured_rules()
    assessments = [
        flood_assessment(weather, metrics, now=now, rules=rules, rainfall_intensity_mm_h=scenario.rainfall_intensity_mm_h if scenario else None, rainfall_duration_hours=scenario.rainfall_duration_hours if scenario else 6, drainage_assumption=scenario.drainage_index if scenario else None),
        heat_assessment(weather, now=now, rules=rules, temperature_c=scenario.temperature_c if scenario else None, humidity_percent=scenario.humidity_percent if scenario else None),
        air_assessment(air, now=now),
    ]
    for assessment in assessments:
        if assessment.data_valid_at and (now - assessment.data_valid_at).total_seconds() > (6 if assessment.hazard == "air_quality" else 3) * 3600:
            assessment.warnings.append("Source data is stale; check the validity timestamp before use.")
    return AnalysisResponse(zone_id=bundle.zone_id, mode="simulation" if scenario else "live", assessments=assessments, metrics=metrics, metrics_status="available" if metrics else "unavailable", feature_availability=_feature_availability(weather, metrics, bundle.zone_id, grid_coverage), assessed_at=now, disclaimer="Heuristic/rule-based screening, not calibrated flood probability, official heatwave warning, or inundation map. Simulated inputs are hypothetical." if scenario else "Heuristic/rule-based screening, not calibrated flood probability, official heatwave warning, or inundation map.")


def priority_result(analysis: AnalysisResponse, context: dict | None = None, *, simulated: bool = False) -> PriorityResult:
    context = context or {}
    hazard_summary = {item.hazard: {"level": item.level, "score": item.score, "unit": item.score_unit, "method": item.method} for item in analysis.assessments}
    scores = []
    for item in analysis.assessments:
        if item.score is None:
            continue
        if item.hazard == "flood":
            scores.append(min(item.score / 100, 1))
        elif item.hazard == "heat":
            scores.append(min(max((item.score - 25) / 30, 0), 1))
        elif item.hazard == "air_quality":
            scores.append(min(item.score / 300, 1))
    population = context.get("population_estimate")
    critical = sum(context.get(key) or 0 for key in ("mapped_hospitals", "mapped_schools", "mapped_emergency_services")) if any(context.get(key) is not None for key in ("mapped_hospitals", "mapped_schools", "mapped_emergency_services")) else None
    vulnerability = context.get("vulnerability_index")
    values = {"hazard": max(scores) if scores else None, "population": min(population / 100000, 1) if population is not None else None, "critical_infrastructure": min(critical / 10, 1) if critical is not None else None, "vulnerability": vulnerability}
    if values["hazard"] is None:
        return PriorityResult(zone_id=analysis.zone_id, status="unavailable", components=[PriorityComponent(name=key, normalized=None, weight=weight) for key, weight in PRIORITY_WEIGHTS.items()], warnings=["Hazard inputs are unavailable; no priority can be ranked."], version=PRIORITY_VERSION, simulated=simulated, hazards=hazard_summary)
    available_weight = sum(PRIORITY_WEIGHTS[key] for key, value in values.items() if value is not None)
    components = [PriorityComponent(name=key, normalized=round(value, 4) if value is not None else None, weight=weight, contribution_points=round(100 * value * weight / available_weight, 1) if value is not None and available_weight else None) for key, weight in PRIORITY_WEIGHTS.items() for value in [values[key]]]
    return PriorityResult(zone_id=analysis.zone_id, score=round(sum(component.contribution_points or 0 for component in components), 1) if available_weight else None, status="provisional" if available_weight else "unavailable", components=components, warnings=[f"{key.replace('_', ' ').title()} unavailable; remaining weights renormalized." for key, value in values.items() if value is None] + ["Analysis-cell ranking does not estimate physical damage or rescue need."], version=PRIORITY_VERSION, simulated=simulated, hazards=hazard_summary)


class AnalysisService:
    def __init__(self, environment: EnvironmentService, database: SupabaseGateway):
        self.environment = environment
        self.database = database

    async def context_all(self) -> dict[str, dict]:
        if not self.database.settings.configured:
            return _local_context()
        try:
            rows = await self.database.request("POST", "/rest/v1/rpc/analysis_zone_context_all", json={})
            sourced = {row["slug"]: row for row in rows} if isinstance(rows, list) else {}
            try:
                flood_rows = await self.database.request("POST", "/rest/v1/rpc/analysis_zone_flood_features_all", json={})
                for item in flood_rows if isinstance(flood_rows, list) else []:
                    sourced.setdefault(item["slug"], {}).update({k: v for k, v in item.items() if k != "slug"})
            except Exception:
                logging.getLogger("climaguard.analysis").warning("flood_features_rpc_unavailable")
            for slug, local in _local_context().items():
                prior = sourced.get(slug, {})
                sourced[slug] = {**local, **prior, **{key: value for key, value in local.items() if key != "provenance" and prior.get(key) is None},
                                 "provenance": {**local.get("provenance", {}), **(prior.get("provenance") or {})}}
            return sourced
        except Exception as exc:
            logging.getLogger("climaguard.analysis").warning("zone_context_unavailable type=%s", type(exc).__name__)
            return _local_context()

    @staticmethod
    def metrics_from_context(row: dict | None) -> ZoneMetrics | None:
        if not row:
            return None
        values = {key: row.get(key) for key in ZoneMetrics.model_fields if key in row}
        provenance = values.get("provenance") or {}
        if not (provenance.get("historical_flood_exposure") or {}).get("verified") is True:
            values["historical_flood_exposure"] = None
        if not any(value is not None for key, value in values.items() if key != "provenance"):
            return None
        return ZoneMetrics.model_validate(values)

    async def zone(self, zone_id: str) -> AnalysisResponse:
        bundle, context = await asyncio.gather(self.environment.bundle(zone_id, include_history=False), self.context_all())
        coverage = {"slope": 0, "drainage": 0, "population": 0}
        for zone in grid_zones():
            row = context.get(zone.slug) or {}
            provenance = row.get("provenance") or {}
            coverage["slope"] += int(row.get("slope_mean_degrees") is not None and bool((provenance.get("dem") or {}).get("source")))
            coverage["drainage"] += int(row.get("mapped_drain_distance_m") is not None and bool((provenance.get("mapped_waterways") or {}).get("source")))
            coverage["population"] += int(row.get("population_estimate") is not None and bool((provenance.get("population") or {}).get("source")))
        return assess_bundle(bundle, self.metrics_from_context(context.get(zone_id)), grid_coverage=coverage)

    async def exposure(self, zone_id: str) -> ExposureResponse:
        if not find_zone(zone_id):
            from fastapi import HTTPException
            raise HTTPException(404, "Unknown Pune analysis cell.")
        context = (await self.context_all()).get(zone_id)
        assumptions = ["Counts are mapped assets intersecting a reproducible analysis cell, not assets flooded or damaged.", "Population is a zone-level WorldPop estimate; provenance identifies local cache or PostGIS storage.", "Road length is the road geometry clipped to the cell in PostGIS."]
        if context is None:
            return ExposureResponse(zone_id=zone_id, status="unavailable", method="PostGIS ST_Intersects and ST_Intersection", assumptions=assumptions, warnings=["PostGIS geographic records are unavailable."])
        has_assets = any(context.get(k) is not None for k in ("mapped_hospitals", "mapped_schools", "mapped_emergency_services", "road_length_km"))
        has_pop = context.get("population_estimate") is not None
        return ExposureResponse(zone_id=zone_id, status="available" if has_assets and has_pop else "partial" if has_assets or has_pop else "unavailable", mapped_hospitals=context.get("mapped_hospitals"), mapped_schools=context.get("mapped_schools"), mapped_emergency_services=context.get("mapped_emergency_services"), road_length_km=context.get("road_length_km"), population_in_cell=context.get("population_estimate"), potential_population_exposure=None, method="PostGIS ST_Intersects and ST_Intersection", assumptions=assumptions, warnings=["Potential population exposure unavailable: no validated hazard footprint and matching population coverage are available.", "Geographic co-location is not physical exposure."])

    async def compare(self, *, scenario: ScenarioRequest | None = None) -> ComparisonResponse:
        context_task = asyncio.create_task(self.context_all())
        bundles = await asyncio.gather(*(self.environment.bundle(zone.slug, include_history=False) for zone in grid_zones()))
        context = await context_task
        results = []
        for bundle in bundles:
            row = context.get(bundle.zone_id)
            analysis = assess_bundle(bundle, self.metrics_from_context(row), scenario=scenario if scenario and scenario.zone_id == bundle.zone_id else None)
            results.append(priority_result(analysis, row, simulated=bool(scenario and scenario.zone_id == bundle.zone_id)))
        ranked = sorted((item for item in results if item.score is not None), key=lambda item: (-item.score, item.zone_id))
        for rank, item in enumerate(ranked, 1):
            item.rank = rank
        return ComparisonResponse(mode="simulation" if scenario else "live", zones=sorted(results, key=lambda item: (item.rank is None, item.rank or 0)), assessed_at=datetime.now(timezone.utc), disclaimer="Provisional, normalized screening priority. Missing population, mapped assets and vulnerability are disclosed; ranks are not operational dispatch orders.")

    async def extreme_flood_demo(self) -> DemoFloodResponse:
        """Use the Nugen preset with each cell's sourced context, without live weather or writes."""
        from app.services.nugen_guidance import SCENARIOS
        from app.services.zones import coordinates_for
        preset = SCENARIOS["extreme_rainfall"]
        context = await self.context_all()
        now = datetime.now(timezone.utc)
        unavailable = StreamError(detail="No current environmental values are used in this simulation.")

        def assess(zone_id: str) -> AnalysisResponse:
            bundle = EnvironmentBundle(zone_id=zone_id, coordinate=coordinates_for(zone_id),
                weather=unavailable, air_quality=unavailable, history=unavailable,
                persistence="not_configured", retrieved_at=now)
            inputs = ScenarioRequest(zone_id=zone_id, rainfall_intensity_mm_h=preset.rainfall_intensity_mm_h,
                                     rainfall_duration_hours=preset.rainfall_duration_hours or 6)
            return assess_bundle(bundle, self.metrics_from_context(context.get(zone_id)), scenario=inputs)

        return DemoFloodResponse(rainfall_intensity_mm_h=preset.rainfall_intensity_mm_h,
            rainfall_duration_hours=preset.rainfall_duration_hours or 6,
            zones={zone.slug: assess(zone.slug) for zone in grid_zones()}, overview=assess("pune"),
            disclaimer="SIMULATION — NOT CURRENT CONDITIONS. Heuristic flood indices, not calibrated probabilities or inundation boundaries. Mapped drain proximity is not verified capacity. No environmental observations, incidents or alerts are written.")

    async def simulate(self, request: ScenarioRequest) -> SimulationResponse:
        if not any(value is not None for value in (request.rainfall_intensity_mm_h, request.temperature_c, request.humidity_percent, request.drainage_index)):
            from fastapi import HTTPException
            raise HTTPException(422, "Supply at least one hypothetical input.")
        bundle, context = await asyncio.gather(self.environment.bundle(request.zone_id, include_history=False), self.context_all())
        row = context.get(request.zone_id)
        metrics = self.metrics_from_context(row)
        baseline = assess_bundle(bundle, metrics)
        simulated = assess_bundle(bundle, metrics, scenario=request)
        comparison = await self.compare(scenario=request)
        priority = next(item for item in comparison.zones if item.zone_id == request.zone_id)
        return SimulationResponse(inputs=request, baseline=baseline, simulated=simulated, priority=priority, disclaimer="SIMULATION MODE: hypothetical inputs only. No forecast, alert, official heatwave warning, or inundation prediction is changed. Reset by clearing the scenario and requesting live analysis.")


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis
