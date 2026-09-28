"""
agents/collaboration/__init__.py
─────────────────────────────────
Layer 12: Multi-Agent Collaboration & Orchestration Package.

Exports:
  - Models:
      CollaborationStatus, TaskStatus, AgentTask, CollaborationPlan,
      CollaborationContext, CollaborationResult, APPROVED_AGENT_CODES, MAX_COLLABORATION_STEPS
  - Planner:
      CollaborationPlanner
  - Engine:
      CollaborationEngine, collaboration_engine
  - Aggregator:
      CollaborationAggregator
"""

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
from agents.collaboration.planner import CollaborationPlanner
from agents.collaboration.aggregator import CollaborationAggregator
from agents.collaboration.engine import CollaborationEngine, collaboration_engine

__all__ = [
    "APPROVED_AGENT_CODES",
    "MAX_COLLABORATION_STEPS",
    "AgentTask",
    "CollaborationContext",
    "CollaborationPlan",
    "CollaborationResult",
    "CollaborationStatus",
    "TaskStatus",
    "CollaborationPlanner",
    "CollaborationAggregator",
    "CollaborationEngine",
    "collaboration_engine",
]
