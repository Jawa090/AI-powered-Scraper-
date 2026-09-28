"""
agents/__init__.py
──────────────────
Agent orchestration package.

Public API::

    from agents import AgentOrchestrator, agent_orchestrator
"""

from agents.orchestrator import AgentOrchestrator, agent_orchestrator
from agents.query import NormalizedQuery, QueryParser
from agents.decisions import DataAvailabilityChecker, DataAvailabilityResult, DecisionType

__all__ = [
    "AgentOrchestrator",
    "agent_orchestrator",
    "NormalizedQuery",
    "QueryParser",
    "DataAvailabilityChecker",
    "DataAvailabilityResult",
    "DecisionType",
]
