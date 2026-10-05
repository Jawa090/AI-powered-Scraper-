"""
agents/graph/tools/__init__.py
──────────────────────────────
LangGraph agent tools — @tool-decorated functions callable by the LLM.
"""

from agents.graph.tools.search import search_leads, count_leads, get_lead
from agents.graph.tools.catalog import list_sources, list_datasets
from agents.graph.tools.jobs import get_job_status
from agents.graph.tools.scrape import propose_scrape

READ_TOOLS = [search_leads, count_leads, get_lead, list_sources, list_datasets, get_job_status]
ALL_TOOLS = [*READ_TOOLS, propose_scrape]

__all__ = [
    "search_leads", "count_leads", "get_lead",
    "list_sources", "list_datasets",
    "get_job_status", "propose_scrape",
    "READ_TOOLS", "ALL_TOOLS",
]
