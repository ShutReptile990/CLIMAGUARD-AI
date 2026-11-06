"""Ground Nugen guidance in live analysis or isolated hypothetical screening."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from fastapi import HTTPException
from app.core.errors import NugenFailure
from app.integrations.nugen import NugenClient
from app.integrations.supabase import SupabaseGateway
from app.schemas.analysis import ScenarioRequest
from app.schemas.environment import EnvironmentBundle, StreamError
from app.schemas.nugen import GuidanceRequest, GuidanceResponse, GuidanceScenario, NugenAnalysisContext
from app.services.analysis import AnalysisService, assess_bundle, priority_result
from app.services.zones import LEGACY_CENTERS, coordinates_for, find_zone


# Explicit hypothetical inputs. There is no AQI simulator, so none is invented.
SCENARIOS = {
    "extreme_rainfall": GuidanceScenario(id="extreme_rainfall", label="Extreme Rainfall / Severe Flood Screening", rainfall_intensity_mm_h=25,
        rainfall_duration_hours=6, limitation="Hypothetical rainfall intensity; no forecast, observed flood or inundation boundary."),
    "severe_heat": GuidanceScenario(id="severe_heat", label="Severe heat", temperature_c=43, humidity_percent=60,
        limitation="Hypothetical temperature and humidity; not an official heatwave warning."),
    "combined_stress": GuidanceScenario(id="combined_stress", label="Rainfall and heat", rainfall_intensity_mm_h=30,
        rainfall_duration_hours=6, temperature_c=41, humidity_percent=60,
        limitation="Hypothetical rainfall, temperature and humidity; air quality is not simulated."),
}


def locality_name(slug: str) -> str:
    zone = find_zone(slug)
    if zone:
        return zone.name
    if slug in LEGACY_CENTERS:
        return "Pune" if slug == "pune" else slug.capitalize()
    return slug


def analysis_context(analysis, *, geography: dict | None = None, priority=None, scenario: GuidanceScenario | None = None) -> dict:
    metrics = analysis.metrics
    provenance = metrics.provenance or {} if metrics else {}
    population = provenance.get("population") or {}
    dem = provenance.get("dem") or {}
    drainage = provenance.get("mapped_waterways") or {}
    metric_summary = ({"population_estimate": metrics.population_estimate,
                       "population_source": population.get("source"), "population_year": population.get("dataset_year"),
                       "population_resolution": population.get("spatial_resolution"),
                       "population_retrieved_at": population.get("retrieved_at_utc"),
                       "slope_mean_degrees": metrics.slope_mean_degrees, "terrain_source": dem.get("source"),
                       "mapped_drain_distance_m": metrics.mapped_drain_distance_m,
                       "drainage_source": drainage.get("source")} if metrics else None)
    infrastructure = ({key: geography.get(key) for key in
                       ("mapped_hospitals", "mapped_schools", "mapped_emergency_services", "road_length_km")}
                      if geography and any(geography.get(key) is not None for key in
                                           ("mapped_hospitals", "mapped_schools", "mapped_emergency_services", "road_length_km")) else None)
    priority_summary = ({"status": priority.status, "score": priority.score,
                         "components": [{"name": item.name, "contribution_points": item.contribution_points}
                                        for item in priority.components]} if priority else None)
    context = {"locality_id": analysis.zone_id, "mode": analysis.mode,
            "scenario": scenario.model_dump(mode="json", exclude_none=True) if scenario else None,
            "hazards": [{"hazard": item.hazard, "status": item.status, "level": item.level,
                         "score": item.score, "score_unit": item.score_unit, "method": item.method,
                         "valid_at": item.data_valid_at.isoformat() if item.data_valid_at and not scenario else None,
                         "forecast_horizon_hours": None if scenario else item.forecast_horizon_hours, "rules_version": item.rules_version,
                         "factors": [{"name": ({"Forecast 24-hour rainfall": "Hypothetical rainfall total",
                                               "Peak hourly rainfall": "Hypothetical rain intensity"}.get(factor.name, factor.name)
                                              if scenario and factor.source == "Hypothetical input" else factor.name),
                                      "value": factor.value, "unit": factor.unit, "source": factor.source}
                                     for factor in item.factors[:4]], "warnings": item.warnings[:4], "sources": item.sources[:4]}
                        for item in analysis.assessments],
            "feature_availability": [item.model_dump() for item in analysis.feature_availability],
            "metrics": metric_summary, "infrastructure": infrastructure, "priority": priority_summary}
    return NugenAnalysisContext.model_validate(context).model_dump(mode="json", exclude_none=True)


def prompt_for(audience: str, name: str, context: dict) -> str:
    task = ("Explain the selected Pune area in calm, citizen-friendly language and give three practical preparedness actions covering only the available hazard evidence."
            if audience == "citizen" else
            "Give a concise authority response brief with three evidence-aware actions that together cover immediate preparedness, public communication, infrastructure review, and monitoring. Explain provisional priority factors without calling them dispatch orders. Do not issue or publish an alert.")
    grounding = ("You are generating preparedness recommendations for a hypothetical climate scenario. The input conditions are simulated for educational and demonstration purposes, not verified current weather or an official emergency. Provide practical, non-alarmist safety actions relevant to the simulated risk factors. Do not claim a real disaster is occurring, an evacuation has been ordered, or an authority has issued an alert. Use only the attached deterministic simulation analysis. "
                 if context.get("mode") == "simulation" else "You are CLIMAGUARD AI using only the attached deterministic live analysis. ")
    return (grounding + task + "\n"
            "Return ONLY a JSON object with keys summary (string), risk_explanation (string), actions (array of exactly three complete unnumbered sentences), limitations (string). "
            "Make summary and limitations complete sentences. Do not add markdown or prose outside the JSON object. "
            "Use no digits, percentages, measured quantities, or new environmental facts anywhere in the response. "
            "Use words like 'fine particles' instead of numbered pollutant names. Do not number the actions. "
            "Do not call the heuristic flood index a probability or the US AQI Indian AQI. "
            "Never say a mapped asset is flooded or a mapped drain has known capacity. Do not invent safe routes or evacuation orders. "
            "If a hazard is unavailable, say its evidence is missing. Treat model estimates as estimates. "
            "The limitations field must state that this is AI guidance, not an official alert or dispatch order. "
            f"Selected area: {name}. Source analysis JSON: {json.dumps(context, ensure_ascii=False, separators=(',', ':'))}")


class NugenGuidanceService:
    def __init__(self, nugen: NugenClient, analysis: AnalysisService, database: SupabaseGateway):
        self.nugen = nugen
        self.analysis = analysis
        self.database = database
        self.cache: dict[str, tuple[datetime, GuidanceResponse]] = {}

    async def _persist(self, response: GuidanceResponse, analysis_hash: str) -> str:
        if not (self.database.settings.configured and self.database.settings.supabase_secret_key):
            return "not_configured"
        try:
            rows = await self.database.table("zones", privileged=True, params={"select": "id", "slug": f"eq.{response.locality_id}", "limit": 1})
            if isinstance(rows, list) and rows:
                zone_uuid = rows[0]["id"]
            else:
                zone = find_zone(response.locality_id)
                if zone is None:
                    return "failed"
                zone_uuid = str(zone.id)
            await self.database.table("ai_recommendations", "POST", privileged=True,
                json={"zone_id": zone_uuid, "recommendation": response.guidance.model_dump_json(), "model_name": "Nugen",
                      "audience": response.audience, "model_id": response.model_id,
                      "inferred_at": response.inferred_at.isoformat(), "source_analysis": response.source_analysis,
                      "analysis_hash": analysis_hash}, prefer="return=minimal")
            return "stored"
        except Exception as exc:
            logging.getLogger("climaguard.nugen").warning("draft_persistence_failed type=%s", type(exc).__name__)
            return "failed"

    async def generate(self, locality_id: str, audience: str, request: GuidanceRequest | None = None) -> GuidanceResponse:
        request = request or GuidanceRequest()
        if coordinates_for(locality_id) is None:
            raise HTTPException(404, "Unknown Pune analysis area.")
        geography = {}
        scenario = None
        if request.mode == "simulation":
            scenario = SCENARIOS[request.scenario_id]
            # No environmental fetch, live measurements or Supabase writes in simulation.
            geography = (await self.analysis.context_all()).get(locality_id, {})
            now = datetime.now(timezone.utc)
            unavailable = StreamError(detail="No current environmental values are used in simulation guidance.")
            bundle = EnvironmentBundle(zone_id=locality_id, coordinate=coordinates_for(locality_id),
                weather=unavailable, air_quality=unavailable, history=unavailable,
                persistence="not_configured", retrieved_at=now)
            inputs = ScenarioRequest(zone_id=locality_id,
                rainfall_intensity_mm_h=scenario.rainfall_intensity_mm_h,
                rainfall_duration_hours=scenario.rainfall_duration_hours or 6,
                temperature_c=scenario.temperature_c, humidity_percent=scenario.humidity_percent)
            analysis = assess_bundle(bundle, self.analysis.metrics_from_context(geography), scenario=inputs)
        else:
            analysis = await self.analysis.zone(locality_id)
            geography = (await self.analysis.context_all()).get(locality_id, {}) if hasattr(self.analysis, "context_all") else {}
        if not any(item.status == "available" for item in analysis.assessments):
            raise NugenFailure("No supported hazard inputs are available for guidance.", "nugen_missing_context")
        priority = priority_result(analysis, geography) if audience == "authority" else None
        context = analysis_context(analysis, geography=geography, priority=priority, scenario=scenario)
        fingerprint = sha256(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()
        cache_key = f"{self.nugen.settings.nugen_model_id}:{audience}:{locality_id}:{fingerprint}"
        cached = self.cache.get(cache_key)
        if cached and (datetime.now(timezone.utc) - cached[0]).total_seconds() < 600:
            return cached[1].model_copy(update={"cache_hit": True})
        name = locality_name(locality_id)
        prompt = prompt_for(audience, name, context)
        inference = await self.nugen.generate(prompt, allowed_numbers=set())
        guidance = inference.guidance
        if scenario:
            import re
            unsafe = re.compile(r"\b(?:evacuat(?:e|ion) (?:now|immediately|has been ordered)|(?:official|authority) alert (?:has been )?issued|(?:flooding|a disaster) is (?:happening|occurring) (?:now|currently))\b", re.IGNORECASE)
            if any(unsafe.search(value) for value in [guidance.summary, guidance.limitations, *guidance.actions]):
                raise NugenFailure("Nugen described the hypothetical scenario as a real emergency; no advice was shown.", "nugen_safety_rejected")
        guidance.risk_explanation = " ".join(
            f"{item['hazard'].replace('_', ' ').title()} {'simulated ' if scenario else ''}screening is {item['level']} and considers "
            f"{', '.join(factor['name'].replace('_', ' ') for factor in item['factors'][:3])}."
            for item in context["hazards"] if item["status"] == "available" and item["factors"]
        ) or "Source data is insufficient to explain hazard screening."
        # Keep hazard labels under deterministic control: provider prose can confuse
        # "high air-quality risk" with "high air quality" or misstate a rule band.
        levels = {item["hazard"]: item["level"] if item["status"] == "available" else "unavailable"
                  for item in context["hazards"]}
        guidance.summary = (f"{'Hypothetical scenario' if scenario else 'Current screening'} for {name}: {levels.get('flood', 'unavailable')} flood risk, "
                            f"{levels.get('heat', 'unavailable')} heat risk, and "
                            f"{levels.get('air_quality', 'unavailable')} air-quality risk. "
                            "Review the Nugen preparedness actions below.")
        response = GuidanceResponse(audience=audience, mode=request.mode,
                                    scenario_id=scenario.id if scenario else None,
                                    scenario_label=scenario.label if scenario else None,
                                    locality_id=locality_id, locality_name=name,
                                    model_id=inference.model_id, provider_request_id=inference.provider_request_id,
                                    inferred_at=inference.inferred_at,
                                    guidance=guidance, source_analysis={**context, "inference": {"status": "success",
                                      "provider_request_id": inference.provider_request_id}}, persistence="not_configured",
                                    disclaimer=("SIMULATION — NOT LIVE CONDITIONS. Hypothetical demonstration guidance, not an official alert or current environmental report."
                                                if scenario else "Nugen-generated preparedness guidance from deterministic live analysis. Not an official alert, validated flood probability, or dispatch order."))
        response.persistence = "not_stored_simulation" if scenario else await self._persist(response, fingerprint)
        self.cache[cache_key] = (response.inferred_at, response)
        return response
