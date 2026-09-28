"""
tests/test_phase_2g.py
───────────────────────
Verification test suite for Phase 2G: Production Validation & Hardening.
Tests configuration audits, LLM failure fallbacks, database failure resilience,
scraper honest failure states, security boundaries, SQL injection prevention,
input hardening, and the 10 Master E2E scenarios from Step 4.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.orchestrator import AgentOrchestrator
from agents.intent.engine import IntentEngine
from agents.intent.models import IntentType, StructuredIntent
from agents.workflow.models import WorkflowPlan, PlanStep, StepStatus, WorkflowStatus
from agents.workflow.planner import WorkflowPlanner
from agents.workflow.collaboration import workflow_collaboration_engine
from agents.specialized.database_agent import database_agent, DatabaseSecurityError
from agents.specialized.scraper_agent import scraper_agent
from services.config_validator import ConfigValidator, mask_secret, mask_database_url
from app import health_check, readiness_check, bot_chat, BotChatRequest


class TestPhase2G(unittest.TestCase):
    """Phase 2G Production Hardening & Validation Test Suite."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.session_id = f"sess-test-2g-{os.urandom(4).hex()}"

    # =======================================================================
    # 2G.1 Configuration Validation
    # =======================================================================

    def test_01_config_secret_masking(self):
        masked_pwd = mask_database_url("postgresql+psycopg://user:super_secret_pw@db.host.com:5432/production")
        self.assertNotIn("super_secret_pw", masked_pwd)
        self.assertIn("****", masked_pwd)

        masked_key = mask_secret("sk-1234567890abcdef")
        self.assertTrue(masked_key.startswith("sk"))
        self.assertIn("****", masked_key)
        self.assertNotIn("1234567890", masked_key)

    def test_02_scraper_credentials_audit(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NYSCR_USERNAME", None)
            os.environ.pop("NYSCR_PASSWORD", None)
            audit = ConfigValidator.audit_scraper_credentials()
            self.assertEqual(audit["bonfire"]["status"], "READY")
            self.assertEqual(audit["dasny"]["status"], "READY")
            self.assertEqual(audit["jwiz"]["status"], "READY")
            self.assertEqual(audit["nyscr"]["status"], "BLOCKED")
            self.assertIn("NYSCR_USERNAME", audit["nyscr"]["missing"])

    # =======================================================================
    # 2G.2 LLM Failure Handling & Fallback
    # =======================================================================

    @patch("agents.intent.engine.get_llm_provider")
    def test_03_llm_failure_controlled_fallback(self, mock_provider_factory):
        mock_provider = MagicMock()
        mock_provider.generate_structured.side_effect = TimeoutError("LLM Provider request timed out after 30s")
        mock_provider_factory.return_value = mock_provider

        intent_engine = IntentEngine()
        intent = intent_engine.parse("Find contractors in Dallas")

        self.assertTrue(intent.is_fallback)
        self.assertEqual(intent.location, "Dallas")
        self.assertEqual(intent.category, "Contractor")
        self.assertIn("QueryParser", intent.reasoning)
        self.assertIn("fallback", intent.reasoning.lower())

    # =======================================================================
    # 2G.3 Database Failure Handling
    # =======================================================================

    @patch("agents.orchestrator.SessionLocal")
    def test_04_database_failure_handling(self, mock_session):
        mock_session.side_effect = ConnectionError("PostgreSQL connection refused")
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me leads from the database",
        )
        self.assertIn("reply", res)
        self.assertEqual(res["workflowStatus"], "FAILED")
        self.assertIn("error", res["reply"].lower())
        # Confirm no fabricated data returned
        self.assertIsNone(res.get("agentResult"))

    # =======================================================================
    # 2G.4 Scraper Failure & Honest Statuses
    # =======================================================================

    def test_05_scraper_preflight_blocked_truthful(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NYSCR_USERNAME", None)
            os.environ.pop("NYSCR_PASSWORD", None)
            has_creds, err = scraper_agent.check_credentials_preflight("nyscr")
            self.assertFalse(has_creds)
            self.assertIn("NYSCR credentials are not configured", err)

            # Creating a job for nyscr must return BLOCKED status
            res = scraper_agent.create_job("nyscr", {"keyword": "test"})
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "BLOCKED")
            self.assertIsNone(res["job_id"])

    # =======================================================================
    # 2G.5 Security Audit: SQL Injection & Whitelist
    # =======================================================================

    def test_06_sql_injection_defense(self):
        # 1. Malicious SQL payload in filters
        res = database_agent.search_leads(filters={"title": "test' OR 1=1; DROP TABLE leads; --"})
        self.assertFalse(res["success"])
        self.assertIn("SQL injection attempt detected", res["errors"][0])

        # 2. Unauthorized field access attempt
        res_field = database_agent.search_leads(filters={"unauthorized_field": "test"})
        self.assertFalse(res_field["success"])
        self.assertIn("not in allowed fields", res_field["errors"][0])

    def test_07_unauthorized_agent_and_tool_defense(self):
        # Reject unknown agent in workflow
        plan = WorkflowPlan(
            plan_id="plan-sec-01",
            steps=[PlanStep(step_id="step_1", agent="arbitrary_agent_code", action="run_shell")],
        )
        valid, errors = WorkflowPlanner.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("unauthorized agent", errors[0])

        # Reject unknown scraper ID
        plan_scraper = WorkflowPlan(
            plan_id="plan-sec-02",
            steps=[PlanStep(step_id="step_1", agent="scraper", action="create_job", parameters={"scraper_id": "malicious_scraper"})],
        )
        valid_s, errors_s = WorkflowPlanner.validate_plan(plan_scraper)
        self.assertFalse(valid_s)
        self.assertIn("unknown scraper_id", errors_s[0])

    # =======================================================================
    # 2G.6 Input Boundary Hardening
    # =======================================================================

    def test_08_input_quantity_and_limit_hardening(self):
        # Quantity out of bounds for scraper
        valid, err = scraper_agent.validate_scraper_request("bonfire", {"limit": 999999})
        self.assertFalse(valid)
        self.assertIn("must be an integer between 1 and 50000", err)

        valid_neg, err_neg = scraper_agent.validate_scraper_request("bonfire", {"limit": -5})
        self.assertFalse(valid_neg)

        # Confirm and generate bounds quantity safely
        with patch("scraper_manager.scraper_manager.create_job", return_value="job-bounded-1"):
            req_data = {"quantity": 1000000, "industry": "contractor", "location": "dallas"}
            res = self.orchestrator.confirm_and_generate(self.session_id, req_data, preferred_script_id="bonfire")
            self.assertTrue(res["success"])

    # =======================================================================
    # 2G.7 Observability & API Endpoints
    # =======================================================================

    def test_09_fastapi_health_and_readiness_endpoints(self):
        # Liveness probe
        data = health_check()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["registeredScripts"], 4)

        # Readiness probe (DB connected)
        data_ready = readiness_check()
        self.assertEqual(data_ready["status"], "ready")
        self.assertEqual(data_ready["database"], "connected")

        # Chatbot endpoint integration via route handler
        chat_req = BotChatRequest(
            sessionId=self.session_id,
            message="Show me contractors in Dallas from the database.",
        )
        chat_res = bot_chat(chat_req)
        self.assertEqual(chat_res["agentCode"], "database")
        self.assertIn("reply", chat_res)

    # =======================================================================
    # 2G.8 Master Step 4 E2E Scenarios (1 through 10)
    # =======================================================================

    # TEST 1 — DATABASE QUERY
    def test_10_master_test_1_database_query(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me contractors in Dallas from the database.",
        )
        self.assertEqual(res["agentCode"], "database")
        self.assertIn("PostgreSQL", res["reply"])
        self.assertEqual(res["workflowStatus"], "COMPLETED")

    # TEST 2 — SCRAPER REQUEST
    @patch("scraper_manager.scraper_manager.create_job")
    def test_11_master_test_2_scraper_request(self, mock_create):
        mock_create.return_value = "job-bonfire-master-2"
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Scrape 50 contractor leads in Dallas from Bonfire.",
        )
        self.assertEqual(res["recommendedScript"], "bonfire")
        self.assertEqual(res["jobId"], "job-bonfire-master-2")
        self.assertIn("RUNNING", res["reply"])

    # TEST 3 — COMBINED WORKFLOW
    @patch("scraper_manager.scraper_manager.create_job")
    def test_12_master_test_3_combined_workflow(self, mock_create):
        mock_create.return_value = "job-bonfire-master-3"
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Find Dallas contractors already in the database and also scrape fresh Bonfire results.",
        )
        self.assertIn("database", res["agentsInvolved"])
        self.assertIn("scraper", res["agentsInvolved"])
        self.assertEqual(res["workflowStatus"], "COMPLETED")
        self.assertEqual(res["jobId"], "job-bonfire-master-3")

    # TEST 4 — BLOCKED SCRAPER
    def test_13_master_test_4_blocked_scraper(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NYSCR_USERNAME", None)
            os.environ.pop("NYSCR_PASSWORD", None)
            res = self.orchestrator.handle_message(
                session_id=self.session_id,
                message="Run scraper NYSCR to harvest contracts",
            )
            self.assertEqual(res["decision"], "BLOCKED")
            self.assertIn("BLOCKED", res["reply"])
            self.assertIn("NYSCR credentials are not configured", res["reply"])

    # TEST 5 — LLM OFFLINE
    @patch("agents.intent.engine.get_llm_provider")
    def test_14_master_test_5_llm_offline(self, mock_provider_factory):
        mock_provider = MagicMock()
        mock_provider.generate_structured.side_effect = ConnectionError("Ollama/vLLM daemon offline")
        mock_provider_factory.return_value = mock_provider

        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me contractors in Dallas from the database",
        )
        self.assertTrue(res["intent"].get("is_fallback"))
        self.assertEqual(res["agentCode"], "database")
        self.assertIn("PostgreSQL", res["reply"])

    # TEST 6 — DATABASE FAILURE
    @patch("agents.orchestrator.SessionLocal")
    def test_15_master_test_6_database_failure(self, mock_session):
        mock_session.side_effect = ConnectionError("PostgreSQL unreachable")
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me contractors in Dallas from the database",
        )
        self.assertEqual(res["workflowStatus"], "FAILED")
        self.assertIn("error", res["reply"].lower())

    # TEST 7 — INVALID SCRAPER
    def test_16_master_test_7_invalid_scraper(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Run scraper nonexistent_spider_engine",
        )
        self.assertIn("The requested scraper engine was not recognized", res["reply"])
        self.assertIn("bonfire", res["reply"])
        self.assertIsNone(res["jobId"])

    # TEST 8 — UNAUTHORIZED TOOL/AGENT
    def test_17_master_test_8_unauthorized_tool_or_agent(self):
        plan = WorkflowPlan(
            plan_id="plan-auth-test",
            steps=[PlanStep(step_id="step_1", agent="system_shell_agent", action="exec_bash")],
        )
        valid, errors = WorkflowPlanner.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("unauthorized agent", errors[0])

    # TEST 9 — SQL INJECTION
    def test_18_master_test_9_sql_injection(self):
        # Normal chatbot message containing SQL injection attempt
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Show me contractors in Dallas'; DROP TABLE leads; --",
        )
        # Should not crash, should normalize safely and query DB safely using parameterized queries
        self.assertIn("reply", res)
        self.assertEqual(res["agentCode"], "database")

    # TEST 10 — RESPONSE CONTRACT
    def test_19_master_test_10_response_contract(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Find contractors in Dallas and compare with existing leads",
        )
        expected_fields = [
            "reply", "suggestions", "updatedRequirement", "recommendedScript",
            "sessionId", "decision", "agentCode", "handledBy", "jobId",
            "proposedActions", "collaborationId", "agentsInvolved", "agentSteps"
        ]
        for field in expected_fields:
            self.assertIn(field, res, f"Field '{field}' missing from contract")
        self.assertIsInstance(res["suggestions"], list)
        self.assertIsInstance(res["agentsInvolved"], list)
        self.assertIsInstance(res["agentSteps"], list)


if __name__ == "__main__":
    unittest.main()
