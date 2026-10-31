"""Validated Nugen provider and public guidance contracts."""

from datetime import datetime
from typing import Literal
import re
from pydantic import BaseModel, Field, ValidationInfo, field_validator


NUMERIC_CLAIM = re.compile(r"(?<![A-Za-z\d])\d+(?:\.\d+)?")
IDENTIFIERS = re.compile(r"\b(?:PM\s*2\.5|PM\s*10|[A-C][1-3])\b", re.IGNORECASE)


def unsupported_number(value: str, allowed: set[str]) -> bool:
    prose = IDENTIFIERS.sub("", value)
    return "%" in prose or any(token not in allowed for token in NUMERIC_CLAIM.findall(prose))


class NugenMessage(BaseModel):
    content: str = Field(min_length=20, max_length=6000)


class NugenChoice(BaseModel):
    message: NugenMessage
    finish_reason: str | None = None


class NugenChatResponse(BaseModel):
    id: str | None = None
    model: str
    choices: list[NugenChoice] = Field(min_length=1)


class NugenGuidanceText(BaseModel):
    summary: str = Field(min_length=20, max_length=700)
    risk_explanation: str | None = Field(default=None, min_length=20, max_length=700)
    actions: list[str] = Field(min_length=2, max_length=6)
    limitations: str = Field(min_length=15, max_length=500)

    @field_validator("summary", "risk_explanation", "limitations")
    @classmethod
    def no_numeric_measurements(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        allowed = (info.context or {}).get("allowed_numbers", set())
        if unsupported_number(value, allowed):
            raise ValueError("Nugen text contains an unsupported numerical claim")
        return value.strip()

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, values: list[str], info: ValidationInfo) -> list[str]:
        allowed = (info.context or {}).get("allowed_numbers", set())
        if any(not 12 <= len(value.strip()) <= 400 or unsupported_number(value, allowed) for value in values):
            raise ValueError("Nugen actions contain an unsupported numerical claim")
        return [value.strip() for value in values]


class NugenInference(BaseModel):
    guidance: NugenGuidanceText
    model_id: str
    provider_request_id: str | None = None
    inferred_at: datetime


class NugenMetricInput(BaseModel):
    population_estimate: int | None = None
    population_source: str | None = None
    population_year: int | None = None
    population_resolution: str | None = None
    population_retrieved_at: str | None = None
    slope_mean_degrees: float | None = None
    terrain_source: str | None = None
    mapped_drain_distance_m: float | None = None
    drainage_source: str | None = None
    drainage_limitation: str = "Mapped proximity is not verified drainage capacity."


class NugenInfrastructureInput(BaseModel):
    mapped_hospitals: int | None = None
    mapped_schools: int | None = None
    mapped_emergency_services: int | None = None
    road_length_km: float | None = None
    limitation: str = "Mapped co-location does not establish flood damage or safe routes."


class NugenPriorityComponentInput(BaseModel):
    name: str
    contribution_points: float | None = None


class NugenPriorityInput(BaseModel):
    status: str
    score: float | None = None
    components: list[NugenPriorityComponentInput]
    limitation: str = "Provisional screening rank is not a dispatch order."


class NugenFactorInput(BaseModel):
    name: str
    value: float | None = None
    unit: str | None = None
    source: str


class NugenHazardInput(BaseModel):
    hazard: Literal["flood", "heat", "air_quality"]
    status: Literal["available", "unavailable"]
    level: str
    score: float | None = None
    score_unit: str | None = None
    method: str
    valid_at: str | None = None
    forecast_horizon_hours: int | None = None
    rules_version: str
    factors: list[NugenFactorInput]
    warnings: list[str]
    sources: list[str]


class NugenFeatureInput(BaseModel):
    name: str
    status: Literal["available", "partial", "unavailable"]
    source: str
    limitation: str


class NugenAnalysisContext(BaseModel):
    locality_id: str
    mode: Literal["live"]
    hazards: list[NugenHazardInput] = Field(min_length=3, max_length=3)
    feature_availability: list[NugenFeatureInput]
    metrics: NugenMetricInput | None = None
    infrastructure: NugenInfrastructureInput | None = None
    priority: NugenPriorityInput | None = None


class NugenStatus(BaseModel):
    configured: bool
    available: bool
    model_id: str | None = None
    last_success_at: datetime | None = None
    detail: str


class GuidanceResponse(BaseModel):
    status: Literal["available"] = "available"
    audience: Literal["citizen", "authority"]
    locality_id: str
    locality_name: str
    model_id: str
    provider_request_id: str | None = None
    inferred_at: datetime
    guidance: NugenGuidanceText
    source_analysis: dict
    persistence: Literal["stored", "failed", "not_configured"]
    cache_hit: bool = False
    disclaimer: str
