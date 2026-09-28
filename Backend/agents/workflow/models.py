"""
agents/workflow/models.py
─────────────────────────
Structured Internal Workflow Models for Phase 2B.
Defines Plan, PlanStep, ToolCall, AgentResult, and WorkflowResult.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from agents.intent.models import StructuredIntent


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class WorkflowStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass
class ToolCall:
    """
    Representation of an authorized tool call to be performed by an agent.
    Never created directly by LLM.
    """
    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    authorized_by: str = "WorkflowPlanner"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlanStep:
    """
    A discrete step in an execution plan.
    """
    step_id: str
    agent: str  # "database", "scraper", "orchestrator", "sales", etc.
    action: str  # "search_leads", "create_job", "get_status", etc.
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class WorkflowPlan:
    """
    The validated plan constructed by the WorkflowPlanner.
    """
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: Optional[Dict[str, Any]] = None
    steps: List[PlanStep] = field(default_factory=list)
    route: str = "general"  # database_only, scraper_only, combined, job_status, dataset, general, unsupported

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent": self.intent,
            "steps": [s.to_dict() for s in self.steps],
            "route": self.route,
        }


@dataclass
class AgentResult:
    """
    Structured outcome of an agent's execution of a plan step.
    """
    agent: str
    action: str
    success: bool
    status: StepStatus
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class WorkflowResult:
    """
    Final aggregated result of the complete workflow execution.
    """
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: WorkflowStatus = WorkflowStatus.PENDING
    plan_id: Optional[str] = None
    steps_executed: List[PlanStep] = field(default_factory=list)
    agent_results: Dict[str, Any] = field(default_factory=dict)
    aggregated_data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    is_partial: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "plan_id": self.plan_id,
            "steps_executed": [s.to_dict() for s in self.steps_executed],
            "agent_results": self.agent_results,
            "aggregated_data": self.aggregated_data,
            "errors": self.errors,
            "is_partial": self.is_partial,
        }


@dataclass
class CollaborationContext:
    """
    Structured context tracking multi-agent workflow collaboration (Phase 2F).
    Holds lifecycle state, agent participation, dependency outcomes, and intermediate results.
    """
    collaboration_id: str = field(default_factory=lambda: f"collab-{uuid.uuid4().hex[:12]}")
    original_request: str = ""
    intent: Optional[Dict[str, Any]] = None
    workflow_plan: Optional[WorkflowPlan] = None
    participating_agents: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    blocked_steps: List[str] = field(default_factory=list)
    intermediate_results: Dict[str, Any] = field(default_factory=dict)
    final_status: WorkflowStatus = WorkflowStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collaboration_id": self.collaboration_id,
            "original_request": self.original_request,
            "intent": self.intent,
            "workflow_plan": self.workflow_plan.to_dict() if self.workflow_plan else None,
            "participating_agents": self.participating_agents,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "blocked_steps": self.blocked_steps,
            "intermediate_results": self.intermediate_results,
            "final_status": self.final_status.value if isinstance(self.final_status, WorkflowStatus) else str(self.final_status),
        }

