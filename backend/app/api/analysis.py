from fastapi import APIRouter, Depends, Path
from app.schemas.analysis import AnalysisResponse, ComparisonResponse, ExposureResponse, ScenarioRequest, SimulationResponse
from app.services.analysis import AnalysisService, get_analysis_service

router = APIRouter(prefix="/analysis", tags=["transparent analysis"])


@router.get("/compare", response_model=ComparisonResponse)
async def compare(service: AnalysisService = Depends(get_analysis_service)):
    return await service.compare()


@router.get("/{zone_id}", response_model=AnalysisResponse)
async def zone_analysis(zone_id: str = Path(pattern=r"^[a-z0-9-]+$"), service: AnalysisService = Depends(get_analysis_service)):
    return await service.zone(zone_id)


@router.get("/{zone_id}/exposure", response_model=ExposureResponse)
async def exposure(zone_id: str = Path(pattern=r"^[a-z0-9-]+$"), service: AnalysisService = Depends(get_analysis_service)):
    return await service.exposure(zone_id)


@router.post("/simulate", response_model=SimulationResponse)
async def simulate(request: ScenarioRequest, service: AnalysisService = Depends(get_analysis_service)):
    return await service.simulate(request)
