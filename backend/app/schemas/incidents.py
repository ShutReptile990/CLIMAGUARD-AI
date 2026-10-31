from datetime import datetime
from enum import StrEnum
from uuid import UUID
from pydantic import Field
from app.schemas.common import StrictModel


class Category(StrEnum):
    flood = "flood"
    waterlogging = "waterlogging"
    blocked_road = "blocked_road"
    fallen_tree = "fallen_tree"
    heat = "heat"
    air_quality = "air_quality"
    other = "other"


class IncidentStatus(StrEnum):
    submitted = "submitted"
    under_review = "under_review"
    resolved = "resolved"
    rejected = "rejected"


class IncidentCreate(StrictModel):
    localityId: str = Field(min_length=2, max_length=80, pattern="^[a-z0-9-]+$")
    category: Category
    description: str = Field(min_length=20, max_length=2000)
    contact: str | None = Field(default=None, max_length=120)
    severity: str = Field(default="moderate", pattern="^(low|moderate|high|severe)$")
    image_path: str | None = Field(default=None, max_length=180, pattern=r"^[0-9a-f-]{36}/[0-9a-f-]{36}\.(jpg|jpeg|png|webp)$")


class IncidentUpdate(StrictModel):
    description: str = Field(min_length=20, max_length=2000)


class IncidentReview(StrictModel):
    status: IncidentStatus
    review_note: str | None = Field(default=None, max_length=1000)


class Incident(StrictModel):
    id: UUID
    localityId: str
    category: Category
    description: str
    contact: str | None
    createdAt: datetime
    status: IncidentStatus
    review_note: str | None = None
    severity: str = "moderate"
    image_path: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None


class IncidentHistoryEntry(StrictModel):
    created_at: datetime
    old_status: str
    new_status: str
    actor_id: UUID | None = None
