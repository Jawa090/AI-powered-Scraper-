"""
agents/base.py
──────────────
Layer 6: Common Agent Contract.

Defines:
  - AgentStatus      (enum of result statuses)
  - AgentAction      (a proposed action produced by an agent)
  - AgentResult      (structured result every agent must return)
  - AgentContext     (serialisable context passed into every agent)
  - BaseAgent        (abstract base class every specialized agent inherits)

Design principles:
  - Agents are pure business-logic coordinators.
  - Agents MUST NOT perform raw SQL or direct DB access.
  - Agents MUST NOT call scraper scripts directly.
  - Agents use shared Services / Repositories / Job infrastructure.
  - Every agent result is serialisable and auditable.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Agent Status Enum
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    SUCCESS              = "success"
    NEED_CLARIFICATION   = "need_clarification"
    UNSUPPORTED          = "unsupported"
    EXECUTION_REQUIRED   = "execution_required"
    DATA_RETURNED        = "data_returned"
    ACTIONS_PROPOSED     = "actions_proposed"
    ERROR                = "error"


# ---------------------------------------------------------------------------
# AgentAction — a structured action proposed by an agent
# ---------------------------------------------------------------------------

@dataclass
class ProposedAction:
    """
    A concrete next-step action an agent proposes.
    Actions are NEVER automatically executed — they require orchestrator
    confirmation and go through approved execution infrastructure.
    """
    action_type: str          # e.g. "scrape_trigger", "email_draft", "lead_search"
    label: str                # Human-readable label shown in UI
    parameters: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = True
    safe_to_auto_execute: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actionType": self.action_type,
            "action_type": self.action_type,
            "label": self.label,
            "parameters": self.parameters,
            "requiresConfirmation": self.requires_confirmation,
            "safeToAutoExecute": self.safe_to_auto_execute,
        }


# ---------------------------------------------------------------------------
# AgentResult — every agent returns one of these
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """
    Unified result contract returned by every specialized agent.

    Compatible with the frontend BotChatResponse shape when serialised.
    """
    status: AgentStatus
    agent_code: str
    message: str

    # Optional structured payload
    data: Optional[Dict[str, Any]] = None
    proposed_actions: List[ProposedAction] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    clarification_questions: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    handled_by: Optional[str] = None     # name of the specialized agent class

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        return {
            "status": self.status.value,
            "agentCode": self.agent_code,
            "message": self.message,
            "data": self.data,
            "proposedActions": [a.to_dict() for a in self.proposed_actions],
            "suggestions": self.suggestions,
            "clarificationQuestions": self.clarification_questions,
            "metadata": self.metadata,
            "handledBy": self.handled_by,
        }

    @classmethod
    def unsupported(cls, agent_code: str, reason: str) -> "AgentResult":
        return cls(
            status=AgentStatus.UNSUPPORTED,
            agent_code=agent_code,
            message=reason,
            handled_by=agent_code,
        )

    @classmethod
    def clarification(cls, agent_code: str, message: str, questions: List[str], suggestions: List[str] | None = None) -> "AgentResult":
        return cls(
            status=AgentStatus.NEED_CLARIFICATION,
            agent_code=agent_code,
            message=message,
            clarification_questions=questions,
            suggestions=suggestions or [],
            handled_by=agent_code,
        )

    @classmethod
    def error(cls, agent_code: str, detail: str) -> "AgentResult":
        return cls(
            status=AgentStatus.ERROR,
            agent_code=agent_code,
            message=f"An error occurred: {detail}",
            handled_by=agent_code,
        )


# ---------------------------------------------------------------------------
# AgentContext — serialisable context passed into every agent
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    """
    Controlled, serialisable context object for a single agent execution turn.
    Does NOT copy entire DB records into memory — only IDs and parsed data.
    """
    session_id: str
    user_id: str = "usr-ahmed"
    department_id: str = "dept-sales-1"

    # From Layer 5 query understanding
    normalized_query: Optional[Dict[str, Any]] = None   # NormalizedQuery.to_dict()
    availability_decision: Optional[str] = None          # "USE_DATABASE" | "NEED_FETCH" | "NEED_CLARIFICATION"
    availability_reason: Optional[str] = None
    records_available: int = 0

    # Current session requirement state (from frontend)
    current_requirement: Optional[Dict[str, Any]] = None

    # Raw user message for fallback
    raw_message: str = ""

    # Additional metadata (e.g. from previous turns)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "userId": self.user_id,
            "departmentId": self.department_id,
            "normalizedQuery": self.normalized_query,
            "availabilityDecision": self.availability_decision,
            "availabilityReason": self.availability_reason,
            "recordsAvailable": self.records_available,
            "currentRequirement": self.current_requirement,
            "rawMessage": self.raw_message,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# BaseAgent — abstract base class
# ---------------------------------------------------------------------------

class BaseAgent(abc.ABC):
    """
    Abstract base for all specialized agents.

    Subclasses must implement:
      - agent_code      (str class attribute)
      - name            (str class attribute)
      - description     (str class attribute)
      - capabilities    (List[str] class attribute)
      - can_handle()    (returns True if this agent should handle the request)
      - handle()        (returns AgentResult)

    Agents MUST NOT:
      - Call scraper scripts directly.
      - Perform raw SQL.
      - Access os.system / subprocess.
      - Send real emails.
      - Auto-execute any action without going through approved services.
    """

    # Subclass must declare these as class attributes
    agent_code: str = ""
    name: str = ""
    description: str = ""
    capabilities: List[str] = []

    @abc.abstractmethod
    def can_handle(self, context: AgentContext) -> bool:
        """
        Return True if this agent is appropriate for the given context.
        Must be deterministic and fast (no I/O).
        """

    @abc.abstractmethod
    def handle(self, context: AgentContext) -> AgentResult:
        """
        Process the request and return a structured AgentResult.
        May read from services/repositories using a fresh SessionLocal context
        if DB data is needed.
        """

    def get_metadata(self) -> Dict[str, Any]:
        """Return agent metadata for registry/admin purposes."""
        return {
            "agentCode": self.agent_code,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
        }
