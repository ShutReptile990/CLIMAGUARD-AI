"""Official alert lifecycle. Database triggers and RLS enforce transitions again."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import StringConstraints
from typing import Annotated
from app.core.auth import Principal, require_roles
from app.core.errors import ServiceUnavailable, UpstreamError
from app.integrations.supabase import SupabaseGateway, get_gateway
from app.repositories.supabase import Repository
from app.schemas.alerts import Alert, AlertCreate, AlertEdit, AlertPublish, AlertReview
from app.services.workflow_schema import workflow_columns_ready

router = APIRouter(tags=["alerts"])
FIELDS = ("id,title,body,level,localityId:locality_id,source,status,approvedAt:approved_at,createdAt:created_at,"
          "hazard,submittedAt:submitted_at,reviewedAt:reviewed_at,reviewNote:review_note,"
          "publishedAt:published_at,expiresAt:expires_at,createdBy:created_by,approvedBy:approved_by")
LEGACY_FIELDS = "id,title,body,level,localityId:locality_id,source,status,approvedAt:approved_at,createdAt:created_at"


def as_alert(row: dict) -> Alert:
    names = {"localityId": "locality_id", "approvedAt": "approved_at", "createdAt": "created_at",
             "submittedAt": "submitted_at", "reviewedAt": "reviewed_at", "reviewNote": "review_note",
             "publishedAt": "published_at", "expiresAt": "expires_at", "createdBy": "created_by", "approvedBy": "approved_by"}
    data = {**row, **{target: row[source] for target, source in names.items() if source in row and target not in row}}
    return Alert.model_validate({key: data[key] for key in Alert.model_fields if key in data})


async def _list(gateway: SupabaseGateway, *, token: str | None = None, filters: dict | None = None,
                limit: int = 50) -> list[dict]:
    repo = Repository(gateway, token)
    try:
        return await repo.list("alerts", FIELDS, filters=filters, limit=limit, order="created_at.desc")
    except UpstreamError:
        return await repo.list("alerts", LEGACY_FIELDS, filters=filters, limit=limit, order="created_at.desc")


async def public_alerts(gateway: SupabaseGateway, locality_id: str | None = None, limit: int = 50) -> list[Alert]:
    filters = {"status": "eq.published"}
    if locality_id:
        filters["locality_id"] = f"eq.{locality_id}"
    now = datetime.now(timezone.utc)
    try:
        rows = await Repository(gateway).list("alerts", FIELDS,
            filters={**filters, "or": f"(expires_at.is.null,expires_at.gt.{now.isoformat()})"},
            limit=limit, order="created_at.desc")
    except UpstreamError:
        rows = await Repository(gateway).list("alerts", LEGACY_FIELDS, filters=filters, limit=limit, order="created_at.desc")
    return [alert for row in rows if (alert := as_alert(row)).expiresAt is None or alert.expiresAt > now]


@router.get("/alerts", response_model=list[Alert])
async def list_alerts(gateway: SupabaseGateway = Depends(get_gateway),
                      locality_id: Annotated[str | None, StringConstraints(pattern="^[a-z0-9-]+$")] = None,
                      limit: int = Query(default=50, ge=1, le=200)):
    return await public_alerts(gateway, locality_id, limit)


@router.get("/alerts/drafts", response_model=list[Alert])
async def list_drafts(user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await _list(gateway, token=user.token, filters={"status": "in.(draft,pending_approval,approved,rejected)"}, limit=200)
    return [as_alert(row) for row in rows]


@router.get("/alerts/archive", response_model=list[Alert])
async def alert_archive(user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await _list(gateway, token=user.token, filters={"status": "in.(published,expired,withdrawn)"}, limit=200)
    return [as_alert(row) for row in rows]


@router.post("/alerts", response_model=Alert, status_code=201)
async def create_alert(body: AlertCreate, user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    repo = Repository(gateway, user.token)
    zones = await repo.list("zones", "id", filters={"slug": f"eq.{body.localityId}"}, limit=1)
    if not zones:
        raise HTTPException(422, "Unknown locality.")
    ready = await workflow_columns_ready(gateway, "alerts", "hazard", user.token)
    if not ready and body.hazard != "other":
        raise ServiceUnavailable("Hazard-specific alert drafts require database migration 008.")
    payload = {"zone_id": zones[0]["id"], "locality_id": body.localityId, "title": body.title,
        "body": body.body, "level": body.level.value, "source": body.source,
        "status": "draft", "created_by": str(user.id)}
    if ready:
        payload["hazard"] = body.hazard
    row = await repo.insert("alerts", payload)
    return as_alert(row)


@router.patch("/alerts/{alert_id}", response_model=Alert)
async def edit_alert(alert_id: UUID, body: AlertEdit, user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    if not await workflow_columns_ready(gateway, "alerts", "hazard", user.token):
        raise ServiceUnavailable("Draft editing requires database migration 008.")
    current = await Repository(gateway, user.token).one("alerts", alert_id)
    if current is None or current.get("created_by") != str(user.id) or current.get("status") != "draft":
        raise HTTPException(403, "Only the author may edit an unsubmitted draft.")
    return await _transition(gateway, user, alert_id, "draft", {
        "title": body.title, "body": body.body, "level": body.level.value,
        "source": body.source, "hazard": body.hazard})


async def _transition(gateway: SupabaseGateway, user: Principal, alert_id: UUID, expected: str, data: dict) -> Alert:
    rows = await gateway.table("alerts", "PATCH", token=user.token,
        params={"id": f"eq.{alert_id}", "status": f"eq.{expected}"}, json=data, prefer="return=representation")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(409, "Alert changed or is not in the required state.")
    return as_alert(rows[0])


@router.post("/alerts/{alert_id}/submit", response_model=Alert)
async def submit_alert(alert_id: UUID, user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    if not await workflow_columns_ready(gateway, "alerts", "submitted_at", user.token):
        raise ServiceUnavailable("Alert approval requires database migration 008.")
    current = await Repository(gateway, user.token).one("alerts", alert_id)
    if current is None or current.get("created_by") != str(user.id):
        raise HTTPException(403, "Only the draft author may submit it for review.")
    return await _transition(gateway, user, alert_id, "draft", {"status": "pending_approval", "submitted_at": datetime.now(timezone.utc).isoformat()})


@router.post("/alerts/{alert_id}/review", response_model=Alert)
async def review_alert(alert_id: UUID, body: AlertReview, user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    if not await workflow_columns_ready(gateway, "alerts", "reviewed_at", user.token):
        raise ServiceUnavailable("Alert approval requires database migration 008.")
    current = await Repository(gateway, user.token).one("alerts", alert_id)
    if current is None or current.get("status") != "pending_approval":
        raise HTTPException(409, "Only pending alerts can be reviewed.")
    if current.get("created_by") == str(user.id):
        raise HTTPException(403, "A different authority reviewer is required.")
    if not body.approve and not (body.reason or "").strip():
        raise HTTPException(422, "A rejection reason is required.")
    now = datetime.now(timezone.utc).isoformat()
    return await _transition(gateway, user, alert_id, "pending_approval", {
        "status": "approved" if body.approve else "rejected", "approved_by": str(user.id),
        "approved_at": now if body.approve else None, "reviewed_at": now,
        "review_note": body.reason.strip() if body.reason else None})


@router.post("/alerts/{alert_id}/publish", response_model=Alert)
async def publish_alert(alert_id: UUID, body: AlertPublish, user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    if not await workflow_columns_ready(gateway, "alerts", "expires_at", user.token):
        raise ServiceUnavailable("Alert publication requires database migration 008.")
    now = datetime.now(timezone.utc)
    expiry = body.expires_at
    if expiry.tzinfo is None or not now < expiry.astimezone(timezone.utc) <= now + timedelta(days=30):
        raise HTTPException(422, "Expiry must be timezone-aware and within the next 30 days.")
    return await _transition(gateway, user, alert_id, "approved", {
        "status": "published", "published_at": now.isoformat(), "expires_at": expiry.isoformat()})


@router.post("/alerts/{alert_id}/withdraw", response_model=Alert)
async def withdraw_alert(alert_id: UUID, user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    return await _transition(gateway, user, alert_id, "published", {"status": "withdrawn"})


@router.post("/alerts/{alert_id}/expire", response_model=Alert)
async def expire_alert(alert_id: UUID, user: Principal = Depends(require_roles("authority", "admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    if not await workflow_columns_ready(gateway, "alerts", "expires_at", user.token):
        raise ServiceUnavailable("Alert expiry tracking requires database migration 008.")
    current = await Repository(gateway, user.token).one("alerts", alert_id, "id,status,expires_at")
    if not current or current.get("status") != "published":
        raise HTTPException(409, "Only published alerts can expire.")
    if not current.get("expires_at") or datetime.fromisoformat(current["expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc):
        raise HTTPException(422, "This alert has not reached its expiry time.")
    return await _transition(gateway, user, alert_id, "published", {"status": "expired"})
