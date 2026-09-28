"""
agents/specialized/__init__.py
───────────────────────────────
Package containing Foundation Specialized Agents for Layer 6:
  - SalesAgent
  - DataAgent
  - ResearchAgent
  - EmailAgent
  - GrowthAgent
"""

from agents.specialized.sales_agent import SalesAgent
from agents.specialized.data_agent import DataAgent
from agents.specialized.research_agent import ResearchAgent
from agents.specialized.email_agent import EmailAgent
from agents.specialized.growth_agent import GrowthAgent
from agents.specialized.database_agent import DatabaseAgent, database_agent
from agents.specialized.scraper_agent import ScraperAgent, scraper_agent

__all__ = [
    "SalesAgent",
    "DataAgent",
    "ResearchAgent",
    "EmailAgent",
    "GrowthAgent",
    "DatabaseAgent",
    "database_agent",
    "ScraperAgent",
    "scraper_agent",
]


