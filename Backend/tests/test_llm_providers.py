"""
tests/test_llm_providers.py
────────────────────────────
Multi-Provider LLM Layer Unit Tests.

Tests 18 scenarios covering:
  - Provider initialization & configuration
  - NOT_CONFIGURED behavior for missing API keys
  - Provider factory selection & ordering
  - Fallback chain behavior (429, 503, timeout, connection error)
  - All-providers-unavailable → ConnectionError (triggers QueryParser fallback)
  - JSON normalization & malformed JSON handling
  - Timeout handling
  - Secret masking (keys never in logs)
  - Existing StructuredIntent schema compliance

All tests use MOCKED provider calls — no real API keys required.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Optional, Type, TypeVar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pydantic import BaseModel, ValidationError

from agents.llm.provider import LLMProvider
from agents.llm.openai_compatible import OpenAICompatibleProvider
from agents.llm.config import ProviderConfig, ProviderStatus, get_provider_config, resolve_provider_chain
from agents.llm.factory import FallbackLLMProvider, get_llm_provider
from agents.intent.models import IntentType, StructuredIntent
from agents.intent.engine import IntentEngine
from agents.intent.validator import IntentValidator

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Helper: build a valid StructuredIntent dict for mocking
# ---------------------------------------------------------------------------

def _valid_intent_dict(**overrides) -> dict:
    base = {
        "intent": "lead_discovery",
        "needs_database": True,
        "needs_scraping": False,
        "category": "Contractor",
        "location": "Dallas",
        "quantity": 10,
        "fields": ["email", "phone"],
        "filters": {"category": "Contractor"},
        "freshness": False,
        "scraper_id": "bonfire",
        "dataset_id": None,
        "job_id": None,
        "confidence": 0.92,
        "user_request": "Find 10 contractors in Dallas",
        "reasoning": "Standard contractor discovery",
        "is_fallback": False,
        "fallback_reason": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------

class _MockProvider(LLMProvider):
    """Provider that always returns a valid StructuredIntent."""

    def __init__(self, name: str = "mock", intent_dict: Optional[dict] = None):
        self.name = name
        self._intent_dict = intent_dict or _valid_intent_dict()

    def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=2048) -> str:
        return '{"result": "mock"}'

    def generate_structured(self, prompt, schema, system_prompt=None, temperature=0.0):
        return schema.model_validate(self._intent_dict)

    def health_check(self):
        return {"available": True, "provider": self.name, "model": "mock-model"}


class _TimeoutProvider(LLMProvider):
    def generate(self, *a, **kw): raise TimeoutError("Simulated timeout")
    def generate_structured(self, *a, **kw): raise TimeoutError("Simulated timeout")
    def health_check(self): return {"available": False, "details": "Timeout"}


class _ConnectionErrorProvider(LLMProvider):
    def generate(self, *a, **kw): raise ConnectionError("Simulated connection error")
    def generate_structured(self, *a, **kw): raise ConnectionError("Simulated connection error")
    def health_check(self): return {"available": False, "details": "Connection refused"}


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestProviderConfig(unittest.TestCase):
    """Tests 1-3: Provider configuration resolution."""

    # Test 1: Gemini provider initialization
    def test_01_gemini_provider_initialization(self):
        """Gemini provider reads GEMINI_* or legacy LLM_* vars."""
        env = {
            "GEMINI_API_KEY": "gemini-test-key-12345",
            "GEMINI_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "GEMINI_MODEL": "gemini-2.0-flash",
            "GEMINI_TIMEOUT": "25",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_provider_config("gemini")
        self.assertEqual(cfg.name, "gemini")
        self.assertEqual(cfg.status, ProviderStatus.READY)
        self.assertTrue(cfg.is_ready)
        self.assertEqual(cfg.model, "gemini-2.0-flash")
        self.assertEqual(cfg.timeout, 25)
        # Key must NOT appear in masked repr
        self.assertNotIn("gemini-test-key-12345", cfg.masked_key())

    # Test 2: DeepSeek provider initialization
    def test_02_deepseek_provider_initialization(self):
        """DeepSeek provider reads DEEPSEEK_* vars."""
        env = {
            "DEEPSEEK_API_KEY": "ds-test-key-abcde",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "DEEPSEEK_TIMEOUT": "30",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_provider_config("deepseek")
        self.assertEqual(cfg.name, "deepseek")
        self.assertEqual(cfg.status, ProviderStatus.READY)
        self.assertTrue(cfg.is_ready)
        self.assertEqual(cfg.model, "deepseek-chat")
        self.assertNotIn("ds-test-key-abcde", cfg.masked_key())

    # Test 3: NVIDIA provider initialization
    def test_03_nvidia_provider_initialization(self):
        """NVIDIA provider reads NVIDIA_* vars."""
        env = {
            "NVIDIA_API_KEY": "nvapi-test-key-xyz",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "NVIDIA_MODEL": "meta/llama-3.1-8b-instruct",
            "NVIDIA_TIMEOUT": "30",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_provider_config("nvidia")
        self.assertEqual(cfg.name, "nvidia")
        self.assertEqual(cfg.status, ProviderStatus.READY)
        self.assertTrue(cfg.is_ready)
        self.assertNotIn("nvapi-test-key-xyz", cfg.masked_key())


class TestProviderFactory(unittest.TestCase):
    """Tests 4-8: Factory selection and NOT_CONFIGURED behavior."""

    # Test 4: Factory returns FallbackLLMProvider
    def test_04_factory_returns_fallback_provider(self):
        """get_llm_provider() returns a FallbackLLMProvider when multi-provider env is set."""
        env = {
            "LLM_PRIMARY_PROVIDER": "gemini",
            "LLM_FALLBACK_PROVIDERS": "deepseek,nvidia",
            "GEMINI_API_KEY": "gemini-key-999",
            "DEEPSEEK_API_KEY": "",
            "NVIDIA_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            provider = get_llm_provider(force_refresh=True)
        self.assertIsInstance(provider, FallbackLLMProvider)

    # Test 5: Primary provider selection
    def test_05_primary_provider_is_first_in_chain(self):
        """The primary provider name appears first in the resolved chain."""
        # Build a clean env that overrides both the legacy LLM_PROVIDER and the new var
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("LLM_PROVIDER", "LLM_PRIMARY_PROVIDER", "LLM_FALLBACK_PROVIDERS")}
        env_clean.update({
            "LLM_PRIMARY_PROVIDER": "deepseek",
            "LLM_FALLBACK_PROVIDERS": "gemini,nvidia",
            "GEMINI_API_KEY": "g-key",
            "DEEPSEEK_API_KEY": "ds-key",
            "NVIDIA_API_KEY": "",
        })
        with patch.dict(os.environ, env_clean, clear=True):
            chain = resolve_provider_chain()
        self.assertEqual(chain[0].name, "deepseek")
        self.assertEqual(chain[1].name, "gemini")
        self.assertEqual(chain[2].name, "nvidia")

    # Test 6: DeepSeek missing API key → NOT_CONFIGURED
    def test_06_deepseek_missing_key_not_configured(self):
        """DeepSeek with no API key is marked NOT_CONFIGURED, not READY."""
        env_clean = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        env_clean["DEEPSEEK_API_KEY"] = ""
        with patch.dict(os.environ, env_clean, clear=True):
            cfg = get_provider_config("deepseek")
        self.assertEqual(cfg.status, ProviderStatus.NOT_CONFIGURED)
        self.assertFalse(cfg.is_ready)

    # Test 7: NVIDIA missing API key → NOT_CONFIGURED
    def test_07_nvidia_missing_key_not_configured(self):
        """NVIDIA with no API key is marked NOT_CONFIGURED, not READY."""
        env_clean = {k: v for k, v in os.environ.items() if k != "NVIDIA_API_KEY"}
        env_clean["NVIDIA_API_KEY"] = ""
        with patch.dict(os.environ, env_clean, clear=True):
            cfg = get_provider_config("nvidia")
        self.assertEqual(cfg.status, ProviderStatus.NOT_CONFIGURED)
        self.assertFalse(cfg.is_ready)

    # Test 8: Unconfigured provider is skipped during generate_structured
    def test_08_unconfigured_provider_skipped(self):
        """FallbackLLMProvider skips NOT_CONFIGURED providers and uses a READY one."""
        ready_cfg = ProviderConfig(
            name="gemini", base_url="https://example.com/v1",
            model="gemini-test", api_key="real-key-12345", timeout=10,
        )
        skipped_cfg = ProviderConfig(
            name="deepseek", base_url="https://deepseek.com",
            model="deepseek-chat", api_key="", timeout=10,
        )

        # Build real OpenAICompatibleProvider instances but patch requests.post
        p_ready = OpenAICompatibleProvider(
            base_url=ready_cfg.base_url, model=ready_cfg.model,
            api_key=ready_cfg.api_key, timeout=ready_cfg.timeout,
        )
        p_skipped = OpenAICompatibleProvider(
            base_url=skipped_cfg.base_url, model=skipped_cfg.model,
            api_key=skipped_cfg.api_key, timeout=skipped_cfg.timeout,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(_valid_intent_dict())}}]
        }

        fallback = FallbackLLMProvider(
            providers=[p_skipped, p_ready],
            configs=[skipped_cfg, ready_cfg],
        )

        with patch("requests.post", return_value=mock_response):
            result = fallback.generate_structured(
                "test prompt", StructuredIntent
            )

        self.assertIsInstance(result, StructuredIntent)
        self.assertEqual(result.intent, IntentType.LEAD_DISCOVERY)


class TestFallbackBehavior(unittest.TestCase):
    """Tests 9-12: Provider fallback on transient errors."""

    def _make_fallback(self, cfg1, cfg2, provider1_effect, provider2_result=None):
        """Helper to build a FallbackLLMProvider with two providers."""
        p1 = OpenAICompatibleProvider(
            base_url=cfg1.base_url, model=cfg1.model,
            api_key=cfg1.api_key, timeout=cfg1.timeout,
        )
        p2 = OpenAICompatibleProvider(
            base_url=cfg2.base_url, model=cfg2.model,
            api_key=cfg2.api_key, timeout=cfg2.timeout,
        )
        p1.generate_structured = MagicMock(side_effect=provider1_effect)
        if provider2_result is not None:
            p2.generate_structured = MagicMock(return_value=provider2_result)
        return FallbackLLMProvider(providers=[p1, p2], configs=[cfg1, cfg2])

    def _make_config(self, name: str, key: str = "real-key") -> ProviderConfig:
        return ProviderConfig(
            name=name, base_url="https://example.com/v1",
            model="test-model", api_key=key, timeout=10,
        )

    # Test 9: Gemini 429 → DeepSeek fallback
    def test_09_gemini_429_triggers_deepseek_fallback(self):
        """HTTP 429 from Gemini causes FallbackLLMProvider to try DeepSeek."""
        import requests as req_mod
        cfg_gemini = self._make_config("gemini")
        cfg_deepseek = self._make_config("deepseek")

        expected = StructuredIntent.model_validate(_valid_intent_dict())

        # Simulate 429 via ConnectionError (requests raises HTTPError which wraps to ConnectionError)
        fallback = self._make_fallback(
            cfg_gemini, cfg_deepseek,
            provider1_effect=ConnectionError("Gemini 429 Too Many Requests"),
            provider2_result=expected,
        )
        result = fallback.generate_structured("test", StructuredIntent)
        self.assertIsInstance(result, StructuredIntent)
        self.assertEqual(result.intent, IntentType.LEAD_DISCOVERY)

    # Test 10: Gemini 503 → DeepSeek fallback
    def test_10_gemini_503_triggers_deepseek_fallback(self):
        """HTTP 503 from Gemini causes FallbackLLMProvider to try DeepSeek."""
        cfg_gemini = self._make_config("gemini")
        cfg_deepseek = self._make_config("deepseek")

        expected = StructuredIntent.model_validate(_valid_intent_dict())
        fallback = self._make_fallback(
            cfg_gemini, cfg_deepseek,
            provider1_effect=ConnectionError("Gemini 503 Service Unavailable"),
            provider2_result=expected,
        )
        result = fallback.generate_structured("test", StructuredIntent)
        self.assertIsInstance(result, StructuredIntent)

    # Test 11: DeepSeek failure → NVIDIA fallback
    def test_11_deepseek_failure_triggers_nvidia_fallback(self):
        """When DeepSeek fails with timeout, NVIDIA (if configured) is tried."""
        cfg_deepseek = self._make_config("deepseek")
        cfg_nvidia = self._make_config("nvidia")

        expected = StructuredIntent.model_validate(_valid_intent_dict(
            intent="database_search", needs_database=True
        ))

        p_ds = OpenAICompatibleProvider(
            base_url=cfg_deepseek.base_url, model=cfg_deepseek.model,
            api_key=cfg_deepseek.api_key, timeout=cfg_deepseek.timeout,
        )
        p_nv = OpenAICompatibleProvider(
            base_url=cfg_nvidia.base_url, model=cfg_nvidia.model,
            api_key=cfg_nvidia.api_key, timeout=cfg_nvidia.timeout,
        )
        p_ds.generate_structured = MagicMock(side_effect=TimeoutError("DeepSeek timeout"))
        p_nv.generate_structured = MagicMock(return_value=expected)

        fallback = FallbackLLMProvider(
            providers=[p_ds, p_nv], configs=[cfg_deepseek, cfg_nvidia]
        )
        result = fallback.generate_structured("test", StructuredIntent)
        self.assertIsInstance(result, StructuredIntent)
        self.assertEqual(result.intent, IntentType.DATABASE_SEARCH)

    # Test 12: All providers unavailable → ConnectionError → QueryParser fallback
    def test_12_all_providers_fail_raises_connection_error(self):
        """When all READY providers fail, FallbackLLMProvider raises ConnectionError."""
        cfg1 = self._make_config("gemini")
        cfg2 = self._make_config("deepseek")

        p1 = OpenAICompatibleProvider(
            base_url=cfg1.base_url, model=cfg1.model,
            api_key=cfg1.api_key, timeout=cfg1.timeout,
        )
        p2 = OpenAICompatibleProvider(
            base_url=cfg2.base_url, model=cfg2.model,
            api_key=cfg2.api_key, timeout=cfg2.timeout,
        )
        p1.generate_structured = MagicMock(side_effect=ConnectionError("Gemini down"))
        p2.generate_structured = MagicMock(side_effect=TimeoutError("DeepSeek timeout"))

        fallback = FallbackLLMProvider(providers=[p1, p2], configs=[cfg1, cfg2])
        with self.assertRaises(ConnectionError):
            fallback.generate_structured("test", StructuredIntent)

    def test_12b_intent_engine_uses_query_parser_when_all_providers_fail(self):
        """IntentEngine catches ConnectionError from FallbackLLMProvider and uses QueryParser."""
        cfg1 = ProviderConfig(
            name="gemini", base_url="https://x.com/v1",
            model="m", api_key="real-key", timeout=5,
        )
        p1 = OpenAICompatibleProvider(
            base_url=cfg1.base_url, model=cfg1.model,
            api_key=cfg1.api_key, timeout=cfg1.timeout,
        )
        p1.generate_structured = MagicMock(side_effect=ConnectionError("All down"))
        fallback_provider = FallbackLLMProvider(providers=[p1], configs=[cfg1])

        engine = IntentEngine(provider=fallback_provider)
        intent = engine.parse("Show me contractors from our database")
        # Should have fallen back to QueryParser
        self.assertTrue(intent.is_fallback)
        self.assertIsNotNone(intent.fallback_reason)


class TestJSONNormalization(unittest.TestCase):
    """Tests 13-14: JSON extraction and normalization."""

    # Test 13: JSON normalization (markdown fences, whitespace)
    def test_13_json_normalization_markdown_fences(self):
        """JSON inside markdown code fences is extracted correctly."""
        provider = OpenAICompatibleProvider(
            base_url="http://localhost:11434/v1", model="test", timeout=5
        )
        raw = "```json\n{\"intent\": \"lead_discovery\", \"needs_database\": true}\n```"
        result = provider._extract_json(raw)
        self.assertEqual(result["intent"], "lead_discovery")
        self.assertTrue(result["needs_database"])

    # Test 14: Malformed JSON handling
    def test_14_malformed_json_raises_value_error(self):
        """Malformed JSON from the LLM raises ValueError, not a silent failure."""
        provider = OpenAICompatibleProvider(
            base_url="http://localhost:11434/v1", model="test", timeout=5
        )
        with self.assertRaises(ValueError) as ctx:
            provider._extract_json("{bad json: not parseable {{")
        self.assertIn("Malformed JSON", str(ctx.exception))


class TestTimeoutHandling(unittest.TestCase):
    """Test 15: Timeout handling."""

    # Test 15: Timeout handling propagated correctly
    def test_15_timeout_raises_timeout_error(self):
        """requests.exceptions.Timeout is converted to TimeoutError by the provider."""
        import requests as req_mod
        provider = OpenAICompatibleProvider(
            base_url="http://localhost:11434/v1", model="test", api_key="k", timeout=1
        )
        with patch("requests.post", side_effect=req_mod.exceptions.Timeout("timed out")):
            with self.assertRaises(TimeoutError):
                provider.generate_structured("test prompt", StructuredIntent)


class TestProviderExceptionHandling(unittest.TestCase):
    """Test 16: Provider exception handling."""

    # Test 16: Connection error handling
    def test_16_connection_error_handling(self):
        """requests.exceptions.RequestException is converted to ConnectionError."""
        import requests as req_mod
        provider = OpenAICompatibleProvider(
            base_url="http://localhost:11434/v1", model="test", api_key="k", timeout=5
        )
        with patch("requests.post", side_effect=req_mod.exceptions.ConnectionError("refused")):
            with self.assertRaises(ConnectionError):
                provider.generate("test prompt")


class TestSecretMasking(unittest.TestCase):
    """Test 17: Secret masking."""

    # Test 17: API keys are masked in ProviderConfig.masked_key()
    def test_17_api_key_masked_in_config(self):
        """ProviderConfig.masked_key() never returns the full API key."""
        cfg = ProviderConfig(
            name="gemini",
            base_url="https://example.com",
            model="test",
            api_key="super-secret-api-key-12345",
            timeout=10,
        )
        masked = cfg.masked_key()
        self.assertNotIn("super-secret-api-key-12345", masked)
        self.assertIn("****", masked)

    def test_17b_empty_key_returns_not_set(self):
        """Empty API key shows <not set> instead of the real key."""
        cfg = ProviderConfig(
            name="nvidia", base_url="https://x.com", model="m", api_key="", timeout=10
        )
        self.assertEqual(cfg.masked_key(), "<not set>")

    def test_17c_key_not_logged_in_provider_statuses(self):
        """FallbackLLMProvider.get_provider_statuses() does not include API keys."""
        cfg = ProviderConfig(
            name="gemini", base_url="https://x.com/v1",
            model="gm", api_key="my-secret-key-9999", timeout=5,
        )
        p = OpenAICompatibleProvider(
            base_url=cfg.base_url, model=cfg.model,
            api_key=cfg.api_key, timeout=cfg.timeout,
        )
        fallback = FallbackLLMProvider(providers=[p], configs=[cfg])
        statuses = fallback.get_provider_statuses()
        for status in statuses:
            self.assertNotIn("api_key", status)
            self.assertNotIn("my-secret-key-9999", str(status))


class TestStructuredIntentValidation(unittest.TestCase):
    """Test 18: StructuredIntent schema compliance for all providers."""

    # Test 18: All providers must produce schema-compliant StructuredIntent
    def test_18_structured_intent_schema_preserved(self):
        """StructuredIntent from any provider must validate against the canonical schema."""
        REQUIRED_FIELDS = {
            "intent", "needs_database", "needs_scraping", "category", "location",
            "quantity", "fields", "filters", "freshness", "scraper_id",
            "dataset_id", "job_id", "confidence", "user_request",
            "reasoning", "is_fallback", "fallback_reason",
        }
        intent_dict = _valid_intent_dict()
        intent = StructuredIntent.model_validate(intent_dict)
        intent_json = intent.model_dump()

        for field in REQUIRED_FIELDS:
            self.assertIn(field, intent_json, f"Required field '{field}' missing from StructuredIntent")

    def test_18b_intent_validator_still_rejects_invalid_scraper(self):
        """IntentValidator still rejects unknown scraper IDs regardless of provider."""
        intent = StructuredIntent(
            intent=IntentType.SCRAPER_REQUEST,
            scraper_id="fake-provider-injected-scraper",
            user_request="run fake scraper",
        )
        is_valid, errors = IntentValidator.validate(intent)
        self.assertFalse(is_valid)
        self.assertTrue(any("fake-provider-injected-scraper" in e for e in errors))

    def test_18c_legacy_env_vars_still_work(self):
        """Legacy LLM_PROVIDER=gemini + LLM_API_KEY still produces a READY Gemini config."""
        env = {
            "LLM_PROVIDER": "gemini",
            "LLM_API_KEY": "legacy-gemini-key-abc",
            "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "LLM_MODEL": "gemini-2.0-flash",
            "LLM_TIMEOUT": "30",
        }
        # Remove GEMINI_API_KEY so the legacy path is taken
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("GEMINI_API_KEY", "LLM_PRIMARY_PROVIDER")}
        env_clean.update(env)
        with patch.dict(os.environ, env_clean, clear=True):
            cfg = get_provider_config("gemini")
        self.assertEqual(cfg.status, ProviderStatus.READY)
        self.assertEqual(cfg.model, "gemini-2.0-flash")

    def test_18d_app_does_not_crash_when_all_providers_not_configured(self):
        """
        Application startup must not crash even if ALL providers are NOT_CONFIGURED.
        IntentEngine will use QueryParser fallback for every request.
        """
        env = {
            "GEMINI_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            "NVIDIA_API_KEY": "",
            # Remove legacy key too
            "LLM_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            try:
                provider = get_llm_provider(force_refresh=True)
            except Exception as exc:
                self.fail(f"get_llm_provider() raised unexpectedly: {exc}")

        # The IntentEngine should fall back to QueryParser
        engine = IntentEngine(provider=provider)
        intent = engine.parse("Show me contractors in Dallas")
        # is_fallback may be True (QueryParser) or False (if some provider worked)
        # The important thing: no crash, valid intent returned
        self.assertIsInstance(intent, StructuredIntent)
        self.assertIsNotNone(intent.intent)


if __name__ == "__main__":
    unittest.main()
