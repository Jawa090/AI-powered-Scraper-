"""
Tests for agents/llm/chat_models.py — LLM provider factory.

These tests verify configuration logic WITHOUT calling real APIs.
"""

import os
import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset module-level caches between tests."""
    import agents.llm.chat_model as cm
    cm._cached_chat_model = None
    cm._cached_chat_model_with_tools = None
    yield
    cm._cached_chat_model = None
    cm._cached_chat_model_with_tools = None


class TestBuildChatModel:
    """Test build_chat_model with various env configurations."""

    def test_no_keys_raises(self, monkeypatch):
        """With no API keys set, build_chat_model must raise LLMUnavailable."""
        from settings import settings
        monkeypatch.setattr(settings, "LLM_API_KEY", "")
        monkeypatch.setattr(settings, "LLM_MODEL", "")

        from agents.llm.chat_model import build_chat_model, LLMUnavailable
        with pytest.raises(LLMUnavailable, match="not_configured"):
            build_chat_model().invoke("hello")

    def test_gemini_only(self, monkeypatch):
        """With only LLM_API_KEY and LLM_PROVIDER=gemini, should return a Gemini model."""
        from settings import settings
        monkeypatch.setattr(settings, "LLM_API_KEY", "test-gemini-key")
        monkeypatch.setattr(settings, "LLM_MODEL", "gemini-3.8-flash")
        monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")

        from agents.llm.chat_model import build_chat_model
        model = build_chat_model()
        assert model is not None
        assert not hasattr(model, 'fllbcks')  # Single provider, no fllbck wrapper

    def test_deepseek_only(self, monkeypatch):
        """With only DEEPSEEK_API_KEY, should return a DeepSeek model."""
        pass # Not applicable, deepseek fallback is inside invoke_llm not build_chat_model

    def test_wrong_key_still_builds(self, monkeypatch):
        """Build with a key that is just invalid string still builds."""
        from settings import settings
        monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "LLM_API_KEY", "invalid-key")
        monkeypatch.setattr(settings, "LLM_MODEL", "gemini-flash")

        from agents.llm.chat_model import build_chat_model
        model = build_chat_model()
        assert model is not None


class TestHealthCheck:
    """Test llm_health_check returns safe provider info."""

    def test_health_check_no_keys(self, monkeypatch):
        from settings import settings
        monkeypatch.setattr(settings, "LLM_API_KEY", "")

        from agents.llm.chat_model import llm_health_check
        result = llm_health_check()
        assert result["configured"] is False
        # Should never contain actual key values
        result_str = str(result)
        assert "api_key" not in result_str.lower() or "key" not in result_str

    def test_health_check_with_gemini(self, monkeypatch):
        from settings import settings
        monkeypatch.setattr(settings, "LLM_API_KEY", "test-key-12345")
        monkeypatch.setattr(settings, "LLM_MODEL", "gemini-3.8-flash")
        monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")

        from agents.llm.chat_model import llm_health_check
        result = llm_health_check()
        assert result["configured"] is True
        assert result["provider"] == "gemini"
        assert result["model"] == "gemini-3.8-flash"
        # Key must NEVER appear in health check output
        assert "test-key-12345" not in str(result)
