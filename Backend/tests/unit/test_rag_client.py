"""
Unit tests for Backend/integrations/rag_client.py
"""
import pytest
import httpx
from Backend.integrations.rag_client import RAGClient
from Backend.tests.fakes.fake_rag import FakeRAGTransport


@pytest.mark.unit
def test_rag_client_not_deployed():
    """Empty base_url reports state='not_deployed' without making network calls."""
    client = RAGClient(base_url="", token="")
    st = client.status()
    assert st["state"] == "not_deployed"
    assert st["available"] is False

    res = client.search(query="roofing")
    assert "error" in res
    assert res["error"]["code"] == "not_deployed"


@pytest.mark.unit
def test_rag_client_status_ready_and_search():
    """Client successfully queries status and executes search against mock transport."""
    transport = FakeRAGTransport(expected_token="valid-token", state="ready")
    client = RAGClient(base_url="http://rag-service", token="valid-token", transport=transport)

    st = client.status()
    assert st["state"] == "ready"
    assert st["available"] is True
    assert st["version"] == "v1"

    res = client.search(query="roofing", top_k=5, user_id="usr-1", user_role="admin")
    assert "hits" in res
    assert len(res["hits"]) >= 1
    assert res["hits"][0]["chunkId"] == "chk-001"


@pytest.mark.unit
def test_rag_client_search_not_ready_reports_409():
    """Search when RAG is not ready returns 409 conflict response as dict."""
    transport = FakeRAGTransport(expected_token="valid-token", state="not_configured")
    client = RAGClient(base_url="http://rag-service", token="valid-token", transport=transport)

    res = client.search(query="roofing")
    assert res.get("state") == "not_configured"
    assert res.get("available") is False


@pytest.mark.unit
def test_rag_client_unreachable():
    """Transport network failures mapped to state='unreachable'."""
    class FailingTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused", request=request)

    client = RAGClient(base_url="http://rag-down", token="token", transport=FailingTransport())
    st = client.status()
    assert st["state"] == "unreachable"
    assert st["available"] is False

    res = client.search(query="roofing")
    assert "error" in res
    assert res["error"]["code"] == "unreachable"


@pytest.mark.unit
def test_rag_client_malformed_response():
    """Non-conforming response mapped to state='error'."""
    class BadTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"some": "random_data"}, request=request)

    client = RAGClient(base_url="http://rag-bad", token="token", transport=BadTransport())
    st = client.status()
    assert st["state"] == "error"
    assert st["available"] is False
