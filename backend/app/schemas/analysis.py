from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

Hazard = Literal["flood", "heat", "air_quality"]
Level = Literal["low", "moderate", "high", "severe", "unavailable"]


class Contribution(BaseModel):
    name: str
    value: float | None = None
    unit: str | None = None
    contribution_points: float | None = None
    source: str


class HazardAssessment(BaseModel):
    hazard: Hazard
    status: Literal["available", "unavailable"]
    method: Literal["heuristic_index", "rule_based", "us_aqi_category"]
    level: Level
    score: float | None = None
    score_unit: str | None = None
    category: str | None = None
    factors: list[Contribution] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    precautions: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    assessed_at: datetime
    data_valid_at: datetime | None = None
    forecast_horizon_hours: int | None = None
    rules_version: str
    simulated: bool = False


class ZoneMetrics(BaseModel):
    dem_mean_m: float | None = None
    slope_mean_degrees: float | None = Field(default=None, ge=0, le=90)
    drainage_index: float | None = Field(default=None, ge=0, le=1)
    historical_flood_exposure: float | None = Field(default=None, ge=0, le=1)
    population_estimate: int | None = Field(default=None, ge=0)
    vulnerability_index: float | None = Field(default=None, ge=0, le=1)
    mapped_waterway_distance_m: float | None = Field(default=None, ge=0)
    mapped_drain_distance_m: float | None = Field(default=None, ge=0)
    mapped_culvert_count: int | None = Field(default=None, ge=0)
    provenance: dict | None = None


class FeatureAvailability(BaseModel):
    name: str
    status: Literal["available", "partial", "unavailable"]
    source: str
    limitation: str


class AnalysisResponse(BaseModel):
    zone_id: str
    mode: Literal["live", "simulation"]
    assessments: list[HazardAssessment]
    metrics: ZoneMetrics | None
    metrics_status: Literal["available", "unavailable"]
    feature_availability: list[FeatureAvailability] = Field(default_factory=list)
    assessed_at: datetime
    disclaimer: str


class ExposureResponse(BaseModel):
    zone_id: str
    status: Literal["available", "partial", "unavailable"]
    mapped_hospitals: int | None = None
    mapped_schools: int | None = None
    mapped_emergency_services: int | None = None
    road_length_km: float | None = None
    population_in_cell: int | None = None
    potential_population_exposure: int | None = None
    method: str
    assumptions: list[str]
    warnings: list[str]


class PriorityComponent(BaseModel):
    name: str
    normalized: float | None = Field(default=None, ge=0, le=1)
    weight: float
    contribution_points: float | None = None


class PriorityResult(BaseModel):
    zone_id: str
    rank: int | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    status: Literal["provisional", "unavailable"]
    components: list[PriorityComponent]
    warnings: list[str]
    version: str
    simulated: bool = False
    hazards: dict[str, dict[str, str | float | None]] = Field(default_factory=dict)


class ComparisonResponse(BaseModel):
    mode: Literal["live", "simulation"]
    zones: list[PriorityResult]
    assessed_at: datetime
    disclaimer: str


class ScenarioRequest(BaseModel):
    zone_id: str = Field(pattern=r"^[a-z0-9-]+$")
    rainfall_intensity_mm_h: float | None = Field(default=None, ge=0, le=250)
    rainfall_duration_hours: int = Field(default=6, ge=1, le=24)
    temperature_c: float | None = Field(default=None, ge=-10, le=60)
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    drainage_index: float | None = Field(default=None, ge=0, le=1)


class SimulationResponse(BaseModel):
    mode: Literal["simulation"] = "simulation"
    inputs: ScenarioRequest
    baseline: AnalysisResponse
    simulated: AnalysisResponse
    priority: PriorityResult
    disclaimer: str
