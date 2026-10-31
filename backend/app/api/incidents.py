from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import Principal, current_user, require_roles
from app.integrations.supabase import SupabaseGateway, get_gateway
from app.repositories.supabase import Repository
from app.schemas.incidents import Incident, IncidentCreate, IncidentHistoryEntry, IncidentReview, IncidentUpdate
from app.core.errors import ServiceUnavailable, SupabaseRequestError, UpstreamError
from app.services.workflow_schema import workflow_columns_ready

router = APIRouter(tags=["incidents"])
FIELDS = "id,localityId:locality_id,category,description,contact,createdAt:created_at,status,review_note,severity,image_path,reviewed_at,reviewed_by"
LEGACY_FIELDS = "id,localityId:locality_id,category,description,contact,createdAt:created_at,status,review_note"


def as_incident(row: dict) -> Incident:
    row = {**row, "localityId": row.get("localityId", row.get("locality_id")), "createdAt": row.get("createdAt", row.get("created_at"))}
    row = {key: row[key] for key in Incident.model_fields if key in row}
    return Incident.model_validate(row)


@router.get("/incidents", response_model=list[Incident])
async def list_incidents(user: Principal = Depends(current_user), gateway: SupabaseGateway = Depends(get_gateway), limit: int = Query(default=50, ge=1, le=200)):
    filters = {"reporter_id": f"eq.{user.id}"} if user.role == "citizen" else None
    try:
        rows = await Repository(gateway, user.token).list("incident_reports", FIELDS, filters=filters, limit=limit, order="created_at.desc")
    except UpstreamError:
        rows = await Repository(gateway, user.token).list("incident_reports", LEGACY_FIELDS, filters=filters, limit=limit, order="created_at.desc")
    return [as_incident(row) for row in rows]


@router.post("/incidents", response_model=Incident, status_code=201)
async def create_incident(body: IncidentCreate, user: Principal = Depends(current_user), gateway: SupabaseGateway = Depends(get_gateway)):
    if body.image_path and not body.image_path.startswith(f"{user.id}/"):
        raise HTTPException(422, "Image must belong to the authenticated reporter.")
    workflow_ready = await workflow_columns_ready(gateway, "incident_reports", "severity", user.token)
    if not workflow_ready and (body.image_path or body.severity != "moderate" or body.category.value not in {"flood", "heat", "air_quality", "other"}):
        raise ServiceUnavailable("Incident severity, categories and images require database migration 008.")
    repo = Repository(gateway, user.token)
    zones = await repo.list("zones", "id", filters={"slug": f"eq.{body.localityId}"}, limit=1)
    if not zones:
        raise HTTPException(422, "Unknown locality.")
    payload = {"zone_id": zones[0]["id"], "locality_id": body.localityId, "reporter_id": str(user.id), "category": body.category.value, "description": body.description, "contact": body.contact}
    if workflow_ready:
        payload.update({"severity": body.severity, "image_path": body.image_path})
    row = await repo.insert("incident_reports", payload)
    return as_incident(row)


@router.get("/incidents/{incident_id}/history", response_model=list[IncidentHistoryEntry])
async def incident_history(incident_id: UUID, user: Principal = Depends(current_user), gateway: SupabaseGateway = Depends(get_gateway)):
    current = await Repository(gateway, user.token).one("incident_reports", incident_id, "id,reporter_id")
    if current is None or (user.role == "citizen" and current.get("reporter_id") != str(user.id)):
        raise HTTPException(404, "Incident not found.")
    rows = await gateway.table("audit_logs", privileged=True,
        params={"select": "actor_id,created_at,details", "entity_type": "eq.incident_reports",
                "entity_id": f"eq.{incident_id}", "order": "created_at.asc", "limit": 100})
    return [IncidentHistoryEntry(actor_id=row.get("actor_id") if user.role != "citizen" else None,
        created_at=row["created_at"], old_status=row["details"].get("old_status", "unknown"),
        new_status=row["details"].get("new_status", "unknown")) for row in rows or []]


@router.patch("/incidents/{incident_id}", response_model=Incident)
async def edit_incident(incident_id: UUID, body: IncidentUpdate, user: Principal = Depends(current_user), gateway: SupabaseGateway = Depends(get_gateway)):
    repo = Repository(gateway, user.token)
    current = await repo.one("incident_reports", incident_id)
    if current is None or current.get("reporter_id") != str(user.id) or current.get("status") != "submitted":
        raise HTTPException(403, "Only your submitted reports can be edited.")
    row = await repo.update("incident_reports", incident_id, {"description": body.description})
    if row is None:
        raise HTTPException(404, "Incident not found.")
    return as_incident(row)


@router.delete("/incidents/{incident_id}", status_code=204)
async def delete_incident(incident_id: UUID, user: Principal = Depends(current_user), gateway: SupabaseGateway = Depends(get_gateway)):
    repo = Repository(gateway, user.token)
    current = await repo.one("incident_reports", incident_id)
    if current is None or current.get("reporter_id") != str(user.id) or current.get("status") != "submitted":
        raise HTTPException(403, "Only your submitted reports can be deleted.")
    await repo.delete("incident_reports", incident_id)


@router.patch("/incidents/{incident_id}/review", response_model=Incident)
async def review_incident(incident_id: UUID, body: IncidentReview, reviewer: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    if body.status not in ("under_review", "resolved", "rejected"):
        raise HTTPException(422, "Invalid review status.")
    if body.status == "rejected" and not (body.review_note or "").strip():
        raise HTTPException(422, "A rejection reason is required.")
    expected = "submitted" if body.status == "under_review" else "under_review"
    current = await Repository(gateway, reviewer.token).one("incident_reports", incident_id, "id,status")
    if current is None:
        raise HTTPException(404, "Incident not found.")
    if current["status"] != expected:
        raise HTTPException(409, "Report is not in the required review state. Refresh the queue.")
    workflow_ready = await workflow_columns_ready(gateway, "incident_reports", "reviewed_at", reviewer.token)
    if not workflow_ready:
        raise ServiceUnavailable("Incident review requires the migration 008 review fields.")
    changes = {"status": body.status.value, "review_note": body.review_note.strip() if body.review_note else None,
               "reviewed_by": str(reviewer.id), "reviewed_at": datetime.now(timezone.utc).isoformat()}
    try:
        rows = await gateway.table("incident_reports", "PATCH", token=reviewer.token,
            params={"id": f"eq.{incident_id}", "status": f"eq.{expected}"},
            json=changes, prefer="return=representation")
    except SupabaseRequestError as exc:
        if exc.code == "42725":
            raise ServiceUnavailable("Incident review needs database migration 009 to repair the PostGIS location guard.") from exc
        if exc.code in {"P0001", "23514"}:
            raise HTTPException(409, "Report review was rejected by the database transition guard. Refresh the queue.") from exc
        raise
    if not isinstance(rows, list) or not rows:
        raise HTTPException(409, "Report changed or is not in the required review state.")
    row = rows[0]
    return as_incident(row)
