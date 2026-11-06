"""DEMO unit fixtures for workflow transitions; no live records are created."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.api.alerts import AlertPublish, AlertReview, alert_history, create_alert, edit_published_alert, public_alerts, publish_alert, review_alert, submit_alert
from app.api.incidents import create_incident, review_incident
from app.core.auth import Principal
from app.core.errors import ServiceUnavailable, SupabaseRequestError, UpstreamError
from app.main import app
from app.integrations.supabase import get_gateway
from app.schemas.incidents import IncidentCreate, IncidentReview
from app.schemas.alerts import AlertCreate, AlertEdit


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


def test_public_alerts_require_published_state_and_cell_filter():
    class Database:
        async def table(self, table, method="GET", **kwargs):
            assert kwargs["params"]["status"] == "eq.published"
            assert kwargs["params"]["locality_id"] == "in.(pune,pune-grid-r2-c2)"
            assert kwargs["params"]["order"] == "published_at.desc.nullslast"
            return [alert_row(), {**alert_row(), "localityId": "pune"}, {**alert_row(), "status": "draft"},
                    {**alert_row(), "status": "withdrawn"}]

    alerts = asyncio.run(public_alerts(Database(), "pune-grid-r2-c2"))
    assert len(alerts) == 2 and {alert.localityId for alert in alerts} == {"pune", "pune-grid-r2-c2"}


def test_self_approval_waits_for_migration_010():
    author = principal()
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if kwargs["params"].get("select") == "incident_id":
                raise UpstreamError("column unavailable")
            return [{"status": "pending_approval", "created_by": str(author.id)}]
    async def run():
        with pytest.raises(ServiceUnavailable) as error:
            await review_alert(uuid4(), AlertReview(approve=True), author, Database())
        assert "migration 010" in error.value.detail
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


def test_single_authority_alert_lifecycle_uses_expected_state_updates():
    author = principal()
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
            assert method == "PATCH"
            if kwargs["params"]["status"] != f"eq.{row['status']}":
                return []
            row.update(kwargs["json"])
            transitions.append(row["status"])
            return [row.copy()]
    async def run():
        database = Database()
        alert_id = uuid4()
        submitted = await submit_alert(alert_id, author, database)
        assert submitted.status == "pending_approval"
        approved = await review_alert(alert_id, AlertReview(approve=True), author, database)
        assert approved.status == "approved" and approved.approvedBy == author.id
        published = await publish_alert(alert_id, AlertPublish(expires_at=datetime.now(timezone.utc) + timedelta(hours=2)), author, database)
        assert published.status == "published" and published.expiresAt is not None
        with pytest.raises(HTTPException) as duplicate:
            await publish_alert(alert_id, AlertPublish(expires_at=datetime.now(timezone.utc) + timedelta(hours=2)), author, database)
        assert duplicate.value.status_code == 409
    asyncio.run(run())
    assert transitions == ["pending_approval", "approved", "published"]


def test_linked_advisory_requires_verified_incident_in_same_zone():
    author, incident_id, zone_id = principal(), uuid4(), uuid4()
    body = AlertCreate(title="TEST weather update", body="Please check official local updates before travel.",
        level="moderate", localityId="pune-grid-r2-c2", source="Verified report and live analysis",
        incidentId=incident_id)
    class Database:
        def __init__(self, incident_status="resolved", incident_zone=zone_id):
            self.incident_status, self.incident_zone = incident_status, incident_zone
            self.inserted = None
        async def table(self, table, method="GET", **kwargs):
            if method == "GET" and table == "zones":
                return [{"id": str(zone_id)}]
            if method == "GET" and table == "incident_reports":
                return [{"id": str(incident_id), "status": self.incident_status,
                         "locality_id": "pune-grid-r2-c2", "zone_id": str(self.incident_zone)}]
            if method == "GET" and table == "alerts":
                return [{"incident_id": None}]
            if method == "POST" and table == "alerts":
                self.inserted = kwargs["json"]
                return [{"id": str(uuid4()), **self.inserted, "created_at": datetime.now(timezone.utc).isoformat(),
                         "approved_at": None}]
            raise AssertionError((table, method, kwargs))
    async def run():
        valid = Database()
        result = await create_alert(body, author, valid)
        assert result.incidentId == incident_id and valid.inserted["incident_id"] == str(incident_id)
        for invalid in (Database("submitted"), Database(incident_zone=uuid4())):
            with pytest.raises(HTTPException) as error:
                await create_alert(body, author, invalid)
            assert error.value.status_code == 422 and invalid.inserted is None
    asyncio.run(run())


def test_published_alert_edit_and_audit_history_require_authority():
    author, alert_id = principal(), uuid4()
    row = {"id": str(alert_id), "title": "TEST weather update", "body": "Please check official local updates before travel.",
           "level": "moderate", "locality_id": "pune-grid-r2-c2", "source": "Verified source",
           "status": "published", "approved_at": datetime.now(timezone.utc).isoformat(),
           "created_at": datetime.now(timezone.utc).isoformat()}
    class Database:
        async def table(self, table, method="GET", **kwargs):
            if table == "alerts" and method == "GET":
                return [row.copy()]
            if table == "alerts" and method == "PATCH":
                assert kwargs["params"]["status"] == "eq.published"
                assert "approved_by" not in kwargs["json"] and "expires_at" not in kwargs["json"]
                row.update(kwargs["json"])
                return [row.copy()]
            if table == "audit_logs":
                assert kwargs["privileged"] and kwargs["params"]["entity_id"] == f"eq.{alert_id}"
                return [{"actor_id": str(author.id), "created_at": datetime.now(timezone.utc).isoformat(),
                         "action": "alerts.edited", "details": {"status": "published", "changed_fields": ["body"]}}]
            raise AssertionError((table, method))
    async def run():
        database = Database()
        edited = await edit_published_alert(alert_id, AlertEdit(title=row["title"], body="Updated official guidance for this analysis cell.",
            level="moderate", source="Verified source"), author, database)
        assert edited.status == "published" and edited.body.startswith("Updated")
        history = await alert_history(alert_id, author, database)
        assert history[0].actorId == author.id and history[0].changedFields == ["body"]
    asyncio.run(run())


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
            published_edit = await client.patch(f"/api/alerts/{uuid4()}/published", headers=headers,
                json={"title": "TEST update", "body": "A valid official update for this analysis cell.",
                      "level": "moderate", "source": "Verified source", "hazard": "other"})
            history = await client.get(f"/api/alerts/{uuid4()}/history", headers=headers)
            assert incident.status_code == alert.status_code == published_edit.status_code == history.status_code == 403
            assert (await client.post(f"/api/alerts/{uuid4()}/review", json={"approve": True})).status_code == 401
    try:
        asyncio.run(run())
    finally:
        app.dependency_overrides.clear()
