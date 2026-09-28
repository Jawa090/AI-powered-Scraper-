"""
tests/test_phase_2a.py
───────────────────────
Verification test suite for Phase 2A: Open-Source LLM Provider + Structured Intent.
Covers all 17 required scenarios from Master Prompt Phase 2A.5.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure Backend directory is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.intent.models import IntentType, StructuredIntent
from agents.intent.validator import IntentValidator
from agents.intent.engine import IntentEngine
from agents.llm.provider import LLMProvider
from agents.llm.openai_compatible import OpenAICompatibleProvider
from agents.llm.factory import get_llm_provider
from pydantic import ValidationError


class MockSuccessLLMProvider(LLMProvider):
    """Mock provider simulating successful structured responses."""

    def __init__(self, mock_intent_dict=None):
        self.mock_intent_dict = mock_intent_dict or {
            "intent": "lead_discovery",
            "needs_database": True,
            "needs_scraping": False,
            "category": "Contractor",
            "location": "Dallas",
            "quantity": 25,
            "fields": ["email", "phone"],
            "filters": {"category": "Contractor"},
            "freshness": False,
            "scraper_id": "bonfire",
            "confidence": 0.95,
            "user_request": "Find 25 contractors in Dallas",
            "reasoning": "Standard contractor discovery request",
        }

    def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=2048):
        return '{"result": "mock text"}'

    def generate_structured(self, prompt, schema, system_prompt=None, temperature=0.0):
        return schema.model_validate(self.mock_intent_dict)

    def health_check(self):
        return {"available": True, "provider": "mock", "model": "mock-llama3"}


class MockTimeoutLLMProvider(LLMProvider):
    def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=2048):
        raise TimeoutError("LLM request timed out after 30 seconds")

    def generate_structured(self, prompt, schema, system_prompt=None, temperature=0.0):
        raise TimeoutError("LLM request timed out after 30 seconds")

    def health_check(self):
        return {"available": False, "details": "Timeout"}


class MockUnavailableLLMProvider(LLMProvider):
    def generate(self, prompt, system_prompt=None, temperature=0.1, max_tokens=2048):
        raise ConnectionError("Failed to connect to LLM endpoint: connection refused")

    def generate_structured(self, prompt, schema, system_prompt=None, temperature=0.0):
        raise ConnectionError("Failed to connect to LLM endpoint: connection refused")

    def health_check(self):
        return {"available": False, "details": "Connection refused"}


class TestPhase2A(unittest.TestCase):
    """Tests for Phase 2A: Open-Source LLM Provider + Structured Intent."""

    # 1. Provider initialization
    def test_01_provider_initialization(self):
        provider = OpenAICompatibleProvider(
            base_url="http://localhost:11434/v1",
            model="llama3",
            timeout=15,
        )
        self.assertEqual(provider.base_url, "http://localhost:11434/v1")
        self.assertEqual(provider.model, "llama3")
        self.assertEqual(provider.timeout, 15)

    # 2. Missing configuration defaults
    def test_02_missing_configuration_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = OpenAICompatibleProvider()
            self.assertEqual(provider.base_url, "http://localhost:11434/v1")
            self.assertEqual(provider.model, "llama3")
            self.assertEqual(provider.timeout, 30)

    # 3. Successful LLM response
    def test_03_successful_llm_response(self):
        provider = MockSuccessLLMProvider()
        res = provider.generate("Hello")
        self.assertIn("mock text", res)

    # 4. Structured intent parsing
    def test_04_structured_intent_parsing(self):
        provider = MockSuccessLLMProvider()
        engine = IntentEngine(provider=provider)
        intent = engine.parse("Find 25 contractors in Dallas")
        self.assertEqual(intent.intent, IntentType.LEAD_DISCOVERY)
        self.assertEqual(intent.category, "Contractor")
        self.assertEqual(intent.location, "Dallas")
        self.assertEqual(intent.quantity, 25)
        self.assertFalse(intent.is_fallback)

    # 5. Malformed JSON handling
    def test_05_malformed_json_handling(self):
        provider = OpenAICompatibleProvider()
        with self.assertRaises(ValueError):
            provider._extract_json("not valid json at all {bad-json")

    # 6. Invalid intent
    def test_06_invalid_intent_rejected(self):
        with self.assertRaises(ValidationError):
            StructuredIntent(
                intent="invalid_intent_type",  # type: ignore
                user_request="test",
            )

    # 7. Invalid scraper ID
    def test_07_invalid_scraper_id_rejected(self):
        intent = StructuredIntent(
            intent=IntentType.SCRAPER_REQUEST,
            scraper_id="nonexistent_scraper",
            user_request="run unknown scraper",
        )
        is_valid, errors = IntentValidator.validate(intent)
        self.assertFalse(is_valid)
        self.assertTrue(any("nonexistent_scraper" in e for e in errors))

    # 8. Invalid quantity bounds
    def test_08_invalid_quantity_bounds(self):
        with self.assertRaises(ValidationError):
            StructuredIntent(
                intent=IntentType.LEAD_DISCOVERY,
                quantity=0,
                user_request="0 leads",
            )
        with self.assertRaises(ValidationError):
            StructuredIntent(
                intent=IntentType.LEAD_DISCOVERY,
                quantity=60000,
                user_request="60000 leads",
            )

    # 9. Invalid filter
    def test_09_invalid_filter_rejected(self):
        intent = StructuredIntent(
            intent=IntentType.DATABASE_SEARCH,
            filters={"disallowed_secret_column": "value"},
            user_request="search with invalid column",
        )
        is_valid, errors = IntentValidator.validate(intent)
        self.assertFalse(is_valid)
        self.assertTrue(any("disallowed_secret_column" in e for e in errors))

    # 10. LLM timeout triggers controlled fallback
    def test_10_llm_timeout(self):
        engine = IntentEngine(provider=MockTimeoutLLMProvider())
        intent = engine.parse("Find contractors in Dallas")
        self.assertTrue(intent.is_fallback)
        self.assertIn("timed out", intent.fallback_reason.lower())
        self.assertEqual(intent.location, "Dallas")

    # 11. Provider unavailable triggers controlled fallback
    def test_11_provider_unavailable(self):
        engine = IntentEngine(provider=MockUnavailableLLMProvider())
        intent = engine.parse("Show me leads from the database")
        self.assertTrue(intent.is_fallback)
        self.assertIn("unavailable", intent.fallback_reason.lower())
        self.assertEqual(intent.intent, IntentType.DATABASE_SEARCH)

    # 12. Fallback parser explicitly tracked
    def test_12_fallback_parser_tracked(self):
        engine = IntentEngine(provider=MockUnavailableLLMProvider())
        intent = engine.parse("Extract leads from jwiz")
        self.assertTrue(intent.is_fallback)
        self.assertIsNotNone(intent.fallback_reason)
        self.assertNotEqual(intent.reasoning, "")

    # 13. Empty user request
    def test_13_empty_user_request(self):
        engine = IntentEngine(provider=MockSuccessLLMProvider())
        intent = engine.parse("")
        self.assertEqual(intent.intent, IntentType.GENERAL_INFORMATION)
        self.assertFalse(intent.needs_database)
        self.assertFalse(intent.needs_scraping)

    # 14. General information intent
    def test_14_general_information(self):
        engine = IntentEngine(provider=MockUnavailableLLMProvider())
        intent = engine.parse("Hello, what can you do?")
        self.assertEqual(intent.intent, IntentType.GENERAL_INFORMATION)
        self.assertFalse(intent.needs_database)
        self.assertFalse(intent.needs_scraping)

    # 15. Database search intent
    def test_15_database_search(self):
        engine = IntentEngine(provider=MockUnavailableLLMProvider())
        intent = engine.parse("Show me contractors from our database")
        self.assertEqual(intent.intent, IntentType.DATABASE_SEARCH)
        self.assertTrue(intent.needs_database)
        self.assertFalse(intent.needs_scraping)

    # 16. Scraper request intent
    def test_16_scraper_request(self):
        engine = IntentEngine(provider=MockUnavailableLLMProvider())
        intent = engine.parse("Scrape 50 contractors in Dallas")
        self.assertEqual(intent.intent, IntentType.SCRAPER_REQUEST)
        self.assertTrue(intent.needs_scraping)
        self.assertEqual(intent.quantity, 50)
        self.assertEqual(intent.location, "Dallas")

    # 17. Combined database + scraper request
    def test_17_combined_database_scraper_request(self):
        engine = IntentEngine(provider=MockUnavailableLLMProvider())
        intent = engine.parse("Find contractors in Dallas and compare with existing leads")
        self.assertTrue(intent.needs_database)
        self.assertTrue(intent.needs_scraping)


if __name__ == "__main__":
    unittest.main()
