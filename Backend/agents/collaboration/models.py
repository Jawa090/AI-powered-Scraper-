"""
agents/collaboration/models.py
───────────────────────────────
Layer 12: Multi-Agent Collaboration Contracts & Data Models.

Defines typed, auditable contracts for multi-agent workflows:
  - CollaborationStatus (lifecycle state of collaboration)
  - TaskStatus          (lifecycle state of individual agent tasks)
  - AgentTask           (a single task assigned to a specialized agent)
  - CollaborationPlan   (deterministic DAG of agent tasks)
  - CollaborationContext (controlled, sanitized shared context)
  - CollaborationResult (aggregated outcome of a multi-agent workflow)

Safety & Architectural Principles:
  - Strict typing and serialisability.
  - Whitelisted agents only.
  - Sanitized context propagation (no DB secrets, passwords, raw ORM pointers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from agents.base import AgentResult, AgentStatus, ProposedAction

# Whitelist of allowed specialized agent codes
APPROVED_AGENT_CODES = frozenset({"sales", "data", "research", "email", "growth"})
MAX_COLLABORATION_STEPS = 5


# ---------------------------------------------------------------------------
# Status Enums
# ---------------------------------------------------------------------------

class CollaborationStatus(str, Enum):
    PLANNED   = "PLANNED"
    RUNNING   = "RUNNING"
    WAITING   = "WAITING"
    COMPLETED = "COMPLETED"
    PARTIAL   = "PARTIAL"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    SKIPPED   = "SKIPPED"
    BLOCKED   = "BLOCKED"


# ---------------------------------------------------------------------------
# AgentTask Contract
# ---------------------------------------------------------------------------

@dataclass
class AgentTask:
    """
    An explicit, bounded task assigned to a specialized agent in a collaboration plan.
    """
    task_id: str
    agent_code: str
    purpose: str
    input_context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # list of task_ids
    execution_order: int = 1
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[AgentResult] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Enforce agent whitelist
        code = (self.agent_code or "").strip().lower()
        if code not in APPROVED_AGENT_CODES:
            raise ValueError(
                f"Invalid agent_code '{self.agent_code}'. Must be one of: {sorted(APPROVED_AGENT_CODES)}"
            )
        self.agent_code = code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "taskId": self.task_id,
            "agentCode": self.agent_code,
            "purpose": self.purpose,
            "inputContext": self.input_context,
            "dependencies": self.dependencies,
            "executionOrder": self.execution_order,
            "status": self.status.value,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# CollaborationPlan Contract
# ---------------------------------------------------------------------------

@dataclass
class CollaborationPlan:
    """
    A deterministic, bounded plan containing ordered agent tasks and dependencies.
    """
    collaboration_id: str = field(default_factory=lambda: f"collab-{uuid.uuid4().hex[:12]}")
    original_request: str = ""
    normalized_query: Optional[Dict[str, Any]] = None
    tasks: List[AgentTask] = field(default_factory=list)
    status: CollaborationStatus = CollaborationStatus.PLANNED
    max_steps: int = MAX_COLLABORATION_STEPS
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_multi_agent(self) -> bool:
        """True if the plan requires more than one agent."""
        distinct_agents = {t.agent_code for t in self.tasks}
        return len(self.tasks) > 1 or len(distinct_agents) > 1

    @property
    def participating_agents(self) -> List[str]:
        """Ordered list of distinct participating agent codes."""
        seen = []
        for t in self.tasks:
            if t.agent_code not in seen:
                seen.append(t.agent_code)
        return seen

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def validate(self) -> None:
        """
        Validate plan boundaries, task counts, agent whitelists, and acyclicity.
        Raises ValueError on validation failure.
        """
        if len(self.tasks) > self.max_steps:
            raise ValueError(
                f"Collaboration plan exceeds maximum allowed steps ({len(self.tasks)} > {self.max_steps})"
            )

        task_ids = {t.task_id for t in self.tasks}
        if len(task_ids) != len(self.tasks):
            raise ValueError("Duplicate task IDs found in collaboration plan")

        # Dependency & DAG cycle detection
        adj: Dict[str, List[str]] = {t.task_id: [] for t in self.tasks}
        for task in self.tasks:
            for dep in task.dependencies:
                if dep not in task_ids:
                    raise ValueError(f"Task '{task.task_id}' depends on non-existent task '{dep}'")
                adj[dep].append(task.task_id)

        # Topological sort / cycle detection (Kahn's algorithm)
        in_degree = {t.task_id: len(t.dependencies) for t in self.tasks}
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            curr = queue.pop(0)
            visited_count += 1
            for neighbor in adj.get(curr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(self.tasks):
            raise ValueError("Cyclic dependency detected in collaboration plan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collaborationId": self.collaboration_id,
            "originalRequest": self.original_request,
            "normalizedQuery": self.normalized_query,
            "tasks": [t.to_dict() for t in self.tasks],
            "status": self.status.value,
            "maxSteps": self.max_steps,
            "isMultiAgent": self.is_multi_agent,
            "participatingAgents": self.participating_agents,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# CollaborationContext Contract
# ---------------------------------------------------------------------------

_FORBIDDEN_CONTEXT_KEYS = frozenset({
    "password", "secret", "token", "connection_string", "db_uri",
    "credentials", "api_key", "private_key", "raw_sql", "session_maker"
})


@dataclass
class CollaborationContext:
    """
    Controlled, shared context object passed during multi-agent execution.
    Strictly sanitizes data to prevent exposing secrets, credentials, or raw ORM handles.
    """
    collaboration_id: str
    session_id: str
    user_id: str = "usr-ahmed"
    department_id: str = "dept-sales-1"
    raw_message: str = ""
    normalized_query: Optional[Dict[str, Any]] = None
    current_task: Optional[AgentTask] = None
    previous_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def sanitize(self) -> None:
        """Strip any unsafe or secret keys from metadata and previous results."""
        def _clean_dict(d: Dict[str, Any]) -> Dict[str, Any]:
            cleaned = {}
            for k, v in d.items():
                if any(forbidden in k.lower() for forbidden in _FORBIDDEN_CONTEXT_KEYS):
                    continue
                if isinstance(v, dict):
                    cleaned[k] = _clean_dict(v)
                elif isinstance(v, list):
                    cleaned[k] = [_clean_dict(item) if isinstance(item, dict) else item for item in v]
                else:
                    cleaned[k] = v
            return cleaned

        self.metadata = _clean_dict(self.metadata)
        self.previous_results = _clean_dict(self.previous_results)

    def to_dict(self) -> Dict[str, Any]:
        self.sanitize()
        return {
            "collaborationId": self.collaboration_id,
            "sessionId": self.session_id,
            "userId": self.user_id,
            "departmentId": self.department_id,
            "rawMessage": self.raw_message,
            "normalizedQuery": self.normalized_query,
            "currentTaskId": self.current_task.task_id if self.current_task else None,
            "previousResults": self.previous_results,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# CollaborationResult Contract
# ---------------------------------------------------------------------------

@dataclass
class CollaborationResult:
    """
    Final output of a multi-agent collaboration run.
    Wraps individual task outcomes and provides an aggregated AgentResult.
    """
    collaboration_id: str
    status: CollaborationStatus
    participating_agents: List[str]
    tasks: List[AgentTask]
    aggregated_result: AgentResult
    error_summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collaborationId": self.collaboration_id,
            "status": self.status.value,
            "participatingAgents": self.participating_agents,
            "tasks": [t.to_dict() for t in self.tasks],
            "aggregatedResult": self.aggregated_result.to_dict(),
            "errorSummary": self.error_summary,
            "metadata": self.metadata,
        }
