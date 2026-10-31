"""DEMO unit fixtures for workflow transitions; no live records are created."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.api.alerts import AlertPublish, AlertReview, public_alerts, publish_alert, review_alert, submit_alert
from app.api.incidents import create_incident, review_incident
from app.core.auth import Principal
from app.core.errors import ServiceUnavailable, SupabaseRequestError, UpstreamError
from app.main import app
from app.integrations.supabase import get_gateway
from app.schemas.incidents import IncidentCreate, IncidentReview


def principal(role="authority"):
    return Principal(id=uuid4(), role=role, token="DEMO-token")


def alert_row(*, expiry=None):
    return {"id": str(uuid4()), "title": "Verified weather advisory", "body": "Follow local authority updates and prepare for changing conditions.",
            "level": "moderate", "localityId": "pune-grid-r2-c2", "source": "Verified source", "status": "published",
            "approvedAt": datetime.now(timezone.utc).isoformat(), "createdAt": datetime.now(timezone.utc).isoformat(),
            "expiresAt": expiry.isoformat() if expiry else None}


def test_public_alerts_exclude_expired_records():
    class Database:
        async def table(self, table, method="GET", **kwargs):
            assert table == "alerts" and "expires_at" in kwargs["params"]["or"]
            return [alert_row(expiry=datetime.now(timezone.utc) - timedelta(minutes=1)),
                    alert_row(expiry=datetime.now(timezone.utc) + timedelta(hours=1))]
    assert len(asyncio.run(public_alerts(Database(), "pune-grid-r2-c2"))) == 1


def test_alert_author_cannot_review_own_draft():
    author = principal()
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if kwargs["params"].get("limit") == 0:
                return []
            return [{"status": "pending_approval", "created_by": str(author.id)}]
    async def run():
        with pytest.raises(HTTPException) as error:
            await review_alert(uuid4(), AlertReview(approve=True), author, Database())
        assert error.value.status_code == 403
    asyncio.run(run())


def test_alert_submit_rejects_other_author_and_publish_rejects_invalid_expiry():
    user = principal()
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if kwargs["params"].get("limit") == 0:
                return []
            return [{"status": "draft", "created_by": str(uuid4())}]
    async def run():
        with pytest.raises(HTTPException) as error:
            await submit_alert(uuid4(), user, Database())
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as expiry:
            await publish_alert(uuid4(), AlertPublish(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)), user, Database())
        assert expiry.value.status_code == 422
    asyncio.run(run())


def test_two_authority_alert_lifecycle_uses_expected_state_updates():
    author, reviewer = principal(), principal()
    row = {"id": str(uuid4()), "title": "Verified weather advisory", "body": "Follow local authority updates and prepare for changing conditions.",
           "level": "moderate", "locality_id": "pune-grid-r2-c2", "source": "Verified bulletin", "status": "draft",
           "approved_at": None, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": str(author.id)}
    transitions = []
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if kwargs["params"].get("limit") == 0:
                return []
            if method == "GET":
                return [row.copy()]
            assert method == "PATCH" and kwargs["params"]["status"] == f"eq.{row['status']}"
            row.update(kwargs["json"])
            transitions.append(row["status"])
            return [row.copy()]
    async def run():
        database = Database()
        alert_id = uuid4()
        submitted = await submit_alert(alert_id, author, database)
        assert submitted.status == "pending_approval"
        approved = await review_alert(alert_id, AlertReview(approve=True), reviewer, database)
        assert approved.status == "approved" and approved.approvedBy == reviewer.id
        published = await publish_alert(alert_id, AlertPublish(expires_at=datetime.now(timezone.utc) + timedelta(hours=2)), author, database)
        assert published.status == "published" and published.expiresAt is not None
    asyncio.run(run())
    assert transitions == ["pending_approval", "approved", "published"]


def test_incident_image_path_cannot_belong_to_another_user():
    user = principal("citizen")
    body = IncidentCreate(localityId="pune-grid-r2-c2", category="flood", description="Observed water near the main crossing today.",
                          image_path=f"{uuid4()}/{uuid4()}.jpg")
    async def run():
        with pytest.raises(HTTPException) as error:
            await create_incident(body, user, object())
        assert error.value.status_code == 422
    asyncio.run(run())


def test_legacy_incident_submission_survives_pending_migration():
    user = principal("citizen")
    row = {"id": str(uuid4()), "locality_id": "pune-grid-r2-c2", "category": "flood",
           "description": "Observed water near the main crossing today.", "contact": None,
           "created_at": datetime.now(timezone.utc).isoformat(), "status": "submitted"}
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if table == "incident_reports" and method == "GET":
                raise UpstreamError("missing schema column")
            if table == "zones":
                return [{"id": str(uuid4())}]
            assert table == "incident_reports" and method == "POST"
            assert "severity" not in kwargs["json"] and "image_path" not in kwargs["json"]
            return [row]
    async def run():
        body = IncidentCreate(localityId="pune-grid-r2-c2", category="flood", description=row["description"])
        created = await create_incident(body, user, Database())
        assert created.status == "submitted" and created.severity == "moderate"
        with pytest.raises(ServiceUnavailable):
            await create_incident(IncidentCreate(localityId="pune-grid-r2-c2", category="waterlogging",
                description=row["description"]), user, Database())
    asyncio.run(run())


def test_incident_review_rejects_missing_reason_and_conflicting_transition():
    user = principal()
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if method == "GET":
                return [{"id": str(uuid4()), "status": "resolved"}]
            raise AssertionError("Conflicting review must not write")
    async def run():
        with pytest.raises(HTTPException) as reason:
            await review_incident(uuid4(), IncidentReview(status="rejected"), user, Database())
        assert reason.value.status_code == 422
        with pytest.raises(HTTPException) as conflict:
            await review_incident(uuid4(), IncidentReview(status="under_review"), user, Database())
        assert conflict.value.status_code == 409
    asyncio.run(run())


def test_incident_review_missing_report_is_404():
    class Database:
        async def table(self, table, method="GET", **kwargs):
            assert table == "incident_reports" and method == "GET"
            return []
    async def run():
        with pytest.raises(HTTPException) as error:
            await review_incident(uuid4(), IncidentReview(status="under_review"), principal(), Database())
        assert error.value.status_code == 404
    asyncio.run(run())


def test_incident_review_persists_transition_and_reads_audit_history():
    from app.api.incidents import incident_history
    reviewer = principal()
    report_id = uuid4()
    row = {"id": str(report_id), "reporter_id": str(uuid4()), "locality_id": "pune-grid-r2-c2",
           "category": "flood", "description": "Observed water near the main crossing today.",
           "contact": None, "created_at": datetime.now(timezone.utc).isoformat(), "status": "submitted",
           "review_note": None, "reviewed_by": None, "reviewed_at": None}
    audit = []
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if table == "audit_logs":
                return audit
            if method == "GET" and kwargs["params"].get("limit") == 0:
                return []
            if method == "GET":
                return [row.copy()]
            assert table == "incident_reports" and method == "PATCH"
            assert kwargs["token"] == reviewer.token
            assert kwargs["params"]["status"] == f"eq.{row['status']}"
            previous = row["status"]
            row.update(kwargs["json"])
            audit.append({"actor_id": str(reviewer.id), "created_at": datetime.now(timezone.utc).isoformat(),
                          "details": {"old_status": previous, "new_status": row["status"]}})
            return [row.copy()]
    async def run():
        database = Database()
        started = await review_incident(report_id, IncidentReview(status="under_review"), reviewer, database)
        assert started.status == "under_review" and started.reviewed_by == reviewer.id and started.reviewed_at
        finished = await review_incident(report_id, IncidentReview(status="resolved", review_note="Field checked"), reviewer, database)
        assert finished.status == "resolved" and finished.review_note == "Field checked"
        history = await incident_history(report_id, reviewer, database)
        assert [(entry.old_status, entry.new_status) for entry in history] == [
            ("submitted", "under_review"), ("under_review", "resolved")]
    asyncio.run(run())


def test_incident_review_reports_unapplied_geometry_guard_fix():
    report_id = uuid4()
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if method == "GET" and kwargs["params"].get("limit") == 0:
                return []
            if method == "GET":
                return [{"id": str(report_id), "status": "submitted"}]
            raise SupabaseRequestError(400, "42725")
    async def run():
        with pytest.raises(ServiceUnavailable, match="migration 009"):
            await review_incident(report_id, IncidentReview(status="under_review"), principal(), Database())
    asyncio.run(run())


def test_citizen_role_cannot_call_authority_review_routes():
    citizen = principal("citizen")
    class Database:
        async def user(self, _):
            return {"id": str(citizen.id)}
        async def table(self, table, method="GET", **kwargs):
            if table == "profiles":
                return [{"id": str(citizen.id), "role": "citizen"}]
            raise AssertionError("Privileged table reached by citizen")
    app.dependency_overrides[get_gateway] = lambda: Database()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": "Bearer DEMO-token"}
            incident = await client.patch(f"/api/incidents/{uuid4()}/review", headers=headers, json={"status": "under_review"})
            alert = await client.post(f"/api/alerts/{uuid4()}/review", headers=headers, json={"approve": True})
            assert incident.status_code == alert.status_code == 403
    try:
        asyncio.run(run())
    finally:
        app.dependency_overrides.clear()
