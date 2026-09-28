"""
tests/test_natural_lead_retrieval.py
────────────────────────────────────
Regression tests verifying natural conversational lead retrieval:
  A. User requests 5 contractor leads in Dallas.
  B. Scraper produces 5 verified records.
  C. User then says 'Show me the leads'.
  D. System retrieves those 5 records.
  E. No second scraper job is created.
  F. Internal job/dataset IDs remain backend-only.
  G. The original quantity/location/requirement remains associated with the conversation.
  H. Category normalization does not mutate contractor into an increasingly incorrect category.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.orchestrator import AgentOrchestrator
from agents.specialized.database_agent import database_agent
from agents.query.parser import QueryParser

CONTRACT_FIELDS = [
    "reply", "suggestions", "updatedRequirement", "recommendedScript",
    "sessionId", "decision", "agentCode", "handledBy", "jobId",
    "proposedActions", "collaborationId", "agentsInvolved", "agentSteps",
]


class TestNaturalLeadRetrieval(unittest.TestCase):
    """E2E two-turn natural conversation tests."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.session_id = f"sess-nat-{os.urandom(4).hex()}"
        self.dataset_id = "ds-5219a2"
        self.job_id = "job-1790592336-9369"

    def _assert_contract(self, res: dict):
        for field in CONTRACT_FIELDS:
            self.assertIn(field, res, f"Contract field '{field}' missing")

    # Scenario H: Category normalization does not mutate "contractor"
    def test_category_normalization_does_not_mutate(self):
        """H. 'contractor' does NOT mutate into 'Commercial Contractor' or 'Residential Commercial Contractor'."""
        # Turn 1: user requests contractor
        q1 = QueryParser.parse("I need 5 contractor leads in Dallas.")
        self.assertEqual(q1.category, "Contractor")
        self.assertIsNone(q1.company_type)

        # Context generated after turn 1
        ctx = {
            "industry": q1.category,
            "location": q1.location,
            "quantity": q1.quantity,
            "companyType": "Not specified",
            "datasetId": self.dataset_id,
        }

        # Turn 2: user says "Show me the leads" with context
        q2 = QueryParser.parse("Show me the leads", context_requirement=ctx)
        self.assertEqual(q2.category, "Contractor")
        self.assertNotIn("Residential", q2.category)
        self.assertNotIn("Commercial", q2.category)

    # Scenarios A through G: Complete Two-Turn Lifecycle
    @patch.object(database_agent, "search_leads")
    def test_full_two_turn_show_me_the_leads(self, mock_search_leads):
        """
        A. User requests 5 contractor leads in Dallas.
        B. Scraper produces 5 verified records.
        C. User then says 'Show me the leads'.
        D. System retrieves those 5 records.
        E. No second scraper job is created.
        F. Internal job/dataset IDs remain backend-only.
        G. The original quantity/location/requirement remains associated.
        """
        # Turn 1: Initial user request
        res1 = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="I need 5 contractor leads in Dallas.",
        )
        self._assert_contract(res1)
        self.assertEqual(res1["updatedRequirement"]["industry"], "Contractor")
        self.assertEqual(res1["updatedRequirement"]["location"], "Dallas")
        self.assertEqual(res1["updatedRequirement"]["quantity"], 5)

        # Turn 1 Confirmation & Scraper execution produces dataset_id and completed requirement
        current_req = dict(res1["updatedRequirement"])
        current_req["datasetId"] = self.dataset_id
        current_req["jobId"] = self.job_id
        current_req["status"] = "completed"
        current_req["completionPercentage"] = 100

        # Mock database_agent.search_leads returning the 5 verified records for that dataset
        mock_leads = [
            {"id": f"lead-{i}", "title": f"Procurement Opportunity {i}",
             "organization_name": "City of Dallas", "dataset_id": self.dataset_id}
            for i in range(5)
        ]
        mock_search_leads.return_value = {
            "success": True,
            "count": 5,
            "records": mock_leads,
            "errors": [],
        }

        # Turn 2: User says "Show me the leads"
        res2 = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me the leads",
            current_requirement=current_req,
        )
        self._assert_contract(res2)

        # D. System retrieves those 5 records
        mock_search_leads.assert_called_once()
        call_kwargs = mock_search_leads.call_args.kwargs
        self.assertEqual(call_kwargs.get("filters", {}).get("dataset_id"), self.dataset_id)
        self.assertEqual(res2["agentResult"]["data"]["count"], 5)
        self.assertEqual(len(res2["agentResult"]["data"]["leads"]), 5)

        # E. No second scraper job is created
        self.assertIsNone(res2["jobId"])
        self.assertEqual(res2["agentCode"], "database")
        self.assertEqual(res2["handledBy"], "DatabaseAgent")

        # F. Internal job/dataset IDs remain backend-only (not in user-facing reply text)
        self.assertNotIn(self.dataset_id, res2["reply"])
        self.assertNotIn(self.job_id, res2["reply"])
        # But present in structured backend data
        self.assertEqual(res2["agentResult"]["data"]["dataset_id"], self.dataset_id)

        # G. The original quantity/location/requirement remains associated
        self.assertEqual(res2["updatedRequirement"]["industry"], "Contractor")
        self.assertEqual(res2["updatedRequirement"]["location"], "Dallas")
        self.assertEqual(res2["updatedRequirement"]["quantity"], 5)
        self.assertIn("Contractor", res2["reply"])
        self.assertIn("Dallas", res2["reply"])

    @patch.object(database_agent, "search_leads")
    def test_natural_variations_retrieve_leads(self, mock_search_leads):
        """Natural variations like 'view leads', 'show records', 'get the leads' retrieve records."""
        mock_search_leads.return_value = {
            "success": True,
            "count": 5,
            "records": [{"id": f"lead-{i}", "organization_name": "Test Co"} for i in range(5)],
            "errors": [],
        }

        current_req = {
            "industry": "Contractor",
            "location": "Dallas",
            "quantity": 5,
            "datasetId": self.dataset_id,
            "status": "completed",
        }

        for phrase in ["view leads", "show records", "get the leads", "Show the leads"]:
            with self.subTest(phrase=phrase):
                mock_search_leads.reset_mock()
                res = self.orchestrator.handle_message(
                    session_id=self.session_id,
                    message=phrase,
                    current_requirement=current_req,
                )
                mock_search_leads.assert_called_once()
                self.assertIsNone(res["jobId"])
                self.assertEqual(res["agentCode"], "database")
                self.assertNotIn(self.dataset_id, res["reply"])
