"""
agents/research/__init__.py
────────────────────────────
Package for Layer 8 Controlled Research Boundary and Provider abstractions.
"""

from agents.research.provider import ApprovedResearchProvider, ResearchFinding, ResearchResponse

__all__ = [
    "ApprovedResearchProvider",
    "ResearchFinding",
    "ResearchResponse",
]
