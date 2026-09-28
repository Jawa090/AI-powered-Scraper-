"""
tests/test_phase_2c.py
───────────────────────
Verification test suite for Phase 2C: Database Agent.
Tests search, dataset queries, job queries, availability, filters, pagination,
SQL injection protection, invalid field rejection, and structured result contracts.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.specialized.database_agent import DatabaseAgent, database_agent
from agents.base import AgentContext


class TestPhase2C(unittest.TestCase):
    """Tests for Phase 2C: Database Agent."""

    def setUp(self):
        self.agent = DatabaseAgent()

    # 1. Lead search returns structured result contract
    def test_01_lead_search_contract(self):
        res = self.agent.search_leads(filters={"category": "contractor"}, limit=5)
        self.assertIn("success", res)
        self.assertIn("count", res)
        self.assertIn("records", res)
        self.assertEqual(res["source"], "postgresql")
        self.assertEqual(res["query_type"], "search_leads")
        self.assertTrue(isinstance(res["records"], list))

    # 2. Dataset search returns structured contract
    def test_02_dataset_search_contract(self):
        res = self.agent.search_datasets(limit=5)
        self.assertTrue(res["success"])
        self.assertIn("records", res)
        self.assertEqual(res["source"], "postgresql")
        self.assertEqual(res["query_type"], "search_datasets")

    # 3. Job lookup - existing or 404 handled gracefully
    def test_03_job_lookup(self):
        res = self.agent.get_job("job-nonexistent-12345")
        self.assertFalse(res["success"])
        self.assertIn("not found", res["errors"][0].lower())

    # 4. Job listing returns list
    def test_04_job_listing(self):
        res = self.agent.list_jobs(limit=5)
        self.assertTrue(res["success"])
        self.assertEqual(res["query_type"], "list_jobs")
        self.assertTrue(isinstance(res["records"], list))

    # 5. Count matching leads
    def test_05_count_matching_leads(self):
        res = self.agent.count_matching_leads(filters={"category": "contractor"})
        self.assertTrue(res["success"])
        self.assertIsInstance(res["count"], int)
        self.assertGreaterEqual(res["count"], 0)

    # 6. Data availability check
    def test_06_check_data_availability(self):
        res = self.agent.check_data_availability(
            category="contractor",
            location="Dallas",
            quantity=10,
        )
        self.assertTrue(res["success"])
        self.assertIn("is_sufficient", res)
        self.assertIn("requested_quantity", res)
        self.assertEqual(res["requested_quantity"], 10)

    # 7. Filters work without errors
    def test_07_filters_execution(self):
        res = self.agent.search_leads(
            filters={"category": "electrical", "location": "New York"},
            limit=5,
        )
        self.assertTrue(res["success"])

    # 8. Pagination bounds respected
    def test_08_pagination_bounds(self):
        res = self.agent.search_leads(limit=5000, offset=0)
        self.assertTrue(res["success"])
        # Should cap at 1000 without crashing
        self.assertLessEqual(len(res["records"]), 1000)

    # 9. Invalid field rejected by policy
    def test_09_invalid_field_rejected(self):
        res = self.agent.search_leads(
            filters={"disallowed_secret_password_column": "secret"}
        )
        self.assertFalse(res["success"])
        self.assertTrue(any("not in allowed fields" in e for e in res["errors"]))

    # 10. SQL injection attempt blocked
    def test_10_sql_injection_attempt_blocked(self):
        malicious_input = "contractor' UNION SELECT id, password, username, email FROM users --"
        res = self.agent.search_leads(
            filters={"category": malicious_input}
        )
        self.assertFalse(res["success"])
        self.assertTrue(any("SQL injection attempt detected" in e for e in res["errors"]))

    # 11. Empty result handled truthfully
    def test_11_empty_result_truthful(self):
        res = self.agent.search_leads(
            filters={"category": "xyznonexistentindustrynevermatches123456789"}
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 0)
        self.assertEqual(len(res["records"]), 0)

    # 12. Database unavailable handled gracefully
    @patch("agents.specialized.database_agent.SessionLocal")
    def test_12_database_unavailable_handled(self, mock_session):
        mock_session.side_effect = ConnectionError("PostgreSQL connection refused")
        res = self.agent.search_leads(limit=5)
        self.assertFalse(res["success"])
        self.assertTrue(any("connection refused" in e.lower() for e in res["errors"]))

    # 13. Agent handle() interface works
    def test_13_agent_handle_interface(self):
        ctx = AgentContext(
            session_id="sess-test",
            normalized_query={"category": "contractor", "location": "Dallas", "quantity": 5},
            raw_message="Show me contractors in Dallas",
        )
        result = self.agent.handle(ctx)
        self.assertIn(result.status.value, ["success", "data_returned"])
        self.assertEqual(result.agent_code, "database")


if __name__ == "__main__":
    unittest.main()
