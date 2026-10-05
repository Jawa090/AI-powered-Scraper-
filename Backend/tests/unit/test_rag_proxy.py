"""
Unit tests for Backend/routes/rag_proxy.py
"""
import pytest
from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient
from app import app


@pytest.fixture
def api_client():
    return TestClient(app)


@pytest.mark.unit
def test_rag_proxy_unauthenticated(api_client):
    """Accessing /api/rag without auth returns 401."""
    res = api_client.get("/api/rag/v1/status")
    assert res.status_code == 401


@pytest.mark.unit
def test_rag_proxy_authenticated_status_when_not_deployed(api_client, user_token):
    """Authenticated user can access /api/rag/v1/status even when RAG is not deployed."""
    headers = {"Authorization": f"Bearer {user_token}"}
    with patch("settings.settings.RAG_SERVICE_URL", ""):
        res = api_client.get("/api/rag/v1/status", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "not_deployed"
        assert data["available"] is False


@pytest.mark.unit
def test_rag_proxy_authenticated_search_when_not_deployed(api_client, user_token):
    """Authenticated user can access /api/rag/v1/search when not deployed -> 409 conflict."""
    headers = {"Authorization": f"Bearer {user_token}"}
    with patch("settings.settings.RAG_SERVICE_URL", ""):
        res = api_client.post("/api/rag/v1/search", json={"query": "test"}, headers=headers)
        assert res.status_code == 409
        data = res.json()
        assert data["state"] == "not_deployed"


@pytest.mark.unit
def test_rag_proxy_non_admin_forbidden_on_admin_endpoint(api_client, user_token):
    """Non-admin user cannot access endpoints other than v1/status and v1/search -> 403."""
    headers = {"Authorization": f"Bearer {user_token}"}
    res = api_client.get("/api/rag/v1/documents", headers=headers)
    assert res.status_code == 403


@pytest.mark.unit
def test_rag_proxy_admin_allowed_on_admin_endpoint(api_client, admin_token):
    """Admin user can access /api/rag/v1/documents."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    with patch("settings.settings.RAG_SERVICE_URL", ""):
        res = api_client.get("/api/rag/v1/documents", headers=headers)
        # When RAG_SERVICE_URL is empty, returns 503 RAG_NOT_DEPLOYED, NOT 403 Forbidden
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "RAG_NOT_DEPLOYED"


@pytest.mark.unit
def test_rag_proxy_forwarding(api_client, admin_token):
    """Proxy correctly forwards request to RAG_SERVICE_URL with required identity headers."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    mock_response = httpx.Response(
        status_code=200,
        json={"hits": [{"chunkId": "c1", "score": 0.95}]},
    )

    with patch("settings.settings.RAG_SERVICE_URL", "http://rag-remote:8001"), \
         patch("settings.settings.RAG_SERVICE_TOKEN", "super-secret"), \
         patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
        res = api_client.post(
            "/api/rag/v1/search",
            json={"query": "bonfire roofing", "topK": 3},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["hits"][0]["chunkId"] == "c1"

        # Verify request parameters
        mock_req.assert_called_once()
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["url"] == "http://rag-remote:8001/v1/search"
        sent_headers = call_kwargs["headers"]
        assert sent_headers["X-RAG-Service-Token"] == "super-secret"
        assert "X-User-Id" in sent_headers
        assert sent_headers["X-User-Role"] == "admin"
