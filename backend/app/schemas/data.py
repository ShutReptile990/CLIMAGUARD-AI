from datetime import datetime
from uuid import UUID
from pydantic import Field
from app.schemas.common import StrictModel


class ClimateObservation(StrictModel):
    id: UUID
    zone_id: UUID
    observed_at: datetime
    temperature_c: float | None
    humidity_percent: float | None
    rainfall_mm: float | None
    aqi: int | None
    source: str


class RiskPrediction(StrictModel):
    id: UUID
    zone_id: UUID
    hazard: str
    level: str
    score: float
    predicted_at: datetime
    model_version: str
    source: str


class ImpactAssessment(StrictModel):
    id: UUID
    zone_id: UUID
    prediction_id: UUID
    population_exposed: int | None
    infrastructure_exposed: int | None
    assessed_at: datetime
    source: str


class PriorityAssessment(StrictModel):
    id: UUID
    zone_id: UUID
    score: float
    rank: int | None
    rationale: str
    assessed_at: datetime
    source: str


class Recommendation(StrictModel):
    id: UUID
    zone_id: UUID
    recommendation: str
    model_name: str
    created_at: datetime
    approved_at: datetime | None
