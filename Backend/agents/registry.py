"""
agents/registry.py
──────────────────
Layer 6: Controlled Specialized Agent Registry & Selection Engine.

Rules:
  - Allow ONLY registered specialized agents.
  - Reject unknown agent IDs.
  - Prevent arbitrary Python module execution / arbitrary imports.
  - Provide deterministic agent selection based on request context.
"""

from typing import Any, Dict, List, Optional, Type
from agents.base import BaseAgent, AgentContext
from agents.specialized.sales_agent import SalesAgent
from agents.specialized.data_agent import DataAgent
from agents.specialized.research_agent import ResearchAgent
from agents.specialized.email_agent import EmailAgent
from agents.specialized.growth_agent import GrowthAgent
from agents.specialized.database_agent import DatabaseAgent
from agents.specialized.scraper_agent import ScraperAgent


class AgentRegistry:
    """
    Controlled registry mapping approved agent_code -> BaseAgent instance.
    Prevent execution of unapproved or arbitrary code.
    """

    def __init__(self):
        self._registry: Dict[str, BaseAgent] = {}
        self._register_default_agents()

    def _register_default_agents(self):
        """Auto-register the foundation specialized agents."""
        defaults = [
            SalesAgent(),
            DataAgent(),
            ResearchAgent(),
            EmailAgent(),
            GrowthAgent(),
            DatabaseAgent(),
            ScraperAgent(),
        ]
        for agent in defaults:
            self.register(agent)

    def register(self, agent: BaseAgent):
        """Register a BaseAgent instance."""
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"Cannot register object {agent}: must inherit BaseAgent.")
        
        code = agent.agent_code.strip().lower()
        if not code:
            raise ValueError(f"Agent class {agent.__class__.__name__} must define a non-empty agent_code.")
        
        self._registry[code] = agent

    def is_registered(self, agent_code: str) -> bool:
        """Check if agent_code is registered."""
        return agent_code.strip().lower() in self._registry

    def get(self, agent_code: str) -> BaseAgent:
        """
        Get registered agent instance by code.
        Raises ValueError if agent_code is unknown or unapproved.
        """
        code = agent_code.strip().lower()
        if code not in self._registry:
            raise ValueError(
                f"Unknown or unapproved agent_code: '{agent_code}'. "
                f"Approved agents are: {list(self._registry.keys())}."
            )
        return self._registry[code]

    def list_agents(self) -> List[Dict[str, Any]]:
        """List metadata for all registered agents."""
        return [agent.get_metadata() for agent in self._registry.values()]

    def select_agent(self, context: AgentContext) -> Optional[BaseAgent]:
        """
        Deterministic first-pass agent selection logic.

        Selection order:
          1. If context explicitly specifies an agent in metadata or request, validate & return it.
          2. Query-based evaluation using agent.can_handle(context).
          3. If no agent confidently handles the request: return None (trigger NEED_CLARIFICATION).
        """
        # Step 1: Explicit agent override in metadata
        requested_code = context.metadata.get("requested_agent")
        if requested_code and self.is_registered(requested_code):
            return self.get(requested_code)

        # Step 2: Evaluation order (deterministic prioritization)
        # Sales & Data take priority for business queries; then Email, Growth, Research
        priority_order = ["sales", "data", "email", "growth", "research"]
        
        for code in priority_order:
            if code in self._registry:
                agent = self._registry[code]
                if agent.can_handle(context):
                    return agent

        # Step 3: Check remaining registered agents
        for code, agent in self._registry.items():
            if code not in priority_order and agent.can_handle(context):
                return agent

        # Ambiguous / unhandled request
        return None


# Global singleton instance for platform use
agent_registry = AgentRegistry()
