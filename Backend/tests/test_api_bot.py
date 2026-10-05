"""
tests/test_api_bot.py
─────────────────────
Unit & integration tests for AI Bot API routes and D9 scoping.
Covers Phase P11.11 / P12:
- POST /api/bot/chat: conversational turn, session creation, ownership check (403 for non-owner)
- POST /api/bot/confirm: approve/reject sends prompt through agent turn
- POST /api/bot/confirm-and-generate: 409 when no pending interrupt
- GET  /api/bot/sessions: scoped per D9 (users see own sessions; admin sees all)
- GET  /api/bot/sessions/{id}/messages: excludes hidden messages, supports after=<iso> polling
- GET  /api/leads/export.csv: streams CSV scoped per D9
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch

from app import app
from Database.controller import session_scope
from Database.models.user import User
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from Database.models.job import Job
from Database.models.lead import Lead
from Database.models.organization import Organization
from services.auth import get_current_user

client = TestClient(app)


def test_bot_chat_and_ownership():
    # User 1 logins
    res1 = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    token1 = res1.json()["accessToken"]
    user1_id = res1.json()["user"]["id"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    # Admin logins
    res_admin = client.post("/api/auth/login", json={"username": "Admin", "password": "Admin"})
    token_admin = res_admin.json()["accessToken"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    # Create Alice (User 2)
    test_user = f"user_{uuid.uuid4().hex[:8]}"
    client.post("/api/admin/users", json={
        "username": test_user,
        "name": "Alice User",
        "password": "testpassword"
    }, headers=headers_admin)

    res2 = client.post("/api/auth/login", json={"username": test_user, "password": "testpassword"})
    token2 = res2.json()["accessToken"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    session_id = f"sess-{uuid.uuid4().hex[:8]}"

    with patch("routes.bot.run_turn") as mock_turn:
        mock_turn.return_value = {
            "reply": "I found 5 contracts.",
            "suggestions": ["View details"],
            "sessionId": session_id,
        }

        # User1 chats -> creates session and messages
        res = client.post("/api/bot/chat", json={
            "sessionId": session_id,
            "message": "Find HVAC contracts",
            "clientMessageId": str(uuid.uuid4()),
        }, headers=headers1)
        assert res.status_code == 200
        assert res.json()["reply"] == "I found 5 contracts."

        # Alice cannot chat with User1's session -> 403
        res_forbidden = client.post("/api/bot/chat", json={
            "sessionId": session_id,
            "message": "Can I see this?",
        }, headers=headers2)
        assert res_forbidden.status_code == 403

        # Admin CAN chat with User1's session per D9
        res_admin_chat = client.post("/api/bot/chat", json={
            "sessionId": session_id,
            "message": "Admin message",
        }, headers=headers_admin)
        assert res_admin_chat.status_code == 200


def test_bot_confirm_endpoint():
    res = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    headers = {"Authorization": f"Bearer {res.json()['accessToken']}"}

    session_id = f"sess-{uuid.uuid4().hex[:8]}"

    # First initialize session
    with patch("routes.bot.run_turn") as mock_turn:
        mock_turn.return_value = {"reply": "Proposal ready", "sessionId": session_id}
        client.post("/api/bot/chat", json={"sessionId": session_id, "message": "hello"}, headers=headers)

    # Now confirm approve
    with patch("routes.bot.run_turn") as mock_turn:
        mock_turn.return_value = {"reply": "Starting scraper", "jobId": "job-123", "sessionId": session_id}
        res_approve = client.post("/api/bot/confirm", json={
            "sessionId": session_id,
            "decision": "approve",
        }, headers=headers)
        assert res_approve.status_code == 200
        assert mock_turn.call_args[0][1] == session_id
        assert mock_turn.call_args[0][2] == "Yes, run the proposed scrape."

    # Confirm reject
    with patch("routes.bot.run_turn") as mock_turn:
        mock_turn.return_value = {"reply": "Scrape cancelled", "sessionId": session_id}
        res_reject = client.post("/api/bot/confirm", json={
            "sessionId": session_id,
            "decision": "reject",
        }, headers=headers)
        assert res_reject.status_code == 200
        assert mock_turn.call_args[0][1] == session_id
        assert mock_turn.call_args[0][2] == "No, don't run it."


def test_bot_confirm_and_generate_409_when_no_interrupt():
    res = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    headers = {"Authorization": f"Bearer {res.json()['accessToken']}"}

    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    with patch("routes.bot.pending_interrupt", return_value=False):
        res_cg = client.post("/api/bot/confirm-and-generate", json={
            "sessionId": session_id,
        }, headers=headers)
        assert res_cg.status_code == 409
        assert res_cg.json()["success"] is False


def test_bot_sessions_and_messages_polling():
    res1 = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    headers1 = {"Authorization": f"Bearer {res1.json()['accessToken']}"}
    user1_id = res1.json()["user"]["id"]

    res_admin = client.post("/api/auth/login", json={"username": "Admin", "password": "Admin"})
    headers_admin = {"Authorization": f"Bearer {res_admin.json()['accessToken']}"}

    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        sess = AgentSession(id=session_id, user_id=user1_id, agent_id="agent-master", department_id="dept-default")
        msg1 = AgentMessage(session_id=session_id, sender="user", role="user", text="User query")
        msg2 = AgentMessage(session_id=session_id, sender="agent", role="agent", text="Agent answer")
        msg_hidden = AgentMessage(
            session_id=session_id,
            sender="system",
            role="system_event",
            text="[JOB EVENT] Scraper update",
            message_metadata={"hidden": True},
        )
        session.add_all([sess, msg1, msg2, msg_hidden])
        session.commit()

    # User lists sessions -> sees own session
    res_sess = client.get("/api/bot/sessions", headers=headers1)
    assert res_sess.status_code == 200
    assert any(s["id"] == session_id for s in res_sess.json()["sessions"])

    # User polls messages -> receives visible messages, EXCLUDES hidden messages
    res_msgs = client.get(f"/api/bot/sessions/{session_id}/messages", headers=headers1)
    assert res_msgs.status_code == 200
    msgs = res_msgs.json()["messages"]
    assert len(msgs) == 2
    assert all(m["role"] != "system_event" for m in msgs)

    # Invalid after timestamp -> 400
    res_err = client.get(f"/api/bot/sessions/{session_id}/messages?after=not-a-timestamp", headers=headers1)
    assert res_err.status_code == 400

    # Valid after timestamp
    now_iso = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    res_after = client.get(f"/api/bot/sessions/{session_id}/messages?after={now_iso}", headers=headers1)
    assert res_after.status_code == 200
    assert len(res_after.json()["messages"]) == 0


def test_leads_export_csv():
    res = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    headers = {"Authorization": f"Bearer {res.json()['accessToken']}"}

    res_csv = client.get("/api/leads/export.csv", headers=headers)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "attachment; filename=leads_export.csv" in res_csv.headers["content-disposition"]
    assert "ID,Name,Company,Title" in res_csv.text
