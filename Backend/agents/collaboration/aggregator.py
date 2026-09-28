"""
agents/collaboration/aggregator.py
──────────────────────────────────
Layer 12: Multi-Agent Result Aggregator.

Combines results from multiple specialized agents into a unified, auditable AgentResult:
  - Preserves agent attribution (which agent produced what).
  - Distinguishes SUCCESS / PARTIAL / FAILED workflows.
  - De-duplicates and aggregates proposed actions.
  - Merges contextual quick-action suggestions.
  - Generates polished, structured markdown messages for the frontend.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from agents.base import AgentResult, AgentStatus, ProposedAction
from agents.collaboration.models import (
    AgentTask,
    CollaborationPlan,
    CollaborationResult,
    CollaborationStatus,
    TaskStatus,
)


_AGENT_EMOJIS = {
    "data": "📊",
    "research": "🔬",
    "sales": "🎯",
    "email": "✉️",
    "growth": "📈",
    "orchestrator": "🤖",
}

_AGENT_TITLES = {
    "data": "Data Agent (Lead Discovery)",
    "research": "Research Agent (Market Intelligence)",
    "sales": "Sales Agent (Lead Prioritization)",
    "email": "Email Agent (Outreach Preparation)",
    "growth": "Growth Agent (Strategy & Expansion)",
}


class CollaborationAggregator:
    """
    Combines individual task AgentResults into a single, cohesive AgentResult.
    """

    @classmethod
    def aggregate(
        cls,
        plan: CollaborationPlan,
        session_id: str = "",
    ) -> CollaborationResult:
        """
        Aggregate all task results in a CollaborationPlan into a CollaborationResult.
        """
        completed_tasks = [t for t in plan.tasks if t.status == TaskStatus.COMPLETED]
        failed_tasks = [t for t in plan.tasks if t.status == TaskStatus.FAILED]
        blocked_tasks = [t for t in plan.tasks if t.status == TaskStatus.BLOCKED]
        skipped_tasks = [t for t in plan.tasks if t.status == TaskStatus.SKIPPED]

        # Determine overall collaboration status
        if not plan.tasks:
            status = CollaborationStatus.FAILED
            err_msg = "No tasks were planned for collaboration"
        elif len(completed_tasks) == len(plan.tasks):
            status = CollaborationStatus.COMPLETED
            err_msg = None
        elif len(completed_tasks) > 0:
            status = CollaborationStatus.PARTIAL
            err_msg = f"{len(failed_tasks)} task(s) failed, {len(blocked_tasks)} task(s) blocked."
        else:
            status = CollaborationStatus.FAILED
            err_msg = "; ".join(t.error or f"Task {t.task_id} failed" for t in failed_tasks) or "All tasks failed."

        # Aggregate proposed actions (deduplicate by action_type + label)
        merged_actions: List[ProposedAction] = []
        seen_action_keys: Set[Tuple[str, str]] = set()

        for t in plan.tasks:
            if t.result and t.result.proposed_actions:
                for act in t.result.proposed_actions:
                    key = (act.action_type, act.label)
                    if key not in seen_action_keys:
                        seen_action_keys.add(key)
                        merged_actions.append(act)

        # Aggregate suggestions (deduplicate while preserving order)
        merged_suggestions: List[str] = []
        seen_sugg: Set[str] = set()

        for t in plan.tasks:
            if t.result and t.result.suggestions:
                for s in t.result.suggestions:
                    s_clean = s.strip()
                    if s_clean and s_clean not in seen_sugg:
                        seen_sugg.add(s_clean)
                        merged_suggestions.append(s_clean)

        # Cap suggestions to top 5
        merged_suggestions = merged_suggestions[:5]

        # Aggregate structured data payload
        results_by_agent: Dict[str, Any] = {}
        for t in plan.tasks:
            if t.result and t.result.data:
                results_by_agent[t.agent_code] = t.result.data

        aggregated_data = {
            "collaborationId": plan.collaboration_id,
            "collaborationStatus": status.value,
            "participatingAgents": plan.participating_agents,
            "totalTasks": len(plan.tasks),
            "completedTasks": len(completed_tasks),
            "failedTasks": len(failed_tasks),
            "blockedTasks": len(blocked_tasks),
            "resultsByAgent": results_by_agent,
        }

        # Build polished human-readable message
        message = cls._build_summary_message(
            plan=plan,
            status=status,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            blocked_tasks=blocked_tasks,
        )

        # Determine final AgentStatus
        if status == CollaborationStatus.COMPLETED:
            if merged_actions:
                agent_status = AgentStatus.ACTIONS_PROPOSED
            elif results_by_agent:
                agent_status = AgentStatus.DATA_RETURNED
            else:
                agent_status = AgentStatus.SUCCESS
        elif status == CollaborationStatus.PARTIAL:
            agent_status = AgentStatus.SUCCESS  # Partial success still returns useful data
        else:
            agent_status = AgentStatus.ERROR

        final_agent_result = AgentResult(
            status=agent_status,
            agent_code="orchestrator",
            message=message,
            data=aggregated_data,
            proposed_actions=merged_actions,
            suggestions=merged_suggestions,
            metadata={
                "collaboration_id": plan.collaboration_id,
                "collaboration_status": status.value,
                "participating_agents": plan.participating_agents,
            },
            handled_by="CollaborationAggregator",
        )

        return CollaborationResult(
            collaboration_id=plan.collaboration_id,
            status=status,
            participating_agents=plan.participating_agents,
            tasks=plan.tasks,
            aggregated_result=final_agent_result,
            error_summary=err_msg,
            metadata={
                "sessionId": session_id,
            },
        )

    @classmethod
    def _build_summary_message(
        cls,
        plan: CollaborationPlan,
        status: CollaborationStatus,
        completed_tasks: List[AgentTask],
        failed_tasks: List[AgentTask],
        blocked_tasks: List[AgentTask],
    ) -> str:
        """
        Format a clear, attributed markdown summary of the multi-agent execution.
        """
        lines = []

        if status == CollaborationStatus.COMPLETED:
            lines.append("### 🤝 Multi-Agent Collaboration Complete\n")
            lines.append(f"Successfully coordinated **{len(completed_tasks)} specialized agents** to fulfill your request:\n")
        elif status == CollaborationStatus.PARTIAL:
            lines.append("### ⚠️ Multi-Agent Collaboration Partially Complete\n")
            lines.append(
                f"Completed **{len(completed_tasks)} of {len(plan.tasks)} planned steps**. "
                "Some dependent actions were blocked due to upstream errors:\n"
            )
        else:
            lines.append("### ❌ Multi-Agent Collaboration Failed\n")
            lines.append("The requested multi-agent workflow encountered errors:\n")

        # Report completed tasks
        for task in completed_tasks:
            emoji = _AGENT_EMOJIS.get(task.agent_code, "🤖")
            title = _AGENT_TITLES.get(task.agent_code, task.agent_code.capitalize())
            summary = task.result.message if task.result else "Task completed."
            # Truncate summary to first paragraph or 200 chars for clean bullet formatting
            first_para = summary.split("\n\n")[0].strip()
            lines.append(f"{emoji} **{title}**\n   {first_para}\n")

        # Report failed tasks
        for task in failed_tasks:
            emoji = _AGENT_EMOJIS.get(task.agent_code, "🤖")
            err = task.error or "Unknown error"
            lines.append(f"❌ **{task.agent_code.capitalize()} Agent (Failed)**\n   Error: {err}\n")

        # Report blocked tasks
        for task in blocked_tasks:
            emoji = _AGENT_EMOJIS.get(task.agent_code, "🤖")
            lines.append(
                f"⏸️ **{task.agent_code.capitalize()} Agent (Blocked)**\n   "
                f"Waiting on failed prerequisite tasks: {', '.join(task.dependencies)}\n"
            )

        if status in (CollaborationStatus.COMPLETED, CollaborationStatus.PARTIAL):
            lines.append("---")
            lines.append("Review the aggregated results and proposed next-step actions below.")

        return "\n".join(lines)
