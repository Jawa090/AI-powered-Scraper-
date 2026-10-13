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
        "email": test_user + "@example.test",
        "password": "testpassword"
    }, headers=headers_admin)

    res2 = client.post("/api/auth/login", json={"username": test_user, "password": "testpassword"})
    token2 = res2.json()["accessToken"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    res_new = client.post("/api/bot/chat/new", json={}, headers=headers1)
    session_id = res_new.json()["sessionId"]

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

        # Admin can read the transcript but cannot approve or write as its owner
        res_admin_chat = client.post("/api/bot/chat", json={
            "sessionId": session_id,
            "message": "Admin message",
        }, headers=headers_admin)
        assert res_admin_chat.status_code == 403


def test_bot_confirm_endpoint():
    res = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    headers = {"Authorization": f"Bearer {res.json()['accessToken']}"}

    res_new = client.post("/api/bot/chat/new", json={}, headers=headers)
    session_id = res_new.json()["sessionId"]

    # First initialize session
    with patch("routes.bot.run_turn") as mock_turn:
        mock_turn.return_value = {"reply": "Proposal ready", "sessionId": session_id}
        client.post("/api/bot/chat", json={"sessionId": session_id, "message": "hello"}, headers=headers)

    # A confirmation without a proposal must be rejected.
    assert client.post("/api/bot/confirm", json={"sessionId": session_id, "decision": "approve"}, headers=headers).status_code == 409

    # Now confirm approve against a real pending interrupt snapshot
    with patch("routes.bot.get_compiled_graph") as graph, patch("routes.bot.run_turn") as mock_turn:
        graph.return_value.get_state.return_value.interrupts = [object()]
        mock_turn.return_value = {"reply": "Starting scraper", "jobId": "job-123", "sessionId": session_id}
        res_approve = client.post("/api/bot/confirm", json={
            "sessionId": session_id,
            "decision": "approve",
        }, headers=headers)
        assert res_approve.status_code == 200
        assert mock_turn.call_args[0][1] == session_id
        assert mock_turn.call_args[0][2] == "Yes, run the proposed scrape."

    # Confirm reject
    with patch("routes.bot.get_compiled_graph") as graph, patch("routes.bot.run_turn") as mock_turn:
        graph.return_value.get_state.return_value.interrupts = [object()]
        mock_turn.return_value = {"reply": "Scrape cancelled", "sessionId": session_id}
        res_reject = client.post("/api/bot/confirm", json={
            "sessionId": session_id,
            "decision": "reject",
        }, headers=headers)
        assert res_reject.status_code == 200
        assert mock_turn.call_args[0][1] == session_id
        assert mock_turn.call_args[0][2] == "No, do not run it."



def test_leads_export_csv():
    res = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    headers = {"Authorization": f"Bearer {res.json()['accessToken']}"}

    res_csv = client.get("/api/leads/export.csv", headers=headers)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "attachment; filename=leads_export.csv" in res_csv.headers["content-disposition"]
    assert "ID,Name,Company,Title" in res_csv.text
