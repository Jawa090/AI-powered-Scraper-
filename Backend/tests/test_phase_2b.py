"""
tests/test_phase_2b.py
───────────────────────
Verification test suite for Phase 2B: Orchestrator Integration & Planning.
Tests routing, plan generation, plan validation, and failure handling.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agents.intent.models import IntentType, StructuredIntent
from agents.intent.validator import IntentValidator
from agents.workflow.models import (
    PlanStep,
    StepStatus,
    WorkflowPlan,
    WorkflowResult,
    WorkflowStatus,
)
from agents.workflow.planner import WorkflowPlanner


class TestPhase2B(unittest.TestCase):
    """Tests for Phase 2B: Orchestrator Integration & Workflow Planning."""

    # 1. Database-only routing
    def test_01_database_routing(self):
        intent = StructuredIntent(
            intent=IntentType.DATABASE_SEARCH,
            needs_database=True,
            needs_scraping=False,
            category="Contractor",
            location="Dallas",
            user_request="Show me contractors in Dallas from our database",
        )
        plan = WorkflowPlanner.plan(intent)
        self.assertEqual(plan.route, "database_only")
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].agent, "database")
        self.assertEqual(plan.steps[0].action, "search_leads")

    # 2. Scraper-only routing
    def test_02_scraper_routing(self):
        intent = StructuredIntent(
            intent=IntentType.SCRAPER_REQUEST,
            needs_database=False,
            needs_scraping=True,
            category="Contractor",
            location="Dallas",
            scraper_id="bonfire",
            quantity=50,
            user_request="Scrape 50 contractors in Dallas",
        )
        plan = WorkflowPlanner.plan(intent)
        self.assertEqual(plan.route, "scraper_only")
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].agent, "scraper")
        self.assertEqual(plan.steps[0].action, "create_job")
        self.assertEqual(plan.steps[0].parameters.get("scraper_id"), "bonfire")

    # 3. Combined database + scraper routing
    def test_03_combined_routing(self):
        intent = StructuredIntent(
            intent=IntentType.LEAD_DISCOVERY,
            needs_database=True,
            needs_scraping=True,
            category="Contractor",
            location="Dallas",
            scraper_id="bonfire",
            user_request="Find contractors in Dallas and compare with existing leads",
        )
        plan = WorkflowPlanner.plan(intent)
        self.assertEqual(plan.route, "combined")
        self.assertGreaterEqual(len(plan.steps), 2)
        # Check dependencies
        step_2 = next(s for s in plan.steps if s.step_id == "step_2")
        self.assertIn("step_1", step_2.dependencies)

    # 4. Job status routing
    def test_04_job_status_routing(self):
        intent = StructuredIntent(
            intent=IntentType.JOB_STATUS,
            job_id="job-123-abc",
            user_request="What's the status of job job-123-abc?",
        )
        plan = WorkflowPlanner.plan(intent)
        self.assertEqual(plan.route, "job_status")
        self.assertEqual(plan.steps[0].agent, "database")
        self.assertEqual(plan.steps[0].action, "get_job_status")

    # 5. Dataset routing
    def test_05_dataset_routing(self):
        intent = StructuredIntent(
            intent=IntentType.DATASET_QUERY,
            dataset_id="ds-sample",
            user_request="Show me datasets",
        )
        plan = WorkflowPlanner.plan(intent)
        self.assertEqual(plan.route, "dataset")
        self.assertEqual(plan.steps[0].action, "search_datasets")

    # 6. General information routing
    def test_06_general_routing(self):
        intent = StructuredIntent(
            intent=IntentType.GENERAL_INFORMATION,
            user_request="Hello, what can you do?",
        )
        plan = WorkflowPlanner.plan(intent)
        self.assertEqual(plan.route, "general")
        self.assertEqual(plan.steps[0].agent, "orchestrator")

    # 7. Plan validation: valid plan passes
    def test_07_valid_plan_passes(self):
        intent = StructuredIntent(
            intent=IntentType.DATABASE_SEARCH,
            needs_database=True,
            user_request="Search leads",
        )
        plan = WorkflowPlanner.plan(intent)
        is_valid, errors = WorkflowPlanner.validate_plan(plan)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    # 8. Plan validation: unauthorized agent rejected
    def test_08_unauthorized_agent_in_plan_rejected(self):
        plan = WorkflowPlan(
            steps=[
                PlanStep(
                    step_id="step_1",
                    agent="rogue_unauthorized_agent",
                    action="run_arbitrary_code",
                )
            ]
        )
        is_valid, errors = WorkflowPlanner.validate_plan(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("unauthorized agent" in e for e in errors))

    # 9. Plan validation: invalid dependency rejected
    def test_09_invalid_dependency_rejected(self):
        plan = WorkflowPlan(
            steps=[
                PlanStep(
                    step_id="step_1",
                    agent="database",
                    action="search_leads",
                    dependencies=["nonexistent_step"],
                )
            ]
        )
        is_valid, errors = WorkflowPlanner.validate_plan(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("invalid dependency" in e for e in errors))

    # 10. Malformed scraper ID in plan rejected
    def test_10_malformed_scraper_id_rejected(self):
        plan = WorkflowPlan(
            steps=[
                PlanStep(
                    step_id="step_1",
                    agent="scraper",
                    action="create_job",
                    parameters={"scraper_id": "malicious_scraper_xyz"},
                )
            ]
        )
        is_valid, errors = WorkflowPlanner.validate_plan(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("unknown scraper_id" in e for e in errors))

    # 11. Partial failure representation
    def test_11_partial_failure_representation(self):
        # Database succeeds, scraper fails
        step1 = PlanStep(
            step_id="step_1",
            agent="database",
            action="search_leads",
            status=StepStatus.COMPLETED,
            result={"count": 10},
        )
        step2 = PlanStep(
            step_id="step_2",
            agent="scraper",
            action="create_job",
            status=StepStatus.BLOCKED,
            error="NYSCR credentials not configured",
        )
        result = WorkflowResult(
            status=WorkflowStatus.PARTIAL,
            steps_executed=[step1, step2],
            is_partial=True,
            errors=["Scraper BLOCKED: NYSCR credentials not configured"],
        )
        self.assertEqual(result.status, WorkflowStatus.PARTIAL)
        self.assertTrue(result.is_partial)
        self.assertIn("BLOCKED", result.errors[0])

    # 12. Complete failure representation
    def test_12_complete_failure_representation(self):
        step1 = PlanStep(
            step_id="step_1",
            agent="database",
            action="search_leads",
            status=StepStatus.FAILED,
            error="Database connection timeout",
        )
        result = WorkflowResult(
            status=WorkflowStatus.FAILED,
            steps_executed=[step1],
            is_partial=False,
            errors=["Database connection timeout"],
        )
        self.assertEqual(result.status, WorkflowStatus.FAILED)
        self.assertFalse(result.is_partial)

    # 13. Successful workflow representation
    def test_13_successful_workflow(self):
        step1 = PlanStep(
            step_id="step_1",
            agent="database",
            action="search_leads",
            status=StepStatus.COMPLETED,
            result={"count": 25, "records": [{"id": "lead-1"}]},
        )
        result = WorkflowResult(
            status=WorkflowStatus.COMPLETED,
            steps_executed=[step1],
            is_partial=False,
            aggregated_data={"leads_count": 25},
        )
        self.assertEqual(result.status, WorkflowStatus.COMPLETED)
        self.assertEqual(result.aggregated_data.get("leads_count"), 25)


if __name__ == "__main__":
    unittest.main()
