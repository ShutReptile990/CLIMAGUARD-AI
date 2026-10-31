from fastapi import APIRouter, Depends, Path
from app.schemas.environment import EnvironmentBundle
from app.services.environment import EnvironmentService, get_environment_service

router = APIRouter(tags=["environment"])


@router.get("/environment/{zone_id}", response_model=EnvironmentBundle)
async def environment(zone_id: str = Path(pattern="^[a-z0-9-]+$"), service: EnvironmentService = Depends(get_environment_service)):
    return await service.bundle(zone_id)
