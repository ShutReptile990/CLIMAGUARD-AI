from datetime import datetime
from enum import StrEnum
from uuid import UUID
from pydantic import Field
from app.schemas.common import StrictModel


class AlertLevel(StrEnum):
    low = "low"
    moderate = "moderate"
    high = "high"
    severe = "severe"


class AlertStatus(StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    published = "published"
    expired = "expired"
    withdrawn = "withdrawn"


class AlertCreate(StrictModel):
    title: str = Field(min_length=5, max_length=160)
    body: str = Field(min_length=20, max_length=4000)
    level: AlertLevel
    localityId: str = Field(min_length=2, max_length=80, pattern="^[a-z0-9-]+$")
    source: str = Field(min_length=3, max_length=300)
    hazard: str = Field(default="other", pattern="^(flood|heat|air_quality|other)$")
    incidentId: UUID | None = None


class AlertEdit(StrictModel):
    title: str = Field(min_length=5, max_length=160)
    body: str = Field(min_length=20, max_length=4000)
    level: AlertLevel
    source: str = Field(min_length=3, max_length=300)
    hazard: str = Field(default="other", pattern="^(flood|heat|air_quality|other)$")


class AlertReview(StrictModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=1000)


class AlertPublish(StrictModel):
    expires_at: datetime


class Alert(StrictModel):
    id: UUID
    title: str
    body: str
    level: AlertLevel
    localityId: str
    source: str
    status: AlertStatus
    approvedAt: datetime | None
    createdAt: datetime
    hazard: str = "other"
    submittedAt: datetime | None = None
    reviewedAt: datetime | None = None
    reviewNote: str | None = None
    publishedAt: datetime | None = None
    expiresAt: datetime | None = None
    createdBy: UUID | None = None
    approvedBy: UUID | None = None
    incidentId: UUID | None = None


class AlertHistoryEntry(StrictModel):
    actorId: UUID | None
    createdAt: datetime
    action: str
    oldStatus: str | None = None
    newStatus: str | None = None
    changedFields: list[str] = Field(default_factory=list)
