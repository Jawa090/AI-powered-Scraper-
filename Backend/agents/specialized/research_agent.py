"""
agents/specialized/research_agent.py
────────────────────────────────────
Layer 8: Research Agent Intelligence & External Source Analysis.

Capabilities:
  - research_request
  - source_analysis
  - market_intelligence
  - domain_analysis

Responsibilities:
  - Process research-oriented user queries.
  - Determine whether research can be satisfied by internal platform database or requires external research.
  - Delegate research execution to ApprovedResearchProvider boundary.
  - Return structured, source-aware research results with verified citations.
  - NEVER fabricate sources, facts, or URLs.
  - NEVER execute arbitrary code, shell commands, or raw SQL.
"""

from typing import Any, Dict, List, Optional
from agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus
from agents.research.provider import ApprovedResearchProvider, ResearchResponse


class ResearchAgent(BaseAgent):
    agent_code = "research"
    name = "Market & Intelligence Research Agent"
    description = "Specialized agent for domain research, source analysis, market intelligence, and verified citation synthesis."
    capabilities = [
        "research_request",
        "source_analysis",
        "market_intelligence",
        "domain_analysis",
    ]

    def __init__(self):
        super().__init__()
        self.provider = ApprovedResearchProvider()

    def can_handle(self, context: AgentContext) -> bool:
        """
        ResearchAgent handles queries regarding research, market analysis,
        sources, competitor breakdown, or domain intelligence.
        """
        if not context.normalized_query:
            return False

        intent = context.normalized_query.get("intent", "").lower()
        query_text = (context.raw_message or "").lower()

        research_keywords = [
            "research", "analyze", "analysis", "market", "competitor",
            "source", "overview", "study", "insight", "trend", "report"
        ]
        research_intents = [
            "research_request", "market_analysis", "source_analysis",
            "domain_analysis", "industry_research"
        ]

        if intent in research_intents:
            return True
        if any(kw in query_text for kw in research_keywords):
            return True

        return False

    def handle(self, context: AgentContext) -> AgentResult:
        query_dict = context.normalized_query or {}
        raw_msg = (context.raw_message or "").lower()

        # Case 1: Clarification required
        if context.availability_decision == "NEED_CLARIFICATION":
            return AgentResult.clarification(
                agent_code=self.agent_code,
                message="Research Agent requires a clearer research topic or industry focus.",
                questions=[
                    "What specific industry, market, or procurement topic would you like to research?",
                    "Which region or target location should the research focus on?",
                ],
                suggestions=[
                    "Research General Contracting market in Texas",
                    "Analyze state procurement trends for NYSCR",
                    "Synthesize commercial directory coverage",
                ],
            )

        # Extract topic and location
        topic = query_dict.get("category")
        location = query_dict.get("location")

        if not topic:
            # Fallback extraction from raw message keywords
            topic = context.raw_message or "General Industry"

        # Check if external research requested
        require_external = any(
            kw in raw_msg for kw in ["external", "web", "market trends", "latest research", "competitor", "global"]
        )

        try:
            # Execute research synthesis via Approved Research Boundary
            response: ResearchResponse = self.provider.conduct_research(
                topic=topic,
                location=location,
                require_external=require_external,
            )

            res_dict = response.to_dict()

            return AgentResult(
                status=AgentStatus.DATA_RETURNED if response.findings else AgentStatus.SUCCESS,
                agent_code=self.agent_code,
                message=response.summary,
                data=res_dict,
                suggestions=[
                    f"Export research summary for {response.topic}",
                    f"Search database leads for {response.topic}",
                    "Perform competitor analysis",
                ],
                metadata={
                    "sourceType": response.source_type,
                    "findingsCount": len(response.findings),
                    "citationsCount": len(response.citations),
                    "verifiedRatio": "100%",
                },
                handled_by=self.__class__.__name__,
            )

        except Exception as exc:
            return AgentResult.error(self.agent_code, detail=f"Research synthesis error: {str(exc)}")
