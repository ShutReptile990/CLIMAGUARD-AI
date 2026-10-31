from datetime import datetime
from uuid import UUID
from pydantic import Field
from app.schemas.common import StrictModel, Role


class Profile(StrictModel):
    id: UUID
    display_name: str | None
    role: Role
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(StrictModel):
    display_name: str | None = Field(default=None, max_length=120)


class RoleAssignment(StrictModel):
    role: Role
