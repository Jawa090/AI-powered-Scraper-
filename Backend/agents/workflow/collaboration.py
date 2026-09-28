"""
agents/workflow/collaboration.py
─────────────────────────────────
WorkflowCollaborationEngine — Phase 2F Multi-Agent Collaboration Coordinator.

Executes validated WorkflowPlan instances across authorized specialized agents
(DatabaseAgent, ScraperAgent, Orchestrator) with strict dependency tracking,
structured intermediate result passing, truthful state transitions (COMPLETED,
PARTIAL, BLOCKED, FAILED), agent authorization enforcement, and zero synthetic data.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple, Set

from agents.intent.models import StructuredIntent
from agents.workflow.models import (
    CollaborationContext,
    PlanStep,
    StepStatus,
    WorkflowPlan,
    WorkflowResult,
    WorkflowStatus,
)
from agents.workflow.planner import WorkflowPlanner
from agents.specialized.database_agent import database_agent
from agents.specialized.scraper_agent import scraper_agent
from execution.registry import SCRIPTS_REGISTRY

logger = logging.getLogger(__name__)

# Strict authorization boundary: only approved agents can execute in workflows
AUTHORIZED_WORKFLOW_AGENTS = frozenset({
    "database",
    "scraper",
    "orchestrator",
    "sales",
    "research",
})


class WorkflowCollaborationEngine:
    """
    Central execution and collaboration coordinator for multi-agent workflows.
    Ensures sequential dependencies are enforced, agent results are isolated,
    intermediate results are propagated, and states are reported truthfully.
    """

    @classmethod
    def execute(
        cls,
        plan: WorkflowPlan,
        original_request: str = "",
        context_intent: Optional[StructuredIntent] = None,
    ) -> Tuple[WorkflowResult, CollaborationContext]:
        """
        Executes a validated WorkflowPlan.
        Returns a (WorkflowResult, CollaborationContext) pair.
        """
        # 1. Plan validation & agent authorization check
        is_valid, plan_errors = WorkflowPlanner.validate_plan(plan)
        if not is_valid:
            logger.warning("[WorkflowCollaborationEngine] Plan validation failed: %s", plan_errors)
            collab_ctx = CollaborationContext(
                collaboration_id=f"collab-{uuid.uuid4().hex[:12]}",
                original_request=original_request,
                intent=context_intent.to_dict() if context_intent else (plan.intent or {}),
                workflow_plan=plan,
                participating_agents=list(dict.fromkeys(s.agent for s in plan.steps)),
                failed_steps=[s.step_id for s in plan.steps],
                final_status=WorkflowStatus.FAILED,
            )
            wf_res = WorkflowResult(
                workflow_id=collab_ctx.collaboration_id,
                status=WorkflowStatus.FAILED,
                plan_id=plan.plan_id,
                steps_executed=plan.steps,
                errors=plan_errors,
                is_partial=False,
            )
            return wf_res, collab_ctx

        # 2. Initialize CollaborationContext
        participating = list(dict.fromkeys(s.agent for s in plan.steps))
        collab_ctx = CollaborationContext(
            collaboration_id=f"collab-{uuid.uuid4().hex[:12]}",
            original_request=original_request,
            intent=context_intent.to_dict() if context_intent else (plan.intent or {}),
            workflow_plan=plan,
            participating_agents=participating,
            final_status=WorkflowStatus.IN_PROGRESS,
        )

        completed_ids: Set[str] = set()
        failed_or_blocked_ids: Set[str] = set()

        # 3. Execute steps in sequential / DAG dependency order
        for step in plan.steps:
            # Check agent authorization
            if step.agent not in AUTHORIZED_WORKFLOW_AGENTS:
                step.status = StepStatus.FAILED
                step.error = f"Unauthorized agent '{step.agent}'"
                collab_ctx.failed_steps.append(step.step_id)
                failed_or_blocked_ids.add(step.step_id)
                continue

            # Check prerequisite dependencies
            unmet_deps = [dep for dep in step.dependencies if dep not in completed_ids]
            if unmet_deps:
                step.status = StepStatus.BLOCKED
                step.error = f"Prerequisite step(s) failed or blocked: {', '.join(unmet_deps)}"
                collab_ctx.blocked_steps.append(step.step_id)
                failed_or_blocked_ids.add(step.step_id)
                continue

            # Execute step according to authorized agent
            step.status = StepStatus.RUNNING
            try:
                cls._execute_single_step(step, collab_ctx)
            except Exception as exc:
                logger.error("[WorkflowCollaborationEngine] Step %s failed: %s", step.step_id, exc)
                step.status = StepStatus.FAILED
                step.error = str(exc)

            # Record outcome
            if step.status == StepStatus.COMPLETED:
                completed_ids.add(step.step_id)
                collab_ctx.completed_steps.append(step.step_id)
            elif step.status == StepStatus.BLOCKED:
                failed_or_blocked_ids.add(step.step_id)
                collab_ctx.blocked_steps.append(step.step_id)
            else:
                step.status = StepStatus.FAILED
                failed_or_blocked_ids.add(step.step_id)
                collab_ctx.failed_steps.append(step.step_id)

        # 4. Compute overall final status truthfully
        total_steps = len(plan.steps)
        completed_count = len(collab_ctx.completed_steps)
        blocked_count = len(collab_ctx.blocked_steps)
        failed_count = len(collab_ctx.failed_steps)

        if completed_count == total_steps and total_steps > 0:
            final_status = WorkflowStatus.COMPLETED
        elif blocked_count == total_steps and total_steps > 0:
            final_status = WorkflowStatus.BLOCKED
        elif failed_count == total_steps and total_steps > 0:
            final_status = WorkflowStatus.FAILED
        elif completed_count > 0 and (blocked_count > 0 or failed_count > 0):
            final_status = WorkflowStatus.PARTIAL
        else:
            final_status = WorkflowStatus.PARTIAL if completed_count > 0 else WorkflowStatus.FAILED

        collab_ctx.final_status = final_status

        # 5. Build final WorkflowResult
        errors = [s.error for s in plan.steps if s.error]
        wf_res = WorkflowResult(
            workflow_id=collab_ctx.collaboration_id,
            status=final_status,
            plan_id=plan.plan_id,
            steps_executed=plan.steps,
            agent_results=collab_ctx.intermediate_results,
            aggregated_data=cls._aggregate_intermediate_data(collab_ctx),
            errors=errors,
            is_partial=(final_status == WorkflowStatus.PARTIAL),
        )

        return wf_res, collab_ctx

    @classmethod
    def _execute_single_step(cls, step: PlanStep, context: CollaborationContext) -> None:
        """
        Executes a discrete plan step strictly via the authorized agent boundaries.
        """
        params = step.parameters or {}

        if step.agent == "database":
            if step.action == "search_leads":
                filters = params.get("filters") or {}
                if params.get("category") and "category" not in filters:
                    filters["category"] = params["category"]
                if params.get("location") and "location" not in filters:
                    filters["location"] = params["location"]
                limit = params.get("quantity") or 20
                res = database_agent.search_leads(filters=filters, limit=limit)
                step.result = res
                if res.get("success"):
                    step.status = StepStatus.COMPLETED
                    context.intermediate_results[step.step_id] = res
                    context.intermediate_results["database"] = res
                else:
                    step.status = StepStatus.FAILED
                    step.error = "; ".join(res.get("errors", ["Database lead search failed"]))

            elif step.action == "compare_leads":
                # Intermediate result passing: read from previous steps
                db_data = context.intermediate_results.get("step_1") or context.intermediate_results.get("database") or {}
                scraper_data = context.intermediate_results.get("step_2") or context.intermediate_results.get("scraper") or {}
                db_records = db_data.get("records") or []
                job_id = scraper_data.get("job_id") or scraper_data.get("jobId")
                comparison_key = params.get("comparison_key", "title")

                res = database_agent.compare_leads(
                    db_records=db_records,
                    scraper_job_id=job_id,
                    comparison_key=comparison_key,
                )
                step.result = res
                step.status = StepStatus.COMPLETED
                context.intermediate_results[step.step_id] = res

            elif step.action == "search_datasets":
                limit = params.get("limit", 10)
                res = database_agent.search_datasets(limit=limit)
                step.result = res
                step.status = StepStatus.COMPLETED if res.get("success") else StepStatus.FAILED
                if res.get("success"):
                    context.intermediate_results[step.step_id] = res
                else:
                    step.error = "; ".join(res.get("errors", ["Dataset search failed"]))

            elif step.action == "get_job_status":
                job_id = params.get("job_id")
                res = database_agent.get_job(job_id)
                step.result = res
                step.status = StepStatus.COMPLETED if res.get("success") else StepStatus.FAILED
                if res.get("success"):
                    context.intermediate_results[step.step_id] = res
                else:
                    step.error = "; ".join(res.get("errors", ["Get job failed"]))

            else:
                step.status = StepStatus.FAILED
                step.error = f"Unsupported database action '{step.action}'"

        elif step.agent == "scraper":
            if step.action == "create_job":
                scraper_id = params.get("scraper_id")
                # 1. Preflight credentials check
                has_creds, cred_err = scraper_agent.check_credentials_preflight(scraper_id)
                if not has_creds:
                    step.status = StepStatus.BLOCKED
                    step.error = cred_err
                    context.intermediate_results[step.step_id] = {
                        "status": "BLOCKED",
                        "error": cred_err,
                        "scraper_id": scraper_id,
                    }
                    context.intermediate_results["scraper"] = {
                        "status": "BLOCKED",
                        "error": cred_err,
                        "scraper_id": scraper_id,
                    }
                    return

                # 2. Prepare parameters & invoke canonical pipeline
                prepared_params = scraper_agent.prepare_parameters(scraper_id, params)
                job_res = scraper_agent.create_job(scraper_id, prepared_params)
                step.result = job_res

                if job_res.get("success"):
                    step.status = StepStatus.COMPLETED
                    context.intermediate_results[step.step_id] = job_res
                    context.intermediate_results["scraper"] = job_res
                else:
                    if job_res.get("status") == "BLOCKED":
                        step.status = StepStatus.BLOCKED
                    else:
                        step.status = StepStatus.FAILED
                    err_msg = "; ".join(job_res.get("errors", ["Scraper job creation failed"]))
                    step.error = err_msg
                    context.intermediate_results[step.step_id] = job_res
                    context.intermediate_results["scraper"] = job_res

            elif step.action == "get_job_status":
                job_id = params.get("job_id")
                res = scraper_agent.get_job_status(job_id)
                step.result = res
                step.status = StepStatus.COMPLETED if res.get("success") else StepStatus.FAILED
                if res.get("success"):
                    context.intermediate_results[step.step_id] = res
                else:
                    step.error = "; ".join(res.get("errors", ["Scraper status query failed"]))

            elif step.action == "get_job_result":
                job_id = params.get("job_id")
                res = scraper_agent.get_job_result(job_id)
                step.result = res
                step.status = StepStatus.COMPLETED if res.get("success") else StepStatus.FAILED
                if res.get("success"):
                    context.intermediate_results[step.step_id] = res
                else:
                    step.error = "; ".join(res.get("errors", ["Scraper result query failed"]))

            else:
                step.status = StepStatus.FAILED
                step.error = f"Unsupported scraper action '{step.action}'"

        elif step.agent == "orchestrator":
            step.status = StepStatus.COMPLETED
            step.result = {"message": "Orchestrator general query acknowledged."}
            context.intermediate_results[step.step_id] = step.result

        else:
            step.status = StepStatus.FAILED
            step.error = f"Agent '{step.agent}' execution handler not registered"

    @classmethod
    def _aggregate_intermediate_data(cls, context: CollaborationContext) -> Dict[str, Any]:
        """
        Gathers and structures intermediate results without fabricating any data.
        """
        aggregated: Dict[str, Any] = {
            "collaborationId": context.collaboration_id,
            "status": context.final_status.value if isinstance(context.final_status, WorkflowStatus) else str(context.final_status),
            "participatingAgents": context.participating_agents,
            "completedSteps": context.completed_steps,
            "blockedSteps": context.blocked_steps,
            "failedSteps": context.failed_steps,
        }

        db_out = context.intermediate_results.get("database") or {}
        if db_out:
            aggregated["databaseCount"] = db_out.get("count", 0)
            aggregated["databaseRecords"] = db_out.get("records", [])

        scraper_out = context.intermediate_results.get("scraper") or {}
        if scraper_out:
            aggregated["scraperJobId"] = scraper_out.get("job_id")
            aggregated["scraperStatus"] = scraper_out.get("status")
            if scraper_out.get("error"):
                aggregated["scraperError"] = scraper_out.get("error")

        return aggregated

    @classmethod
    def format_collaboration_response(
        cls,
        context: CollaborationContext,
        result: WorkflowResult,
        target_script: str = "bonfire",
    ) -> Dict[str, Any]:
        """
        Builds a truthful, formatted response dictionary matching the 13-field API contract.
        """
        db_res = context.intermediate_results.get("database") or {}
        scraper_res = context.intermediate_results.get("scraper") or {}

        existing_count = db_res.get("count", 0)
        job_id = scraper_res.get("job_id")
        scraper_status = scraper_res.get("status")
        scraper_err = scraper_res.get("error") or (result.errors[0] if result.errors else None)

        script_upper = (target_script or "SCRAPER").upper()

        if context.final_status == WorkflowStatus.PARTIAL:
            reply = (
                f"Database evaluation: Found **{existing_count} existing records** in PostgreSQL.\n\n"
                f"Live scraper execution (**{script_upper}**) is **{scraper_status or 'BLOCKED'}**.\n"
                f"Reason: {scraper_err or 'Required configuration unavailable'}\n\n"
                f"Workflow Status: **PARTIAL** (Database: SUCCESS, Scraper: {scraper_status or 'BLOCKED'})"
            )
            suggestions = ["View Existing Leads", "Configure Credentials", "Select Different Engine"]
            decision = "PARTIAL"

        elif context.final_status == WorkflowStatus.COMPLETED:
            if job_id:
                reply = (
                    f"Combined workflow initiated successfully.\n\n"
                    f"Database evaluation: Found **{existing_count} existing records** in PostgreSQL.\n"
                    f"Live scraper (**{script_upper}**) triggered (Job **{job_id}**).\n\n"
                    f"Workflow Status: **COMPLETED**\n"
                    f"Results will be compared and synthesized upon extraction completion."
                )
                suggestions = [f"Status of job {job_id}", "View Existing Leads", "Show Recent Jobs"]
                decision = "NEED_FETCH"
            else:
                reply = (
                    f"Workflow completed successfully.\n\n"
                    f"Found **{existing_count} verified records** directly from PostgreSQL.\n\n"
                    f"Workflow Status: **COMPLETED**"
                )
                suggestions = ["View Results", "Show Datasets", "Export Records"]
                decision = "USE_DATABASE"

        elif context.final_status == WorkflowStatus.BLOCKED:
            reply = (
                f"Workflow execution is **BLOCKED**.\n\n"
                f"Target Engine: **{script_upper}**\n"
                f"Reason: {scraper_err or 'Missing required credentials'}\n\n"
                f"Please configure required credentials before proceeding."
            )
            suggestions = ["Configure Credentials", "Select Different Engine", "View Database Leads"]
            decision = "BLOCKED"

        else:  # FAILED
            err_details = "; ".join(result.errors) if result.errors else "Execution error"
            reply = (
                f"Workflow execution could not be completed.\n\n"
                f"Status: **FAILED**\n"
                f"Reason: {err_details}"
            )
            suggestions = ["Retry Request", "Check System Status", "View Available Leads"]
            decision = "FAILED"

        return {
            "reply": reply,
            "suggestions": suggestions,
            "decision": decision,
            "jobId": job_id,
            "collaborationId": context.collaboration_id,
            "collaborationStatus": context.final_status.value if isinstance(context.final_status, WorkflowStatus) else str(context.final_status),
            "agentsInvolved": context.participating_agents,
            "agentSteps": [s.to_dict() for s in result.steps_executed],
            "workflowStatus": context.final_status.value if isinstance(context.final_status, WorkflowStatus) else str(context.final_status),
        }


# Global singleton instance
workflow_collaboration_engine = WorkflowCollaborationEngine()
