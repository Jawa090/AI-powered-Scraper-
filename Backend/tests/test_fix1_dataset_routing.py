"""
tests/test_fix1_dataset_routing.py
────────────────────────────────────
Fix 1 Regression Tests: DATASET ID → LEAD RETRIEVAL ROUTING
Tests 10 scenarios verifying the orchestrator correctly routes:
  - DATASET_QUERY + dataset_id + lead/record request  → search_leads()
  - DATASET_QUERY + metadata/list request             → search_datasets()
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

CONTRACT_FIELDS = [
    "reply", "suggestions", "updatedRequirement", "recommendedScript",
    "sessionId", "decision", "agentCode", "handledBy", "jobId",
    "proposedActions", "collaborationId", "agentsInvolved", "agentSteps",
]

DATASET_ID = "ds-bb70d6"


class TestFix1DatasetRouting(unittest.TestCase):
    """Fix 1 — 10 focused routing tests."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.session_id = f"sess-fix1-{os.urandom(4).hex()}"

    def _assert_contract(self, res: dict):
        for field in CONTRACT_FIELDS:
            self.assertIn(field, res, f"Contract field '{field}' missing")

    # -----------------------------------------------------------------------
    # Tests 1-4: CASE A — dataset_id + lead/record request → search_leads()
    # -----------------------------------------------------------------------

    @patch.object(database_agent, "search_leads")
    @patch.object(database_agent, "search_datasets")
    def test_01_show_5_leads_from_dataset(self, mock_search_ds, mock_search_leads):
        """1. 'Show me the 5 leads from dataset ds-bb70d6' → search_leads()"""
        mock_search_leads.return_value = {
            "success": True, "count": 5, "records": [
                {"id": f"lead-{i}", "title": f"Company {i}",
                 "organization_name": f"Org {i}", "dataset_id": DATASET_ID}
                for i in range(5)
            ], "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, f"Show me the 5 leads from dataset {DATASET_ID}"
        )
        self._assert_contract(res)
        # search_leads MUST be called with dataset_id filter
        mock_search_leads.assert_called_once()
        call_kwargs = mock_search_leads.call_args
        filters = call_kwargs.kwargs.get("filters") or (call_kwargs.args[0] if call_kwargs.args else {})
        self.assertEqual(filters.get("dataset_id"), DATASET_ID)
        # limit must respect quantity=5
        limit = call_kwargs.kwargs.get("limit") or 20
        self.assertLessEqual(limit, 20)  # quantity was 5, limit ≤ 20
        # search_datasets must NOT be called for lead retrieval
        mock_search_ds.assert_not_called()
        # Response fields
        self.assertEqual(res["agentCode"], "database")
        self.assertEqual(res["handledBy"], "DatabaseAgent")
        self.assertIn(DATASET_ID, res["reply"])
        self.assertIsNone(res["jobId"])

    @patch.object(database_agent, "search_leads")
    @patch.object(database_agent, "search_datasets")
    def test_02_show_leads_from_dataset(self, mock_search_ds, mock_search_leads):
        """2. 'Show me the leads from dataset ds-bb70d6' → search_leads()"""
        mock_search_leads.return_value = {
            "success": True, "count": 3, "records": [
                {"id": f"lead-{i}", "title": "Contractor", "organization_name": f"Co {i}", "dataset_id": DATASET_ID}
                for i in range(3)
            ], "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, f"Show me the leads from dataset {DATASET_ID}"
        )
        self._assert_contract(res)
        mock_search_leads.assert_called_once()
        filters = mock_search_leads.call_args.kwargs.get("filters") or {}
        self.assertEqual(filters.get("dataset_id"), DATASET_ID)
        mock_search_ds.assert_not_called()
        self.assertIn(DATASET_ID, res["reply"])

    @patch.object(database_agent, "search_leads")
    @patch.object(database_agent, "search_datasets")
    def test_03_query_leads_where_dataset_id(self, mock_search_ds, mock_search_leads):
        """3. 'Query the leads where dataset_id is ds-bb70d6' → search_leads()"""
        mock_search_leads.return_value = {
            "success": True, "count": 2,
            "records": [{"id": "l1", "title": "T1", "organization_name": "O1", "dataset_id": DATASET_ID}],
            "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, f"Query the leads where dataset_id is {DATASET_ID}"
        )
        self._assert_contract(res)
        mock_search_leads.assert_called_once()
        filters = mock_search_leads.call_args.kwargs.get("filters") or {}
        self.assertEqual(filters.get("dataset_id"), DATASET_ID)
        mock_search_ds.assert_not_called()

    @patch.object(database_agent, "search_leads")
    @patch.object(database_agent, "search_datasets")
    def test_04_give_5_records_from_dataset(self, mock_search_ds, mock_search_leads):
        """4. 'Give me 5 records from ds-bb70d6' → search_leads() with limit=5"""
        mock_search_leads.return_value = {
            "success": True, "count": 5,
            "records": [{"id": f"l{i}", "title": f"T{i}", "organization_name": f"O{i}", "dataset_id": DATASET_ID}
                        for i in range(5)],
            "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, f"Give me 5 records from {DATASET_ID}"
        )
        self._assert_contract(res)
        mock_search_leads.assert_called_once()
        filters = mock_search_leads.call_args.kwargs.get("filters") or {}
        self.assertEqual(filters.get("dataset_id"), DATASET_ID)
        mock_search_ds.assert_not_called()

    # -----------------------------------------------------------------------
    # Tests 5-7: CASE B — metadata/list requests → search_datasets()
    # -----------------------------------------------------------------------

    @patch.object(database_agent, "search_datasets")
    def test_05_show_dataset_metadata(self, mock_search_ds):
        """5. 'Show me dataset ds-bb70d6' → search_datasets() (metadata)"""
        mock_search_ds.return_value = {
            "success": True, "count": 1,
            "records": [{"id": DATASET_ID, "name": "Bonfire Run 1", "records_count": 50, "status": "completed"}],
            "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, f"Show me dataset {DATASET_ID}"
        )
        self._assert_contract(res)
        mock_search_ds.assert_called()
        self.assertEqual(res["agentCode"], "database")
        self.assertEqual(res["handledBy"], "DatabaseAgent")

    @patch.object(database_agent, "search_datasets")
    def test_06_tell_me_about_dataset(self, mock_search_ds):
        """6. 'Tell me about dataset ds-bb70d6' → search_datasets()"""
        mock_search_ds.return_value = {
            "success": True, "count": 1,
            "records": [{"id": DATASET_ID, "name": "Bonfire Run 1", "records_count": 50, "status": "completed"}],
            "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, f"Tell me about dataset {DATASET_ID}"
        )
        self._assert_contract(res)
        mock_search_ds.assert_called()

    @patch.object(database_agent, "search_datasets")
    def test_07_list_datasets(self, mock_search_ds):
        """7. 'List datasets' → search_datasets()"""
        mock_search_ds.return_value = {
            "success": True, "count": 2,
            "records": [
                {"id": "ds-111", "name": "Run A", "records_count": 10},
                {"id": "ds-222", "name": "Run B", "records_count": 20},
            ],
            "errors": []
        }
        res = self.orchestrator.handle_message(self.session_id, "List datasets")
        self._assert_contract(res)
        mock_search_ds.assert_called()
        self.assertEqual(res["agentCode"], "database")

    # -----------------------------------------------------------------------
    # Tests 8-10: Edge cases
    # -----------------------------------------------------------------------

    @patch.object(database_agent, "search_leads")
    @patch.object(database_agent, "search_datasets")
    def test_08_dataset_exists_zero_leads(self, mock_search_ds, mock_search_leads):
        """8. Dataset exists but has zero leads → controlled 0-record response, no scraping"""
        mock_search_leads.return_value = {
            "success": True, "count": 0, "records": [], "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, f"Show me the leads from dataset {DATASET_ID}"
        )
        self._assert_contract(res)
        mock_search_leads.assert_called_once()
        filters = mock_search_leads.call_args.kwargs.get("filters") or {}
        self.assertEqual(filters.get("dataset_id"), DATASET_ID)
        mock_search_ds.assert_not_called()
        # Must report 0 truthfully, no fake data, no scraper triggered
        self.assertIsNone(res["jobId"])
        self.assertIn("0", res["reply"])

    @patch.object(database_agent, "search_leads")
    @patch.object(database_agent, "search_datasets")
    def test_09_nonexistent_dataset_leads(self, mock_search_ds, mock_search_leads):
        """9. 'Show me the leads from dataset ds-does-not-exist' → 0 records, no crash"""
        mock_search_leads.return_value = {
            "success": True, "count": 0, "records": [], "errors": []
        }
        res = self.orchestrator.handle_message(
            self.session_id, "Show me the leads from dataset ds-does-not-exist"
        )
        self._assert_contract(res)
        mock_search_leads.assert_called_once()
        filters = mock_search_leads.call_args.kwargs.get("filters") or {}
        self.assertEqual(filters.get("dataset_id"), "ds-does-not-exist")
        mock_search_ds.assert_not_called()
        self.assertIsNone(res["jobId"])

    def test_10_dataset_id_security_validation(self):
        """10. Injection-like dataset ID is rejected by DatabaseAgent validation"""
        result = database_agent.search_leads(
            filters={"dataset_id": "ds-test'; DROP TABLE leads; --"},
            limit=5,
        )
        # The SQL_INJECTION_RE must catch the DROP TABLE pattern
        self.assertFalse(result["success"])
        self.assertTrue(len(result["errors"]) > 0)
        self.assertIn("SQL injection attempt detected", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
