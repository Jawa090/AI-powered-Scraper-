"""
Tests for agents/llm/chat_models.py — LLM provider factory.

These tests verify configuration logic WITHOUT calling real APIs.
"""

import os
import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset module-level caches between tests."""
    import agents.llm.chat_models as cm
    cm._cached_chat_model = None
    cm._cached_chat_model_with_tools = None
    yield
    cm._cached_chat_model = None
    cm._cached_chat_model_with_tools = None


class TestBuildChatModel:
    """Test build_chat_model with various env configurations."""

    def test_no_keys_raises(self, monkeypatch):
        """With no API keys set, build_chat_model must raise EnvironmentError."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

        from agents.llm.chat_models import build_chat_model
        with pytest.raises(EnvironmentError, match="No LLM provider configured"):
            build_chat_model()

    def test_gemini_only(self, monkeypatch):
        """With only GEMINI_API_KEY, should return a Gemini model."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

        from agents.llm.chat_models import build_chat_model
        model = build_chat_model()
        # Should be a ChatGoogleGenerativeAI instance (not a fallback wrapper)
        assert model is not None
        assert not hasattr(model, 'fallbacks')  # Single provider, no fallback wrapper

    def test_deepseek_only(self, monkeypatch):
        """With only DEEPSEEK_API_KEY, should return a DeepSeek model."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

        from agents.llm.chat_models import build_chat_model
        model = build_chat_model()
        assert model is not None

    def test_both_providers_creates_fallback(self, monkeypatch):
        """With both keys, should create a fallback chain."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

        from agents.llm.chat_models import build_chat_model
        model = build_chat_model()
        assert model is not None
        # The model returned by .with_fallbacks() has a 'fallbacks' attribute
        assert hasattr(model, 'fallbacks')

    def test_wrong_key_still_builds(self, monkeypatch):
        """Build should succeed with invalid keys — failure happens at invoke time."""
        monkeypatch.setenv("GEMINI_API_KEY", "invalid-key")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

        from agents.llm.chat_models import build_chat_model
        model = build_chat_model()
        assert model is not None


class TestHealthCheck:
    """Test llm_health_check returns safe provider info."""

    def test_health_check_no_keys(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

        from agents.llm.chat_models import llm_health_check
        result = llm_health_check()
        assert result["available"] is False
        # Should never contain actual key values
        result_str = str(result)
        assert "api_key" not in result_str.lower() or "key" not in result_str

    def test_health_check_with_gemini(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-12345")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        from agents.llm.chat_models import llm_health_check
        result = llm_health_check()
        assert result["available"] is True
        gemini = [p for p in result["providers"] if p["provider"] == "gemini"][0]
        assert gemini["configured"] is True
        assert gemini["model"] == "gemini-3.8-flash"
        # Key must NEVER appear in health check output
        assert "test-key-12345" not in str(result)
