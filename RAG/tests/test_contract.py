"""
RAG Service Contract v1 Tests
Validates that endpoints /v1/status and /v1/search conform strictly to RAG CONTRACT.md v1.
"""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from RAG.app import app
from RAG.embedders import EMBEDDERS
from RAG.embedders.base import BaseEmbedder


class FakeContractEmbedder(BaseEmbedder):
    """Test embedder returning constant dimension vectors."""
    def embed_query(self, text: str):
        return [0.1] * 768

    def embed_documents(self, texts):
        return [[0.1] * 768 for _ in texts]


@pytest.fixture(autouse=True)
def setup_test_embedder():
    EMBEDDERS["fake_test"] = FakeContractEmbedder
    old_token = os.environ.get("RAG_SERVICE_TOKEN")
    os.environ["RAG_SERVICE_TOKEN"] = "test-secret-token"
    yield
    EMBEDDERS.pop("fake_test", None)
    if old_token is not None:
        os.environ["RAG_SERVICE_TOKEN"] = old_token


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_header_required(client):
    """Missing or invalid X-RAG-Service-Token returns 401."""
    # Missing token
    res = client.get("/v1/status")
    assert res.status_code == 401
    assert "error" in res.json() or "detail" in res.json()

    # Invalid token
    res = client.get("/v1/status", headers={"X-RAG-Service-Token": "wrong-token"})
    assert res.status_code == 401

    # Search without token
    res = client.post("/v1/search", json={"query": "test"})
    assert res.status_code == 401


def test_status_not_configured_shape(client):
    """GET /v1/status returns exact CONTRACT.md v1 structure when not configured."""
    with patch.dict(os.environ, {"RAG_EMBEDDING_PROVIDER": "", "RAG_STATUS_CACHE_SECONDS": "0"}):
        res = client.get("/v1/status", headers={"X-RAG-Service-Token": "test-secret-token"})
        assert res.status_code == 200
        data = res.json()

        # CONTRACT.md required keys
        assert data["version"] == "v1"
        assert data["state"] == "not_configured"
        assert data["available"] is False
        assert isinstance(data["message"], str)
        assert isinstance(data["documents"], int)
        assert isinstance(data["chunks"], int)
        assert "embeddingModel" in data
        assert isinstance(data["dim"], int)


def test_search_not_ready_returns_409_conflict(client):
    """POST /v1/search returns 409 with status body when service is not ready."""
    with patch.dict(os.environ, {"RAG_EMBEDDING_PROVIDER": "", "RAG_STATUS_CACHE_SECONDS": "0"}):
        res = client.post(
            "/v1/search",
            json={"query": "test roofing bid", "topK": 5},
            headers={"X-RAG-Service-Token": "test-secret-token"},
        )
        assert res.status_code == 409
        body = res.json()
        detail = body.get("detail", body)
        assert detail["state"] == "not_configured"
        assert detail["available"] is False
        assert detail["version"] == "v1"


def test_search_ready_hits_shape(client):
    """POST /v1/search returns 200 with CONTRACT.md hits structure when ready."""
    mock_status = {
        "state": "ready",
        "available": True,
        "message": "RAG knowledge base is ready",
        "documents": 10,
        "chunks": 40,
        "embeddingModel": "test-model",
        "dim": 768,
        "version": "v1",
    }
    mock_hits = [
        {
            "chunkId": "chk-001",
            "documentId": "doc-001",
            "title": "Roofing Guidelines",
            "content": "Licensing requirement details",
            "score": 0.92,
            "metadata": {"source": "manual.pdf"},
        }
    ]

    with patch("RAG.api.routes.compute_status", return_value=mock_status), \
         patch("RAG.api.routes.search_rag", return_value={"hits": mock_hits}):
        res = client.post(
            "/v1/search",
            json={"query": "licensing", "topK": 3},
            headers={"X-RAG-Service-Token": "test-secret-token"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "hits" in data
        assert len(data["hits"]) == 1
        hit = data["hits"][0]
        assert hit["chunkId"] == "chk-001"
        assert hit["documentId"] == "doc-001"
        assert hit["title"] == "Roofing Guidelines"
        assert hit["content"] == "Licensing requirement details"
        assert hit["score"] == 0.92
        assert isinstance(hit["metadata"], dict)


def test_admin_role_enforcement(client):
    """Admin-only endpoints require X-User-Role: admin."""
    headers = {"X-RAG-Service-Token": "test-secret-token", "X-User-Role": "user"}

    # Document create forbidden for non-admin
    res = client.post("/v1/documents", json={"title": "T", "content": "C"}, headers=headers)
    assert res.status_code == 403

    # Document list forbidden for non-admin
    res = client.get("/v1/documents", headers=headers)
    assert res.status_code == 403

    # Document delete forbidden for non-admin
    res = client.delete("/v1/documents/doc-123", headers=headers)
    assert res.status_code == 403

    # Chunks bulk forbidden for non-admin
    res = client.post(
        "/v1/chunks/bulk",
        json={"documentId": "doc-123", "chunks": [], "embeddingModel": "m"},
        headers=headers,
    )
    assert res.status_code == 403
