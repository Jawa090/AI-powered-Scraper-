"""
agents/collaboration/engine.py
──────────────────────────────
Layer 12: Multi-Agent Collaboration Execution Engine.

Responsibilities:
  - Executes a validated CollaborationPlan in dependency-aware order.
  - Sanitizes and safely propagates intermediate context between agents.
  - Prevents cyclic execution, infinite loops, and unapproved agent loading.
  - Implements fault-tolerant error boundaries (one agent failure does not crash the pipeline).
  - Integrates with AgentRegistry and CollaborationAggregator.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional, Set

from agents.base import AgentContext, AgentResult, AgentStatus
from agents.registry import agent_registry
from agents.collaboration.models import (
    APPROVED_AGENT_CODES,
    MAX_COLLABORATION_STEPS,
    AgentTask,
    CollaborationContext,
    CollaborationPlan,
    CollaborationResult,
    CollaborationStatus,
    TaskStatus,
)
from agents.collaboration.aggregator import CollaborationAggregator

logger = logging.getLogger(__name__)


class CollaborationEngine:
    """
    Controlled multi-agent orchestration execution coordinator.
    """

    def __init__(self, registry=None):
        self.registry = registry or agent_registry

    def execute(
        self,
        plan: CollaborationPlan,
        session_id: str,
        user_id: str = "usr-ahmed",
        department_id: str = "dept-sales-1",
    ) -> CollaborationResult:
        """
        Execute all tasks in the plan according to their dependencies.
        Returns an aggregated CollaborationResult.
        """
        plan.validate()
        plan.status = CollaborationStatus.RUNNING

        # Initialize shared collaboration context
        collab_context = CollaborationContext(
            collaboration_id=plan.collaboration_id,
            session_id=session_id,
            user_id=user_id,
            department_id=department_id,
            raw_message=plan.original_request,
            normalized_query=plan.normalized_query,
            metadata=dict(plan.metadata),
        )

        completed_task_ids: Set[str] = set()
        failed_task_ids: Set[str] = set()
        executed_steps = 0

        for task in plan.tasks:
            # 1. Loop protection & step boundary check
            executed_steps += 1
            if executed_steps > plan.max_steps:
                task.status = TaskStatus.SKIPPED
                task.error = f"Exceeded maximum collaboration step bound ({plan.max_steps})"
                continue

            # 2. Dependency resolution check
            unmet_deps = [dep for dep in task.dependencies if dep not in completed_task_ids]
            if unmet_deps:
                task.status = TaskStatus.BLOCKED
                failed_or_blocked = [dep for dep in unmet_deps if dep in failed_task_ids]
                if failed_or_blocked:
                    task.error = f"Prerequisite task(s) failed: {', '.join(failed_or_blocked)}"
                else:
                    task.error = f"Unresolved prerequisite dependencies: {', '.join(unmet_deps)}"
                failed_task_ids.add(task.task_id)
                continue

            # 3. Agent whitelist & registry validation
            if task.agent_code not in APPROVED_AGENT_CODES:
                task.status = TaskStatus.FAILED
                task.error = f"Unauthorized agent code '{task.agent_code}'."
                failed_task_ids.add(task.task_id)
                continue

            if not self.registry.is_registered(task.agent_code):
                task.status = TaskStatus.FAILED
                task.error = f"Agent '{task.agent_code}' is not registered in AgentRegistry."
                failed_task_ids.add(task.task_id)
                continue

            # 4. Construct sanitized AgentContext for this task
            agent_instance = self.registry.get(task.agent_code)
            task_context = self._build_task_agent_context(
                collab_context=collab_context,
                task=task,
                plan=plan,
            )

            # 5. Execute specialized agent with error isolation
            task.status = TaskStatus.RUNNING
            try:
                result: AgentResult = agent_instance.handle(task_context)
                task.result = result

                if result.status == AgentStatus.ERROR:
                    task.status = TaskStatus.FAILED
                    task.error = result.message
                    failed_task_ids.add(task.task_id)
                else:
                    task.status = TaskStatus.COMPLETED
                    completed_task_ids.add(task.task_id)

                    # Propagate sanitized task output to shared context
                    self._propagate_result_data(collab_context, task, result)

            except Exception as exc:  # pylint: disable=broad-except
                tb = traceback.format_exc()
                logger.error(f"[CollaborationEngine] Task {task.task_id} failed: {exc}\n{tb}")
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                failed_task_ids.add(task.task_id)

        # 6. Aggregate results
        collab_result = CollaborationAggregator.aggregate(plan, session_id=session_id)
        plan.status = collab_result.status

        return collab_result

    def _build_task_agent_context(
        self,
        collab_context: CollaborationContext,
        task: AgentTask,
        plan: CollaborationPlan,
    ) -> AgentContext:
        """
        Construct a clean, sanitized AgentContext for a single task execution,
        enriching it with sanitized data produced by prior tasks.
        """
        # Base metadata
        meta = dict(collab_context.metadata)
        meta["collaboration_id"] = collab_context.collaboration_id
        meta["task_id"] = task.task_id
        meta["purpose"] = task.purpose
        meta["previous_agents"] = list(collab_context.previous_results.keys())

        # Enrich context based on prior agent outputs
        norm_query = dict(collab_context.normalized_query or {})
        
        # Inject leads/organizations from 'data' agent into downstream agents
        if "data" in collab_context.previous_results:
            data_out = collab_context.previous_results["data"]
            leads = data_out.get("leads") or []
            if leads:
                meta["upstream_leads"] = leads[:20]  # bounded handoff
                meta["upstream_lead_count"] = len(leads)
            if data_out.get("category"):
                norm_query["category"] = data_out["category"]
            if data_out.get("location"):
                norm_query["location"] = data_out["location"]

        # Inject sales prioritization results into email/growth agents
        if "sales" in collab_context.previous_results:
            sales_out = collab_context.previous_results["sales"]
            prioritized = sales_out.get("prioritized_leads") or sales_out.get("leads") or []
            if prioritized:
                meta["prioritized_leads"] = prioritized[:10]
            if sales_out.get("analysis"):
                meta["sales_analysis"] = sales_out["analysis"]

        # Inject research market intelligence into growth agent
        if "research" in collab_context.previous_results:
            res_out = collab_context.previous_results["research"]
            if res_out.get("market_findings"):
                meta["market_findings"] = res_out["market_findings"]

        return AgentContext(
            session_id=collab_context.session_id,
            user_id=collab_context.user_id,
            department_id=collab_context.department_id,
            normalized_query=norm_query,
            availability_decision=meta.get("availability_decision", "USE_DATABASE"),
            records_available=meta.get("upstream_lead_count", 20),
            raw_message=task.input_context.get("raw_message", collab_context.raw_message),
            metadata=meta,
        )

    def _propagate_result_data(
        self,
        collab_context: CollaborationContext,
        task: AgentTask,
        result: AgentResult,
    ) -> None:
        """
        Extract safe, structured facts from the agent result and store in previous_results.
        """
        if not result or not result.data:
            collab_context.previous_results[task.agent_code] = {
                "status": result.status.value if result else "unknown",
                "message": result.message if result else "",
            }
            return

        safe_data: Dict[str, Any] = {
            "status": result.status.value,
            "message": result.message[:250],
        }

        # Extract specific data structures depending on agent type
        raw_data = result.data

        if task.agent_code == "data":
            safe_data["leads"] = raw_data.get("leads") or raw_data.get("sampleLeads") or []
            safe_data["count"] = raw_data.get("totalCount") or len(safe_data["leads"])
            safe_data["category"] = raw_data.get("category")
            safe_data["location"] = raw_data.get("location")

        elif task.agent_code == "sales":
            safe_data["prioritized_leads"] = raw_data.get("prioritizedLeads") or raw_data.get("leads") or []
            safe_data["top_prospects"] = raw_data.get("topProspects") or []
            safe_data["analysis"] = raw_data.get("salesAnalysis")

        elif task.agent_code == "research":
            safe_data["market_findings"] = raw_data.get("findings") or raw_data.get("marketSummary")
            safe_data["sources"] = raw_data.get("sources") or []

        elif task.agent_code == "email":
            safe_data["drafts"] = raw_data.get("drafts") or raw_data.get("templates") or []
            safe_data["draft_count"] = len(safe_data["drafts"])

        elif task.agent_code == "growth":
            safe_data["strategy"] = raw_data.get("strategy") or raw_data.get("recommendations") or []

        # Store in previous_results and sanitize
        collab_context.previous_results[task.agent_code] = safe_data
        collab_context.sanitize()


# Global collaboration engine instance
collaboration_engine = CollaborationEngine()
