"""
agents/graph/tools/__init__.py
──────────────────────────────
LangGraph agent tools registry.
Complies with Phase P11.5.
"""

from agents.graph.tools.rag import knowledge_base_status, search_knowledge_base
from agents.graph.tools.search import search_leads, count_leads, get_lead
from agents.graph.tools.catalog import list_sources, list_datasets, get_dataset_leads
from agents.graph.tools.jobs import get_job_status, resume_job, cancel_job
from agents.graph.tools.scrape import propose_scrape

READ_TOOLS = [
    knowledge_base_status,
    search_knowledge_base,
    search_leads,
    count_leads,
    get_lead,
    list_sources,
    list_datasets,
    get_dataset_leads,
    get_job_status,
    resume_job,
    cancel_job,
]

ALL_TOOLS = [
    *READ_TOOLS,
    propose_scrape,
]

__all__ = [
    "knowledge_base_status",
    "search_knowledge_base",
    "search_leads",
    "count_leads",
    "get_lead",
    "list_sources",
    "list_datasets",
    "get_dataset_leads",
    "get_job_status",
    "resume_job",
    "cancel_job",
    "propose_scrape",
    "READ_TOOLS",
    "ALL_TOOLS",
]
