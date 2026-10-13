"""
tests/unit/test_chat_model.py
──────────────────────────────
Unit tests for agents/llm/chat_model.py.
Verifies single provider instantiation, absence of fallbacks, bounded retry behavior,
error classification, probe, health check, and HTTP 503 D4 error format.
"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.genai.errors import APIError
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agents.llm.chat_model import (
    LLMUnavailable,
    _classify_error,
    clear_cache,
    get_chat_model,
    invoke_llm,
    invoke_structured,
    llm_health_check,
    probe,
)


@pytest.fixture(autouse=True)
def _reset_model_cache():
    """Ensure clean cache before and after every test."""
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Decision D4 Payload & Error Format Tests
# ---------------------------------------------------------------------------

class TestD4ErrorFormat:
    """Validate compliance with Decision D4 format and HTTP 503 status."""

    def test_d4_payload_structure(self):
        exc = LLMUnavailable(reason="timeout", detail="Connection timed out after 30s")
        assert exc.status_code == 503

        d4_payload = exc.to_dict()
        assert d4_payload == {
            "success": False,
            "error": {
                "code": "LLM_UNAVAILABLE",
                "reason": "timeout",
                "message": "The AI API is not responding. Please try again.",
            },
        }

    @pytest.mark.parametrize(
        "reason",
        ["not_configured", "timeout", "auth_error", "rate_limited", "provider_error"],
    )
    def test_d4_reasons_preserved(self, reason):
        exc = LLMUnavailable(reason=reason, detail="Error detail")
        assert exc.reason == reason
        d4 = exc.to_dict()
        assert d4["error"]["reason"] == reason
        assert d4["error"]["code"] == "LLM_UNAVAILABLE"
        assert d4["error"]["message"] == "The AI API is not responding. Please try again."

    def test_d4_to_response_is_http_503(self):
        exc = LLMUnavailable(reason="rate_limited", detail="Quota exhausted")
        resp = exc.to_response()
        assert resp.status_code == 503
        body = json.loads(resp.body.decode("utf-8"))
        assert body["success"] is False
        assert body["error"]["code"] == "LLM_UNAVAILABLE"
        assert body["error"]["reason"] == "rate_limited"


# ---------------------------------------------------------------------------
# Single Provider & No Fallback Chain Tests
# ---------------------------------------------------------------------------

class TestSingleProviderNoFallback:
    """Validate that only a single configured provider is instantiated without fallbacks."""

    def test_empty_key_or_model_raises_not_configured(self):
        with pytest.raises(LLMUnavailable) as exc_info:
            get_chat_model(
                provider="gemini",
                model="",
                api_key="",
                force_refresh=True,
            )
        assert exc_info.value.reason == "not_configured"

        with pytest.raises(LLMUnavailable) as exc_info:
            get_chat_model(
                provider="gemini",
                model="gemini-2.5-flash",
                api_key="",
                force_refresh=True,
            )
        assert exc_info.value.reason == "not_configured"

    def test_gemini_single_provider_instance(self):
        model = get_chat_model(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="fake-test-key",
            force_refresh=True,
        )
        assert isinstance(model, ChatGoogleGenerativeAI)
        # Verify strict single provider — no .fallbacks attribute
        assert not hasattr(model, "fallbacks")
        assert model.max_retries == 0

    def test_openai_compatible_single_provider_instance(self):
        model = get_chat_model(
            provider="openai_compatible",
            model="gpt-4o-mini",
            api_key="fake-test-key",
            base_url="https://api.openai.com/v1",
            force_refresh=True,
        )
        assert isinstance(model, ChatOpenAI)
        # Verify strict single provider — no .fallbacks attribute
        assert not hasattr(model, "fallbacks")
        assert model.max_retries == 0

    def test_no_fallback_provider_constructed(self, monkeypatch):
        """Even if environment variables for other providers exist, only the single configured one is built."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-key")
        monkeypatch.setenv("NVIDIA_API_KEY", "unused-key")

        model = get_chat_model(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="gemini-key",
            force_refresh=True,
        )
        assert isinstance(model, ChatGoogleGenerativeAI)
        assert not hasattr(model, "fallbacks")

    def test_thinking_level_configured_on_gemini(self):
        model_low = get_chat_model(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="fake-test-key",
            thinking_level="low",
            force_refresh=True,
        )
        assert model_low.thinking_budget == 1024

        model_high = get_chat_model(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="fake-test-key",
            thinking_level="high",
            force_refresh=True,
        )
        assert model_high.thinking_budget == 8192

    def test_cache_by_tools_tuple(self):
        m1 = get_chat_model(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="fake-test-key",
            tools=None,
            force_refresh=False,
        )
        m2 = get_chat_model(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="fake-test-key",
            tools=None,
            force_refresh=False,
        )
        assert m1 is m2


# ---------------------------------------------------------------------------
# Error Classification Tests
# ---------------------------------------------------------------------------

class TestErrorClassification:
    """Validate mapping table: auth->auth_error(no retry), 429->rate_limited(yes), timeout->timeout(yes), 5xx->provider_error(yes), other->provider_error(no)."""

    def test_auth_error_not_retryable(self):
        r, retry = _classify_error(PermissionError("401 Unauthorized: Invalid API key"))
        assert r == "auth_error"
        assert retry is False

        r, retry = _classify_error(APIError(401, "API key not valid"))
        assert r == "auth_error"
        assert retry is False

        r, retry = _classify_error(APIError(403, "Permission Denied"))
        assert r == "auth_error"
        assert retry is False

    def test_timeout_retryable(self):
        r, retry = _classify_error(httpx.ReadTimeout("Read timed out"))
        assert r == "timeout"
        assert retry is True

        r, retry = _classify_error(TimeoutError("Connection timed out"))
        assert r == "timeout"
        assert retry is True

        r, retry = _classify_error(httpx.ConnectError("Failed to connect to host"))
        assert r == "timeout"
        assert retry is True

    def test_rate_limited_retryable(self):
        r, retry = _classify_error(APIError(429, "Resource exhausted / rate limit exceeded"))
        assert r == "rate_limited"
        assert retry is True

    def test_5xx_provider_error_retryable(self):
        r, retry = _classify_error(APIError(500, "Internal server error"))
        assert r == "provider_error"
        assert retry is True

        r, retry = _classify_error(APIError(503, "Service unavailable"))
        assert r == "provider_error"
        assert retry is True

    def test_unclassified_error_not_retryable(self):
        r, retry = _classify_error(ValueError("Invalid argument in prompt"))
        assert r == "provider_error"
        assert retry is False


# ---------------------------------------------------------------------------
# Bounded Retry Behavior Tests
# ---------------------------------------------------------------------------

class TestBoundedRetry:
    """Validate retry counts: zero retries on auth_error, bounded retries on transient errors."""

    def test_auth_error_zero_retries(self):
        mock_model = MagicMock()
        mock_model.invoke.side_effect = PermissionError("Invalid API Key")

        with pytest.raises(LLMUnavailable) as exc_info:
            invoke_llm(
                mock_model,
                [HumanMessage(content="hi")],
                max_retries=3,
                retry_delay=0.0,
            )

        assert exc_info.value.reason == "auth_error"
        # Zero retries: called exactly 1 time
        assert mock_model.invoke.call_count == 1

    def test_timeout_retried_up_to_max_retries(self):
        mock_model = MagicMock()
        mock_model.invoke.side_effect = httpx.ReadTimeout("Request timed out")

        with pytest.raises(LLMUnavailable) as exc_info:
            invoke_llm(
                mock_model,
                [HumanMessage(content="hi")],
                max_retries=2,
                retry_delay=0.0,
            )

        assert exc_info.value.reason == "timeout"
        # Initial attempt + 2 retries = 3 calls
        assert mock_model.invoke.call_count == 3

    def test_rate_limited_retried_up_to_max_retries(self):
        mock_model = MagicMock()
        mock_model.invoke.side_effect = APIError(429, "Rate limit reached")

        with pytest.raises(LLMUnavailable) as exc_info:
            invoke_llm(
                mock_model,
                [HumanMessage(content="hi")],
                max_retries=3,
                retry_delay=0.0,
            )

        assert exc_info.value.reason == "rate_limited"
        # Initial attempt + 3 retries = 4 calls
        assert mock_model.invoke.call_count == 4

    def test_5xx_retried_up_to_max_retries(self):
        mock_model = MagicMock()
        mock_model.invoke.side_effect = APIError(503, "Service temporarily unavailable")

        with pytest.raises(LLMUnavailable) as exc_info:
            invoke_llm(
                mock_model,
                [HumanMessage(content="hi")],
                max_retries=1,
                retry_delay=0.0,
            )

        assert exc_info.value.reason == "provider_error"
        # Initial attempt + 1 retry = 2 calls
        assert mock_model.invoke.call_count == 2

    def test_transient_error_recovers_on_retry(self):
        mock_model = MagicMock()
        expected_response = AIMessage(content="Hello after recovery")
        mock_model.invoke.side_effect = [
            httpx.ReadTimeout("First attempt timed out"),
            expected_response,
        ]

        result = invoke_llm(
            mock_model,
            [HumanMessage(content="hi")],
            max_retries=2,
            retry_delay=0.0,
        )

        assert result == expected_response
        assert mock_model.invoke.call_count == 2

    def test_unclassified_error_zero_retries(self):
        mock_model = MagicMock()
        mock_model.invoke.side_effect = TypeError("Malformed parameter")

        with pytest.raises(LLMUnavailable) as exc_info:
            invoke_llm(
                mock_model,
                [HumanMessage(content="hi")],
                max_retries=3,
                retry_delay=0.0,
            )

        assert exc_info.value.reason == "provider_error"
        # Zero retries: called exactly 1 time
        assert mock_model.invoke.call_count == 1


# ---------------------------------------------------------------------------
# Structured Output Invocation Tests
# ---------------------------------------------------------------------------

class TestInvokeStructured:
    """Validate invoke_structured error mapping and retry bounds."""

    class DecisionSchema(BaseModel):
        decision: str

    def test_structured_retry_exhaustion(self):
        mock_model = MagicMock()
        mock_runnable = MagicMock()
        mock_model.with_structured_output.return_value = mock_runnable
        mock_runnable.invoke.side_effect = APIError(500, "Internal Server Error")

        with pytest.raises(LLMUnavailable) as exc_info:
            invoke_structured(
                schema=self.DecisionSchema,
                messages=[HumanMessage(content="classify")],
                model=mock_model,
                max_retries=2,
                retry_delay=0.0,
            )

        assert exc_info.value.reason == "provider_error"
        assert mock_runnable.invoke.call_count == 3

    def test_structured_success_after_transient(self):
        mock_model = MagicMock()
        mock_runnable = MagicMock()
        mock_model.with_structured_output.return_value = mock_runnable
        success_obj = self.DecisionSchema(decision="approve")
        mock_runnable.invoke.side_effect = [
            httpx.ReadTimeout("Timeout"),
            success_obj,
        ]

        result = invoke_structured(
            schema=self.DecisionSchema,
            messages=[HumanMessage(content="classify")],
            model=mock_model,
            max_retries=2,
            retry_delay=0.0,
        )

        assert result == success_obj
        assert mock_runnable.invoke.call_count == 2


# ---------------------------------------------------------------------------
# Probe & Health Check Tests
# ---------------------------------------------------------------------------

class TestProbeAndHealth:
    """Validate probe and health check outputs never leak keys."""

    def test_probe_not_configured_when_empty_key(self, monkeypatch):
        monkeypatch.setattr("settings.settings.LLM_API_KEY", "")
        res = probe()
        assert res["reachable"] is False
        assert res["reason"] == "not_configured"

    @patch("agents.llm.chat_model.invoke_llm")
    @patch("agents.llm.chat_model.get_chat_model")
    def test_probe_successful(self, mock_get, mock_inv, monkeypatch):
        monkeypatch.setattr("settings.settings.LLM_API_KEY", "real-key")
        monkeypatch.setattr("settings.settings.LLM_MODEL", "gemini-2.5-flash")
        monkeypatch.setattr("settings.settings.LLM_PROVIDER", "gemini")

        mock_get.return_value = MagicMock()
        mock_inv.return_value = AIMessage(content="pong")

        res = probe()
        assert res["reachable"] is True
        assert res["reason"] == ""
        assert res["provider"] == "gemini"
        assert res["model"] == "gemini-2.5-flash"
        assert "latency_ms" in res
        assert "key" not in str(res).lower()

    @patch("agents.llm.chat_model.invoke_llm")
    @patch("agents.llm.chat_model.get_chat_model")
    def test_probe_failure_reports_reason(self, mock_get, mock_inv, monkeypatch):
        monkeypatch.setattr("settings.settings.LLM_API_KEY", "real-key")
        monkeypatch.setattr("settings.settings.LLM_MODEL", "gemini-2.5-flash")
        monkeypatch.setattr("settings.settings.LLM_PROVIDER", "gemini")

        mock_get.return_value = MagicMock()
        mock_inv.side_effect = LLMUnavailable(reason="auth_error", detail="Invalid API key")

        res = probe()
        assert res["reachable"] is False
        assert res["reason"] == "auth_error"

    def test_health_check_does_not_expose_key(self, monkeypatch):
        monkeypatch.setattr("settings.settings.LLM_API_KEY", "secret-key-12345")
        monkeypatch.setattr("settings.settings.LLM_MODEL", "gemini-2.5-flash")
        monkeypatch.setattr("settings.settings.LLM_PROVIDER", "gemini")

        res = llm_health_check(probe_mode=False)
        assert res["configured"] is True
        assert res["provider"] == "gemini"
        assert res["model"] == "gemini-2.5-flash"
        # API key must NEVER appear in output
        res_str = json.dumps(res)
        assert "secret-key-12345" not in res_str
        assert "api_key" not in res_str.lower()


# ---------------------------------------------------------------------------
# FastAPI D4 Exception Handler Integration Test
# ---------------------------------------------------------------------------

class TestFastAPIExceptionHandling:
    """Validate that LLMUnavailable raised in FastAPI returns HTTP 503 in D4 format."""

    def test_fastapi_returns_503_d4(self):
        from fastapi.testclient import TestClient
        from app import app

        # Define temporary test route raising LLMUnavailable
        @app.get("/test/llm-failure-endpoint")
        def route_raising():
            raise LLMUnavailable(reason="timeout", detail="Upstream Gemini timed out")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test/llm-failure-endpoint")

        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "LLM_UNAVAILABLE"
        assert data["error"]["reason"] == "timeout"
        assert data["error"]["message"] == "The AI API is not responding. Please try again."
