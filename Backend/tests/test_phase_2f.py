"""
tests/test_phase_2f.py
───────────────────────
Verification test suite for Phase 2F: Multi-Agent Collaboration.
Validates structured collaboration context, sequential dependencies, agent authorization,
result isolation, truthful partial success, and response contract consistency.

Scenarios tested (2F.8 Master Acceptance):
  A. database-only workflow
  B. scraper-only workflow
  C. database + scraper workflow
  D. dependency enforcement
  E. dependent step blocked after predecessor failure
  F. partial success
  G. complete success
  H. unauthorized agent rejected
  I. collaboration metadata populated
  J. collaboration ID consistency
  K. structured intermediate result passing
  L. no fabricated results
  M. existing Phase 2E response contract preserved
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.intent.models import IntentType, StructuredIntent
from agents.workflow.models import (
    CollaborationContext,
    PlanStep,
    StepStatus,
    WorkflowPlan,
    WorkflowResult,
    WorkflowStatus,
)
from agents.workflow.planner import WorkflowPlanner
from agents.workflow.collaboration import (
    WorkflowCollaborationEngine,
    workflow_collaboration_engine,
)
from agents.orchestrator import AgentOrchestrator


class TestPhase2F(unittest.TestCase):
    """Phase 2F Multi-Agent Collaboration Test Suite."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.session_id = f"sess-test-2f-{os.urandom(4).hex()}"

    # A. database-only workflow
    def test_01_database_only_workflow(self):
        plan = WorkflowPlan(
            plan_id="plan-db-only",
            route="database_only",
            steps=[
                PlanStep(
                    step_id="step_1",
                    agent="database",
                    action="search_leads",
                    dependencies=[],
                    parameters={"category": "Contractor", "location": "Dallas", "quantity": 10},
                )
            ],
        )
        res, ctx = workflow_collaboration_engine.execute(plan, original_request="Show contractors in Dallas")
        self.assertEqual(res.status, WorkflowStatus.COMPLETED)
        self.assertEqual(len(ctx.completed_steps), 1)
        self.assertEqual(ctx.participating_agents, ["database"])
        self.assertIn("step_1", ctx.intermediate_results)
        self.assertIn("database", ctx.intermediate_results)

    # B. scraper-only workflow
    @patch("scraper_manager.scraper_manager.create_job")
    def test_02_scraper_only_workflow(self, mock_create):
        mock_create.return_value = "job-bonfire-test-02"
        plan = WorkflowPlan(
            plan_id="plan-scraper-only",
            route="scraper_only",
            steps=[
                PlanStep(
                    step_id="step_1",
                    agent="scraper",
                    action="create_job",
                    dependencies=[],
                    parameters={"scraper_id": "bonfire", "quantity": 25, "location": "Dallas"},
                )
            ],
        )
        res, ctx = workflow_collaboration_engine.execute(plan, original_request="Scrape Bonfire")
        self.assertEqual(res.status, WorkflowStatus.COMPLETED)
        self.assertEqual(ctx.participating_agents, ["scraper"])
        self.assertEqual(res.aggregated_data.get("scraperJobId"), "job-bonfire-test-02")
        self.assertEqual(len(ctx.completed_steps), 1)

    # C. database + scraper workflow
    @patch("scraper_manager.scraper_manager.create_job")
    def test_03_database_and_scraper_workflow(self, mock_create):
        mock_create.return_value = "job-bonfire-collab-03"
        plan = WorkflowPlan(
            plan_id="plan-combined-03",
            route="combined",
            steps=[
                PlanStep(
                    step_id="step_1",
                    agent="database",
                    action="search_leads",
                    dependencies=[],
                    parameters={"category": "Contractor", "location": "Dallas"},
                ),
                PlanStep(
                    step_id="step_2",
                    agent="scraper",
                    action="create_job",
                    dependencies=["step_1"],
                    parameters={"scraper_id": "bonfire", "quantity": 20},
                ),
                PlanStep(
                    step_id="step_3",
                    agent="database",
                    action="compare_leads",
                    dependencies=["step_1", "step_2"],
                    parameters={"comparison_key": "title"},
                ),
            ],
        )
        res, ctx = workflow_collaboration_engine.execute(plan, original_request="Find and scrape")
        self.assertEqual(res.status, WorkflowStatus.COMPLETED)
        self.assertEqual(len(ctx.completed_steps), 3)
        self.assertEqual(ctx.participating_agents, ["database", "scraper"])
        self.assertFalse(res.is_partial)

    # D. dependency enforcement
    def test_04_dependency_enforcement(self):
        plan = WorkflowPlan(
            plan_id="plan-deps",
            steps=[
                PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[]),
                PlanStep(step_id="step_2", agent="scraper", action="create_job", dependencies=["step_1"], parameters={"scraper_id": "bonfire"}),
            ],
        )
        with patch("scraper_manager.scraper_manager.create_job", return_value="job-123"):
            res, ctx = workflow_collaboration_engine.execute(plan)
            self.assertEqual(res.status, WorkflowStatus.COMPLETED)
            self.assertIn("step_1", ctx.completed_steps)
            self.assertIn("step_2", ctx.completed_steps)

    # E. dependent step blocked after predecessor failure
    def test_05_dependent_step_blocked_after_predecessor_failure(self):
        plan = WorkflowPlan(
            plan_id="plan-dep-fail",
            steps=[
                PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[]),
                PlanStep(step_id="step_2", agent="scraper", action="create_job", dependencies=["step_1"], parameters={"scraper_id": "bonfire"}),
            ],
        )
        # Mock database failure on step_1
        with patch.object(sys.modules["agents.specialized.database_agent"].database_agent, "search_leads") as mock_db:
            mock_db.return_value = {"success": False, "records": [], "count": 0, "errors": ["DB connection dropped"]}
            with patch("scraper_manager.scraper_manager.create_job") as mock_create:
                res, ctx = workflow_collaboration_engine.execute(plan)
                # Step 1 failed
                self.assertEqual(plan.steps[0].status, StepStatus.FAILED)
                # Step 2 must be BLOCKED because predecessor failed
                self.assertEqual(plan.steps[1].status, StepStatus.BLOCKED)
                self.assertIn("step_1", plan.steps[1].error)
                # create_job must NOT have been called
                mock_create.assert_not_called()
                self.assertEqual(res.status, WorkflowStatus.FAILED)

    # F. partial success (Database succeeds, Scraper blocked due to missing creds)
    def test_06_partial_success(self):
        plan = WorkflowPlan(
            plan_id="plan-partial",
            steps=[
                PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[]),
                PlanStep(step_id="step_2", agent="scraper", action="create_job", dependencies=["step_1"], parameters={"scraper_id": "nyscr"}),
                PlanStep(step_id="step_3", agent="database", action="compare_leads", dependencies=["step_1", "step_2"]),
            ],
        )
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NYSCR_USERNAME", None)
            os.environ.pop("NYSCR_PASSWORD", None)

            res, ctx = workflow_collaboration_engine.execute(plan)

            self.assertEqual(plan.steps[0].status, StepStatus.COMPLETED)
            self.assertEqual(plan.steps[1].status, StepStatus.BLOCKED)
            self.assertEqual(plan.steps[2].status, StepStatus.BLOCKED)  # Step 3 blocked because Step 2 blocked
            self.assertEqual(res.status, WorkflowStatus.PARTIAL)
            self.assertTrue(res.is_partial)
            self.assertIn("step_1", ctx.completed_steps)
            self.assertIn("step_2", ctx.blocked_steps)

    # G. complete success
    @patch("scraper_manager.scraper_manager.create_job")
    def test_07_complete_success(self, mock_create):
        mock_create.return_value = "job-bonfire-success-7"
        plan = WorkflowPlan(
            plan_id="plan-complete-7",
            steps=[
                PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[]),
                PlanStep(step_id="step_2", agent="scraper", action="create_job", dependencies=["step_1"], parameters={"scraper_id": "bonfire"}),
            ],
        )
        res, ctx = workflow_collaboration_engine.execute(plan)
        self.assertEqual(res.status, WorkflowStatus.COMPLETED)
        self.assertFalse(res.is_partial)
        self.assertEqual(len(ctx.completed_steps), 2)
        self.assertEqual(len(ctx.blocked_steps), 0)
        self.assertEqual(len(ctx.failed_steps), 0)

    # H. unauthorized agent rejected
    def test_08_unauthorized_agent_rejected(self):
        plan = WorkflowPlan(
            plan_id="plan-rogue",
            steps=[
                PlanStep(step_id="step_1", agent="unauthorized_rogue_bot", action="execute_arbitrary_cmd", dependencies=[])
            ],
        )
        valid, errors = WorkflowPlanner.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("unauthorized", errors[0].lower())

        # Executing invalid plan must fail safely
        res, ctx = workflow_collaboration_engine.execute(plan)
        self.assertEqual(res.status, WorkflowStatus.FAILED)
        self.assertEqual(len(res.errors), 1)

    # I. collaboration metadata populated
    def test_09_collaboration_metadata_populated(self):
        plan = WorkflowPlan(
            plan_id="plan-meta",
            steps=[
                PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[]),
            ],
        )
        res, ctx = workflow_collaboration_engine.execute(plan)
        formatted = workflow_collaboration_engine.format_collaboration_response(ctx, res)
        self.assertTrue(formatted["collaborationId"].startswith("collab-"))
        self.assertIn("database", formatted["agentsInvolved"])
        self.assertIsInstance(formatted["agentSteps"], list)
        self.assertEqual(len(formatted["agentSteps"]), 1)
        self.assertEqual(formatted["agentSteps"][0]["status"], "COMPLETED")

    # J. collaboration ID consistency
    def test_10_collaboration_id_consistency(self):
        plan = WorkflowPlan(
            plan_id="plan-id-check",
            steps=[PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[])],
        )
        res, ctx = workflow_collaboration_engine.execute(plan)
        formatted = workflow_collaboration_engine.format_collaboration_response(ctx, res)
        self.assertEqual(ctx.collaboration_id, res.workflow_id)
        self.assertEqual(ctx.collaboration_id, formatted["collaborationId"])

    # K. structured intermediate result passing
    @patch("scraper_manager.scraper_manager.create_job")
    def test_11_structured_intermediate_result_passing(self, mock_create):
        mock_create.return_value = "job-bonfire-k11"
        plan = WorkflowPlan(
            plan_id="plan-intermediate",
            steps=[
                PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[], parameters={"category": "Contractor"}),
                PlanStep(step_id="step_2", agent="scraper", action="create_job", dependencies=["step_1"], parameters={"scraper_id": "bonfire"}),
                PlanStep(step_id="step_3", agent="database", action="compare_leads", dependencies=["step_1", "step_2"]),
            ],
        )
        res, ctx = workflow_collaboration_engine.execute(plan)
        step_3_res = ctx.intermediate_results.get("step_3")
        self.assertIsNotNone(step_3_res)
        self.assertTrue(step_3_res.get("success"))
        records = step_3_res.get("records", [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["scraper_job_id"], "job-bonfire-k11")

    # L. no fabricated results
    def test_12_no_fabricated_results(self):
        # When DB has zero records, count is 0 and no synthetic leads are injected
        with patch.object(sys.modules["agents.specialized.database_agent"].database_agent, "search_leads") as mock_db:
            mock_db.return_value = {"success": True, "records": [], "count": 0, "errors": []}
            plan = WorkflowPlan(
                plan_id="plan-zero",
                steps=[PlanStep(step_id="step_1", agent="database", action="search_leads", dependencies=[])],
            )
            res, ctx = workflow_collaboration_engine.execute(plan)
            self.assertEqual(res.aggregated_data.get("databaseCount"), 0)
            self.assertEqual(res.aggregated_data.get("databaseRecords"), [])

    # M. existing Phase 2E response contract preserved
    def test_13_existing_phase_2e_response_contract_preserved(self):
        res = self.orchestrator.handle_message(
            session_id=self.session_id,
            message="Find contractors in Dallas and compare with existing leads through NYSCR",
        )
        expected_fields = [
            "reply", "suggestions", "updatedRequirement", "recommendedScript",
            "sessionId", "decision", "agentCode", "handledBy", "jobId",
            "proposedActions", "collaborationId", "agentsInvolved", "agentSteps"
        ]
        for field in expected_fields:
            self.assertIn(field, res, f"Contract field '{field}' must be present in response")
        self.assertEqual(res["decision"], "PARTIAL")
        self.assertEqual(res["workflowStatus"], "PARTIAL")
        self.assertIn("database", res["agentsInvolved"])
        self.assertIn("scraper", res["agentsInvolved"])


if __name__ == "__main__":
    unittest.main()
