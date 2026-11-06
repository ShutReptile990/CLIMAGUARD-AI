"""Explicit Nugen inference routes; authority output is role protected."""

from fastapi import APIRouter, Depends, Path, Request
from app.core.auth import Principal, require_roles
from app.schemas.nugen import GuidanceRequest, GuidanceResponse, GuidanceScenario, NugenStatus
from app.services.nugen_guidance import NugenGuidanceService, SCENARIOS

router = APIRouter(prefix="/nugen", tags=["Nugen guidance"])


def get_service(request: Request) -> NugenGuidanceService:
    return request.app.state.nugen_guidance


@router.get("/status", response_model=NugenStatus)
async def status(request: Request):
    return request.app.state.nugen.status()


@router.get("/scenarios", response_model=list[GuidanceScenario])
async def scenarios():
    return list(SCENARIOS.values())


@router.post("/citizen/{locality_id}", response_model=GuidanceResponse)
async def citizen_guidance(locality_id: str = Path(pattern=r"^[a-z0-9-]+$"), body: GuidanceRequest = GuidanceRequest(), service: NugenGuidanceService = Depends(get_service)):
    return await service.generate(locality_id, "citizen", body)


@router.post("/authority/{locality_id}", response_model=GuidanceResponse)
async def authority_guidance(locality_id: str = Path(pattern=r"^[a-z0-9-]+$"),
                             body: GuidanceRequest = GuidanceRequest(),
                             _user: Principal = Depends(require_roles("authority", "admin")),
                             service: NugenGuidanceService = Depends(get_service)):
    return await service.generate(locality_id, "authority", body)
