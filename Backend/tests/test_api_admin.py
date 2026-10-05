"""
tests/test_api_admin.py
───────────────────────
Unit & integration tests for admin API routes.
Covers Phase P12.3:
- Authorization: admin allowed, regular user 403, anonymous 401
- Activity log (/api/admin/requests) with pagination, D10 decision, source filter, and strict date validation
- Request details (/api/admin/requests/{id}) with selectinload (no N+1), slots, KB, job, transcript, tool trace, rows served
- Per-user timeline (/api/admin/users/{id}/requests)
- Admin chat viewer (/api/admin/users/{id}/sessions, /api/admin/sessions/{id}/messages)
- Aggregate stats (/api/admin/stats) with D10 counts, job status, duplicates prevented
- Streamed CSV export (/api/admin/requests/export.csv) with matching filters and validation
- User management (/api/admin/users)
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app import app
from services.auth import require_admin
from Database import get_db
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from Database.models.query_result import QueryResult
from Database.models.job import Job
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from Database.models.lead import Lead
from Database.models.organization import Organization
from Database.models.contact import Contact

client = TestClient(app)


def override_require_admin():
    return User(id="admin_test_user", role="admin", name="Admin User")


def override_require_admin_forbidden():
    raise HTTPException(status_code=403, detail="Not enough permissions")


def override_require_admin_unauth():
    raise HTTPException(status_code=401, detail="Not authenticated")


class TestAdminAPI:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_admin_access_allowed(self):
        """Admin can list requests and receive paginated response."""
        app.dependency_overrides[require_admin] = override_require_admin
        response = client.get("/api/admin/requests")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pageSize" in data

    def test_admin_access_forbidden_for_normal_user(self):
        """Normal user receives 403 on admin routes."""
        app.dependency_overrides[require_admin] = override_require_admin_forbidden
        response = client.get("/api/admin/requests")
        assert response.status_code == 403

        response = client.get("/api/admin/stats")
        assert response.status_code == 403

        response = client.get("/api/admin/users")
        assert response.status_code == 403

    def test_admin_access_unauthorized_for_anonymous(self):
        """Anonymous caller receives 401."""
        app.dependency_overrides[require_admin] = override_require_admin_unauth
        response = client.get("/api/admin/requests")
        assert response.status_code == 401

    def test_admin_requests_date_validation(self):
        """Strict date format validation: invalid dates must return 400."""
        app.dependency_overrides[require_admin] = override_require_admin

        # Invalid 'from' date
        res = client.get("/api/admin/requests?from=not-a-date")
        assert res.status_code == 400
        assert "Invalid 'from' date format" in res.json()["detail"]

        # Invalid 'to' date
        res = client.get("/api/admin/requests?to=2026/10/05")
        assert res.status_code == 400
        assert "Invalid 'to' date format" in res.json()["detail"]

        # Valid date formats
        res = client.get("/api/admin/requests?from=2026-01-01&to=2026-12-31")
        assert res.status_code == 200

    def test_admin_requests_filtering(self):
        """Filter requests by user_id, decision, and source."""
        app.dependency_overrides[require_admin] = override_require_admin

        test_uid = f"user-{uuid.uuid4().hex[:6]}"
        test_qid = f"query-{uuid.uuid4().hex[:6]}"
        test_jid = f"job-{uuid.uuid4().hex[:6]}"

        with session_scope() as session:
            user = User(id=test_uid, name="Filter User", username=f"filter_{test_uid}", password_hash="hash", role="user")
            job = Job(id=test_jid, name="Filter Test Job", script_id="dasny", status="Completed", created_by=test_uid)
            query = Query(
                id=test_qid,
                user_id=test_uid,
                job_id=test_jid,
                query_text="Find construction bids",
                decision="SCRAPER",
                status="completed",
                parameters={"slots": {"source": "dasny"}},
            )
            session.add(user)
            session.add(job)
            session.flush()
            session.add(query)
            session.commit()

        # Filter by user_id
        res = client.get(f"/api/admin/requests?user_id={test_uid}")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert any(item["id"] == test_qid for item in data["items"])

        # Filter by decision
        res = client.get(f"/api/admin/requests?decision=SCRAPER&user_id={test_uid}")
        assert res.status_code == 200
        assert any(item["id"] == test_qid for item in res.json()["items"])

        # Filter by source (routes through jobs.script_id)
        res = client.get(f"/api/admin/requests?source=dasny&user_id={test_uid}")
        assert res.status_code == 200
        assert any(item["id"] == test_qid for item in res.json()["items"])

    def test_admin_request_detail(self):
        """Request detail returns full query, slots, decision, job, transcript, tool trace, rows served."""
        app.dependency_overrides[require_admin] = override_require_admin

        test_uid = f"user-{uuid.uuid4().hex[:6]}"
        test_qid = f"query-{uuid.uuid4().hex[:6]}"
        test_jid = f"job-{uuid.uuid4().hex[:6]}"
        test_sid = f"sess-{uuid.uuid4().hex[:6]}"
        test_lid = f"lead-{uuid.uuid4().hex[:6]}"
        test_org_id = f"org-{uuid.uuid4().hex[:6]}"

        with session_scope() as session:
            user = User(id=test_uid, name="Detail User", username=f"detail_{test_uid}", password_hash="hash", role="user")
            org = Organization(id=test_org_id, name="Apex Contracting", normalized_name="apex contracting")
            lead = Lead(id=test_lid, title="General Contractor", organization_id=test_org_id, status="Qualified")
            job = Job(id=test_jid, name="Detail Test Job", script_id="dasny", status="Completed", error_message="None", created_by=test_uid)
            agent_sess = AgentSession(id=test_sid, user_id=test_uid, agent_id="agent-master", department_id="dept-default")
            msg = AgentMessage(
                session_id=test_sid,
                sender="agent",
                role="agent",
                text="Proposal generated",
                tool_trace=[{"tool": "propose_scrape", "args": {"source": "dasny"}}],
            )
            session.add_all([user, org, lead, job, agent_sess, msg])
            session.flush()

            query = Query(
                id=test_qid,
                user_id=test_uid,
                session_id=test_sid,
                job_id=test_jid,
                query_text="Need general contractors",
                decision="SCRAPER",
                status="completed",
                parameters={
                    "slots": {"category": "construction"},
                    "kb_state": "available",
                    "kb_hits": ["doc-1"],
                },
            )
            qr = QueryResult(query_id=test_qid, lead_id=test_lid, rank=1)

            session.add_all([query, qr])
            session.commit()

        # Non-existent request returns 404
        res404 = client.get("/api/admin/requests/non-existent-id")
        assert res404.status_code == 404

        # Detail fetch
        res = client.get(f"/api/admin/requests/{test_qid}")
        assert res.status_code == 200
        data = res.json()

        assert data["request"]["id"] == test_qid
        assert data["slots"]["category"] == "construction"
        assert data["decision"] == "SCRAPER"
        assert data["kbState"] == "available"
        assert "doc-1" in data["kbHits"]

        # Job detail
        assert data["job"]["id"] == test_jid
        assert data["job"]["errorMessage"] == "None"

        # Transcript and tool trace
        assert len(data["transcript"]) >= 1
        assert any(t["text"] == "Proposal generated" for t in data["transcript"])
        assert len(data["toolTrace"]) >= 1

        # Rows served via single selectinload query
        assert len(data["rowsServed"]) >= 1
        assert data["rowsServed"][0]["leadId"] == test_lid
        assert data["rowsServed"][0]["company"] == "Apex Contracting"

    def test_admin_user_timeline(self):
        """User timeline returns paginated requests for the specified user."""
        app.dependency_overrides[require_admin] = override_require_admin

        test_uid = f"user-{uuid.uuid4().hex[:6]}"
        with session_scope() as session:
            user = User(id=test_uid, name="Timeline User", username=f"timeline_{test_uid}", password_hash="hash", role="user")
            q = Query(id=f"q-{uuid.uuid4().hex[:6]}", user_id=test_uid, query_text="Timeline query", decision="DB")
            session.add(user)
            session.add(q)
            session.commit()

        res = client.get(f"/api/admin/users/{test_uid}/requests")
        assert res.status_code == 200
        data = res.json()
        assert data["user"]["id"] == test_uid
        assert data["total"] >= 1
        assert data["items"][0]["queryText"] == "Timeline query"

    def test_admin_chat_viewer(self):
        """Admin can view user sessions and read all messages (including hidden event messages)."""
        app.dependency_overrides[require_admin] = override_require_admin

        test_uid = f"user-{uuid.uuid4().hex[:6]}"
        test_sid = f"sess-{uuid.uuid4().hex[:6]}"

        with session_scope() as session:
            user = User(id=test_uid, name="Chat User", username=f"chat_{test_uid}", password_hash="hash", role="user")
            sess = AgentSession(id=test_sid, user_id=test_uid, agent_id="agent-master", department_id="dept-default")
            normal_msg = AgentMessage(session_id=test_sid, sender="user", role="user", text="Hello")
            hidden_msg = AgentMessage(
                session_id=test_sid,
                sender="system",
                role="system_event",
                text="[JOB EVENT] Scraper completed",
                message_metadata={"hidden": True},
            )
            session.add_all([user, sess, normal_msg, hidden_msg])
            session.commit()

        # User sessions
        res_sess = client.get(f"/api/admin/users/{test_uid}/sessions")
        assert res_sess.status_code == 200
        assert any(s["id"] == test_sid for s in res_sess.json()["sessions"])

        # Admin messages viewer includes hidden messages
        res_msg = client.get(f"/api/admin/sessions/{test_sid}/messages")
        assert res_msg.status_code == 200
        messages = res_msg.json()["messages"]
        assert len(messages) >= 2
        assert any(m["role"] == "system_event" for m in messages)

    def test_admin_stats(self):
        """Stats endpoint returns D10 decision counts, job status breakdown, and duplicates prevented."""
        app.dependency_overrides[require_admin] = override_require_admin

        res = client.get("/api/admin/stats")
        assert res.status_code == 200
        data = res.json()

        assert "totalQueries" in data
        assert "d10Counts" in data
        assert "jobsByStatus" in data
        assert "duplicatesPrevented" in data
        assert "llmUnavailableTurns" in data
        assert "kbUsage" in data
        assert "totalLeads" in data
        assert "totalDatasets" in data
        assert "totalUsers" in data

        # Validate D10 keys exist
        d10_keys = ["KB", "DB", "SCRAPER", "PARTIAL", "CLARIFY", "NONE", "DECLINED", "FAILED", "LLM_UNAVAILABLE"]
        for k in d10_keys:
            assert k in data["d10Counts"]

    def test_admin_export_csv(self):
        """CSV export returns streamed CSV and validates date parameters identically."""
        app.dependency_overrides[require_admin] = override_require_admin

        # Valid export
        res = client.get("/api/admin/requests/export.csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "attachment; filename=requests_export.csv" in res.headers["content-disposition"]
        assert "ID,User ID,User Name,Query Text" in res.text

        # Invalid date format returns 400
        res_err = client.get("/api/admin/requests/export.csv?from=bad-date")
        assert res_err.status_code == 400
