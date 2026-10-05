"""Unit tests for test fakes in Backend/tests/fakes/."""
import pytest
import httpx
from langchain_core.messages import HumanMessage, AIMessage
from tests.fakes.scripted_chat_model import ScriptedChatModel
from tests.fakes.fake_scraper import FakeScraper
from tests.fakes.fake_rag import FakeRAGTransport


@pytest.mark.unit
def test_scripted_chat_model_responses():
    model = ScriptedChatModel(scripted_responses=[AIMessage(content="Hello test")])
    res = model.invoke([HumanMessage(content="hi")])
    assert res.content == "Hello test"
    assert len(model.call_history) == 1


@pytest.mark.unit
def test_scripted_chat_model_timeout_mode():
    model = ScriptedChatModel(mode="timeout")
    with pytest.raises(httpx.TimeoutException):
        model.invoke([HumanMessage(content="hi")])


@pytest.mark.unit
def test_scripted_chat_model_auth_error_mode():
    model = ScriptedChatModel(mode="auth_error")
    with pytest.raises(PermissionError):
        model.invoke([HumanMessage(content="hi")])


@pytest.mark.unit
def test_fake_scraper_yields_fixtures():
    scraper = FakeScraper()
    records = list(scraper.scrape(params={"limit": 10}))
    assert len(records) >= 1
    assert records[0]["source_code"] == "fake_source"
    scraper.close()
    assert scraper.is_closed is True


@pytest.mark.unit
def test_fake_rag_transport_contract_v1():
    transport = FakeRAGTransport(expected_token="valid-token", state="ready")
    client = httpx.Client(transport=transport, base_url="http://rag-service")

    # Test 401 unauthorized without token
    res = client.get("/v1/status")
    assert res.status_code == 401

    # Test status with token
    headers = {"x-rag-service-token": "valid-token"}
    res = client.get("/v1/status", headers=headers)
    assert res.status_code == 200
    assert res.json()["state"] == "ready"
    assert res.json()["available"] is True

    # Test search
    res = client.post("/v1/search", json={"query": "roofing", "topK": 2}, headers=headers)
    assert res.status_code == 200
    assert len(res.json()["hits"]) >= 1

    # Test 409 when not ready
    transport.state = "not_configured"
    res = client.post("/v1/search", json={"query": "roofing"}, headers=headers)
    assert res.status_code == 409
