from datetime import datetime
from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Role(StrEnum):
    citizen = "citizen"
    authority = "authority"
    admin = "admin"


class Unavailable(StrictModel):
    status: str = "unavailable"
    detail: str


class Zone(StrictModel):
    id: UUID
    slug: str
    name: str
    city: str
    created_at: datetime


class Health(StrictModel):
    status: str
    service: str
    database_configured: bool
