"""
agents/workflow/planner.py
──────────────────────────
WorkflowPlanner: Central planning engine for Phase 2B.
Deconstructs StructuredIntent into a deterministic, authorized WorkflowPlan.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from agents.intent.models import IntentType, StructuredIntent
from agents.workflow.models import PlanStep, StepStatus, WorkflowPlan
from execution.registry import SCRIPTS_REGISTRY

logger = logging.getLogger(__name__)


class WorkflowPlanner:
    """
    Translates validated StructuredIntent into an authorized, multi-step WorkflowPlan.
    Does NOT execute tools or scrapers. Strictly produces execution plans.
    """

    @classmethod
    def plan(cls, intent: StructuredIntent) -> WorkflowPlan:
        """
        Constructs a WorkflowPlan based on the validated StructuredIntent.
        """
        route = cls._determine_route(intent)
        steps: List[PlanStep] = []

        if route == "database_only":
            steps.append(
                PlanStep(
                    step_id="step_1",
                    agent="database",
                    action="search_leads",
                    dependencies=[],
                    parameters={
                        "category": intent.category,
                        "location": intent.location,
                        "quantity": intent.quantity or 20,
                        "fields": intent.fields,
                        "filters": intent.filters,
                        "freshness": intent.freshness,
                    },
                )
            )

        elif route == "scraper_only":
            scraper_id = cls._resolve_scraper_id(intent)
            steps.append(
                PlanStep(
                    step_id="step_1",
                    agent="scraper",
                    action="create_job",
                    dependencies=[],
                    parameters={
                        "scraper_id": scraper_id,
                        "category": intent.category,
                        "location": intent.location,
                        "quantity": intent.quantity or 20,
                        "freshness": intent.freshness,
                    },
                )
            )

        elif route == "combined":
            # Step 1: Query existing DB leads
            steps.append(
                PlanStep(
                    step_id="step_1",
                    agent="database",
                    action="search_leads",
                    dependencies=[],
                    parameters={
                        "category": intent.category,
                        "location": intent.location,
                        "quantity": intent.quantity or 20,
                        "filters": intent.filters,
                    },
                )
            )
            # Step 2: Trigger scraping job for new leads
            scraper_id = cls._resolve_scraper_id(intent)
            steps.append(
                PlanStep(
                    step_id="step_2",
                    agent="scraper",
                    action="create_job",
                    dependencies=["step_1"],
                    parameters={
                        "scraper_id": scraper_id,
                        "category": intent.category,
                        "location": intent.location,
                        "quantity": intent.quantity or 20,
                    },
                )
            )
            # Step 3: Compare / synthesize results
            steps.append(
                PlanStep(
                    step_id="step_3",
                    agent="database",
                    action="compare_leads",
                    dependencies=["step_1", "step_2"],
                    parameters={
                        "comparison_key": "title",
                    },
                )
            )

        elif route == "job_status":
            steps.append(
                PlanStep(
                    step_id="step_1",
                    agent="database",
                    action="get_job_status",
                    dependencies=[],
                    parameters={
                        "job_id": intent.job_id,
                    },
                )
            )

        elif route == "dataset":
            steps.append(
                PlanStep(
                    step_id="step_1",
                    agent="database",
                    action="search_datasets",
                    dependencies=[],
                    parameters={
                        "dataset_id": intent.dataset_id,
                        "category": intent.category,
                    },
                )
            )

        elif route == "general":
            steps.append(
                PlanStep(
                    step_id="step_1",
                    agent="orchestrator",
                    action="general_response",
                    dependencies=[],
                    parameters={
                        "user_request": intent.user_request,
                    },
                )
            )

        else:  # unsupported
            steps.append(
                PlanStep(
                    step_id="step_1",
                    agent="orchestrator",
                    action="unsupported_response",
                    dependencies=[],
                    parameters={
                        "user_request": intent.user_request,
                    },
                )
            )

        return WorkflowPlan(
            plan_id=str(uuid.uuid4()),
            intent=intent.to_dict(),
            steps=steps,
            route=route,
        )

    @classmethod
    def _determine_route(cls, intent: StructuredIntent) -> str:
        """
        Determines the routing category (A through G).
        """
        if intent.intent == IntentType.JOB_STATUS:
            return "job_status"
        if intent.intent == IntentType.DATASET_QUERY:
            return "dataset"
        if intent.intent == IntentType.GENERAL_INFORMATION:
            return "general"

        if intent.needs_database and intent.needs_scraping:
            return "combined"
        if intent.needs_database and not intent.needs_scraping:
            return "database_only"
        if intent.needs_scraping and not intent.needs_database:
            return "scraper_only"

        if intent.intent == IntentType.DATABASE_SEARCH:
            return "database_only"
        if intent.intent == IntentType.SCRAPER_REQUEST:
            return "scraper_only"
        if intent.intent == IntentType.LEAD_DISCOVERY:
            # Default to database-first discovery
            return "database_only"

        return "unsupported"

    @classmethod
    def _resolve_scraper_id(cls, intent: StructuredIntent) -> Optional[str]:
        if intent.scraper_id:
            return intent.scraper_id

        from execution.registry import recommend_scraper  # noqa: PLC0415

        return recommend_scraper(intent.category, intent.location, intent.user_request)

    @classmethod
    def validate_plan(cls, plan: WorkflowPlan) -> Tuple[bool, List[str]]:
        """
        Validates the constructed plan: checks dependencies, agent authorization, parameters.
        """
        errors: List[str] = []
        known_agents = {"database", "scraper", "orchestrator", "sales", "research"}
        step_ids = {s.step_id for s in plan.steps}

        for step in plan.steps:
            if step.agent not in known_agents:
                errors.append(f"Step {step.step_id} references unauthorized agent '{step.agent}'")
            for dep in step.dependencies:
                if dep not in step_ids:
                    errors.append(f"Step {step.step_id} has invalid dependency '{dep}'")
            if step.agent == "scraper" and step.action == "create_job":
                sid = step.parameters.get("scraper_id")
                known_scrapers = {s["id"] for s in SCRIPTS_REGISTRY}
                if sid and sid not in known_scrapers:
                    errors.append(f"Scraper step references unknown scraper_id '{sid}'")

        return len(errors) == 0, errors
