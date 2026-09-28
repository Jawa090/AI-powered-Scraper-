"""
tests/test_phase_2e.py
───────────────────────
Verification test suite for Phase 2E: Chatbot End-to-End.
Tests all 10 required end-to-end scenarios from Master Prompt Phase 2E.4,
and verifies API contracts and truthful state reporting.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.orchestrator import AgentOrchestrator, agent_orchestrator
from agents.intent.models import IntentType


class TestPhase2E(unittest.TestCase):
    """Tests for Phase 2E: Chatbot End-to-End scenarios."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.session_id = f"sess-test-e2e-{os.urandom(4).hex()}"

    # Scenario 1: "Show me leads from the database"
    def test_01_scenario_leads_from_database(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me leads from the database",
        )
        self.assertIn("reply", res)
        self.assertEqual(res["agentCode"], "database")
        self.assertEqual(res["handledBy"], "DatabaseAgent")
        self.assertIn("PostgreSQL", res["reply"])
        self.assertEqual(res["workflowStatus"], "COMPLETED")

    # Scenario 2: "Find contractors in Dallas"
    def test_02_scenario_find_contractors_in_dallas(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Find contractors in Dallas",
        )
        self.assertIn("reply", res)
        self.assertIn(res["decision"], ["USE_DATABASE", "NEED_FETCH", "NEED_CLARIFICATION"])
        self.assertTrue("Dallas" in res["reply"] or "Contractor" in res["reply"] or "contractor" in res["reply"])

    # Scenario 3: "Scrape 50 contractors in Dallas"
    @patch("scraper_manager.scraper_manager.create_job")
    def test_03_scenario_scrape_contractors_in_dallas(self, mock_create):
        mock_create.return_value = "job-bonfire-12345"
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Scrape 50 contractors in Dallas (Bonfire)",
        )
        self.assertIn("reply", res)
        self.assertIn("RUNNING", res["reply"])
        self.assertEqual(res["recommendedScript"], "bonfire")
        self.assertEqual(res["jobId"], "job-bonfire-12345")

    # Scenario 4: "Find contractors in Dallas and compare with existing leads"
    def test_04_scenario_combined_request(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Find contractors in Dallas and compare with existing leads through NYSCR",
        )
        # NYSCR without creds will be BLOCKED, giving PARTIAL status honestly
        self.assertIn("reply", res)
        self.assertIn("PARTIAL", res["decision"])
        self.assertEqual(res["workflowStatus"], "PARTIAL")
        self.assertIn("database", res["agentsInvolved"])
        self.assertIn("scraper", res["agentsInvolved"])

    # Scenario 5: "Show me job status"
    def test_05_scenario_show_job_status(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me the status of job job-2024-test",
        )
        self.assertIn("reply", res)
        # Should not crash and should report status truthfully
        self.assertIn("Job", res["reply"])

    # Scenario 6: "Show me datasets"
    def test_06_scenario_show_datasets(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me datasets",
        )
        self.assertIn("reply", res)
        self.assertEqual(res["agentCode"], "database")
        self.assertIn("dataset", res["reply"].lower())

    # Scenario 7: Unsupported request
    def test_07_scenario_unsupported_request(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Please order me a pepperoni pizza with extra cheese",
        )
        self.assertIn("reply", res)
        self.assertIn("decision", res)

    # Scenario 8: Scraper blocked (NYSCR without credentials)
    def test_08_scenario_scraper_blocked_nyscr(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NYSCR_USERNAME", None)
            os.environ.pop("NYSCR_PASSWORD", None)
            res = self.orchestrator.handle_message(
                session_id=self.session_id,
                message="Run scraper NYSCR",
            )
            self.assertIn("reply", res)
            self.assertEqual(res["decision"], "BLOCKED")
            self.assertIn("BLOCKED", res["reply"])
            self.assertIn("NYSCR credentials are not configured", res["reply"])

    # Scenario 9: Database unavailable
    @patch("agents.orchestrator.SessionLocal")
    def test_09_scenario_database_unavailable(self, mock_session):
        mock_session.side_effect = ConnectionError("PostgreSQL connection refused")
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me leads from the database",
        )
        self.assertIn("reply", res)
        self.assertIn("error", res["reply"].lower())

    # Scenario 10: LLM unavailable (uses controlled fallback seamlessly)
    @patch("agents.intent.engine.get_llm_provider")
    def test_10_scenario_llm_unavailable_fallback(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.generate_structured.side_effect = ConnectionError("LLM server offline")
        mock_get_provider.return_value = mock_provider

        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me leads from the database",
        )
        self.assertIn("reply", res)
        self.assertEqual(res["agentCode"], "database")
        self.assertTrue(res["intent"].get("is_fallback"))

    # Contract Verification: All expected fields present
    def test_11_response_contract_fields(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Hello, how can you help me?",
        )
        expected_fields = [
            "reply", "suggestions", "updatedRequirement", "recommendedScript",
            "sessionId", "decision", "agentCode", "handledBy", "jobId",
            "proposedActions", "collaborationId", "agentsInvolved", "agentSteps"
        ]
        for field in expected_fields:
            self.assertIn(field, res, f"Field '{field}' missing from response contract")


if __name__ == "__main__":
    unittest.main()
