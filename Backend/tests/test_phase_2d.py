"""
tests/test_phase_2d.py
───────────────────────
Verification test suite for Phase 2D: Dedicated ScraperAgent.
Tests registry integration, canonical create_job(), parameter validation,
credential preflight, job statuses, honest failure reporting, and synthetic data prohibition.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from execution.registry import SCRIPTS_REGISTRY, get_registered_script
from agents.specialized.scraper_agent import ScraperAgent, scraper_agent
from agents.base import AgentContext, AgentStatus


class TestPhase2D(unittest.TestCase):
    """Tests for Phase 2D: Scraper Agent."""

    def setUp(self):
        self.agent = ScraperAgent()

    # 1. Registry lookup: authoritative 4 scrapers present
    def test_01_registry_lookup(self):
        self.assertEqual(len(SCRIPTS_REGISTRY), 4)
        for sid in ["bonfire", "dasny", "jwiz", "nyscr"]:
            script = get_registered_script(sid)
            self.assertIsNotNone(script)
            self.assertEqual(script["id"], sid)

    # 2. Invalid scraper rejected
    def test_02_invalid_scraper_rejected(self):
        is_valid, err = self.agent.validate_scraper_request("nonexistent_script_xyz")
        self.assertFalse(is_valid)
        self.assertIn("Unknown script_id", err)

    # 3. Valid scraper accepted
    def test_03_valid_scraper_accepted(self):
        is_valid, err = self.agent.validate_scraper_request("bonfire", {"limit": 20})
        self.assertTrue(is_valid)
        self.assertEqual(err, "")

    # 4. Parameter validation: limit bounds
    def test_04_parameter_validation_limit_bounds(self):
        is_valid, err = self.agent.validate_scraper_request("jwiz", {"limit": -5})
        self.assertFalse(is_valid)
        self.assertIn("between 1 and 50000", err)

        is_valid2, err2 = self.agent.validate_scraper_request("jwiz", {"limit": 99999})
        self.assertFalse(is_valid2)
        self.assertIn("between 1 and 50000", err2)

    # 5. Credential preflight: NYSCR blocks without credentials
    def test_05_credential_preflight_nyscr(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NYSCR_USERNAME", None)
            os.environ.pop("NYSCR_PASSWORD", None)
            has_creds, err = self.agent.check_credentials_preflight("nyscr")
            self.assertFalse(has_creds)
            self.assertIn("NYSCR credentials are not configured", err)

    # 6. Credential preflight: Bonfire/DASNY/JWiz do not require credentials
    def test_06_credential_preflight_others(self):
        for sid in ["bonfire", "dasny", "jwiz"]:
            has_creds, err = self.agent.check_credentials_preflight(sid)
            self.assertTrue(has_creds)
            self.assertIsNone(err)

    # 7. Job creation blocked if credentials absent
    def test_07_job_creation_blocked_without_creds(self):
        with patch.dict(os.environ, {}, clear=True):
            res = self.agent.create_job("nyscr", {"limit": 10})
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "BLOCKED")
            self.assertTrue(any("credentials" in e.lower() for e in res["errors"]))

    # 8. Canonical create_job() path used
    @patch("scraper_manager.scraper_manager.create_job")
    def test_08_canonical_create_job_path(self, mock_create):
        mock_create.return_value = "job-mock-test-123"
        res = self.agent.create_job("bonfire", {"limit": 25, "location": "dallas"})
        self.assertTrue(res["success"])
        self.assertEqual(res["job_id"], "job-mock-test-123")
        mock_create.assert_called_once()

    # 9. Scraper selection logic
    def test_09_scraper_selection(self):
        self.assertEqual(self.agent.select_scraper(location="Dallas"), "bonfire")
        self.assertEqual(self.agent.select_scraper(category="DASNY construction"), "dasny")
        self.assertEqual(self.agent.select_scraper(category="Contractor", location="New York"), "jwiz")
        self.assertEqual(self.agent.select_scraper(preference="bonfire"), "bonfire")

    # 10. Honest failure handling
    @patch("scraper_manager.scraper_manager.create_job")
    def test_10_honest_failure_handling(self, mock_create):
        mock_create.side_effect = RuntimeError("Failed to connect to execution dispatcher")
        res = self.agent.create_job("bonfire", {"limit": 10})
        self.assertFalse(res["success"])
        self.assertIn("Failed to connect", res["errors"][0])

    # 11. ScraperAgent handle() blocks NYSCR cleanly
    def test_11_handle_blocks_nyscr_without_creds(self):
        with patch.dict(os.environ, {}, clear=True):
            ctx = AgentContext(
                session_id="sess-nyscr-block",
                normalized_query={"source_preference": "nyscr", "category": "State Contracts"},
                raw_message="Extract state contracts from nyscr",
            )
            result = self.agent.handle(ctx)
            self.assertEqual(result.status, AgentStatus.ERROR)
            self.assertEqual(result.metadata.get("status"), "BLOCKED")
            self.assertIn("BLOCKED", result.message)

    # 12. No synthetic data: dispatcher check
    def test_12_no_synthetic_data(self):
        import inspect
        import execution.dispatcher as disp_mod
        src = inspect.getsource(disp_mod)
        self.assertNotIn("555-0100", src)
        self.assertNotIn("rfp-bids@dasny.org", src)
        self.assertNotIn("procurement@nyscr.ny.gov", src)


if __name__ == "__main__":
    unittest.main()
