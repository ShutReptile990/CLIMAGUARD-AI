"""Explicit Nugen inference routes; authority output is role protected."""

from fastapi import APIRouter, Depends, Path, Request
from app.core.auth import Principal, require_roles
from app.schemas.nugen import GuidanceResponse, NugenStatus
from app.services.nugen_guidance import NugenGuidanceService

router = APIRouter(prefix="/nugen", tags=["Nugen guidance"])


def get_service(request: Request) -> NugenGuidanceService:
    return request.app.state.nugen_guidance


@router.get("/status", response_model=NugenStatus)
async def status(request: Request):
    return request.app.state.nugen.status()


@router.post("/citizen/{locality_id}", response_model=GuidanceResponse)
async def citizen_guidance(locality_id: str = Path(pattern=r"^[a-z0-9-]+$"), service: NugenGuidanceService = Depends(get_service)):
    return await service.generate(locality_id, "citizen")


@router.post("/authority/{locality_id}", response_model=GuidanceResponse)
async def authority_guidance(locality_id: str = Path(pattern=r"^[a-z0-9-]+$"),
                             _user: Principal = Depends(require_roles("authority", "admin")),
                             service: NugenGuidanceService = Depends(get_service)):
    return await service.generate(locality_id, "authority")
