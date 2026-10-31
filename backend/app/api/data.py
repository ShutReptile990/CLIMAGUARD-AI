from fastapi import APIRouter, Depends, Query
from uuid import UUID
from app.core.errors import ServiceUnavailable
from app.integrations.supabase import SupabaseGateway, get_gateway
from app.repositories.supabase import Repository
from app.schemas.common import Zone
from app.schemas.data import ClimateObservation, RiskPrediction, ImpactAssessment, PriorityAssessment, Recommendation

router = APIRouter(tags=["climate intelligence"])


@router.get("/zones", response_model=list[Zone])
async def zones(gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await Repository(gateway).list("zones", "id,slug,name,city,created_at", order="name.asc")
    return [Zone.model_validate(row) for row in rows]


@router.get("/climate", response_model=list[ClimateObservation])
async def climate(zone_id: UUID, gateway: SupabaseGateway = Depends(get_gateway), limit: int = Query(default=50, ge=1, le=200)):
    rows = await Repository(gateway).list("climate_observations", "id,zone_id,observed_at,temperature_c,humidity_percent,rainfall_mm,aqi,source", filters={"zone_id": f"eq.{zone_id}"}, limit=limit, order="observed_at.desc")
    if not rows:
        raise ServiceUnavailable("Verified climate observations are not available for this zone.")
    return [ClimateObservation.model_validate(row) for row in rows]


@router.get("/predictions", response_model=list[RiskPrediction])
async def predictions(zone_id: UUID, gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await Repository(gateway).list("risk_predictions", "id,zone_id,hazard,level,score,predicted_at,model_version,source", filters={"zone_id": f"eq.{zone_id}"}, order="predicted_at.desc")
    if not rows:
        raise ServiceUnavailable("Validated risk predictions are not available for this zone.")
    return [RiskPrediction.model_validate(row) for row in rows]


@router.get("/impact", response_model=list[ImpactAssessment])
async def impact(zone_id: UUID, gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await Repository(gateway).list("impact_assessments", "id,zone_id,prediction_id,population_exposed,infrastructure_exposed,assessed_at,source", filters={"zone_id": f"eq.{zone_id}"}, order="assessed_at.desc")
    if not rows:
        raise ServiceUnavailable("Validated impact assessments are not available for this zone.")
    return [ImpactAssessment.model_validate(row) for row in rows]


@router.get("/priorities", response_model=list[PriorityAssessment])
async def priorities(zone_id: UUID, gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await Repository(gateway).list("priority_assessments", "id,zone_id,score,rank,rationale,assessed_at,source", filters={"zone_id": f"eq.{zone_id}"}, order="assessed_at.desc")
    if not rows:
        raise ServiceUnavailable("Validated priority assessments are not available for this zone.")
    return [PriorityAssessment.model_validate(row) for row in rows]


@router.get("/recommendations", response_model=list[Recommendation])
async def recommendations(zone_id: UUID, gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await Repository(gateway).list("ai_recommendations", "id,zone_id,recommendation,model_name,created_at,approved_at", filters={"zone_id": f"eq.{zone_id}", "approved_at": "not.is.null"}, order="created_at.desc")
    if not rows:
        raise ServiceUnavailable("Approved Nugen recommendations are not available for this zone.")
    return [Recommendation.model_validate(row) for row in rows]
