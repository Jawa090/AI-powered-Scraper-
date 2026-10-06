"""
agents/graph/tools/scrape.py
─────────────────────────────
Scrape proposal schema tool for the LangGraph agent.
Complies with Phase P11.5.

NOTE: This tool is NOT executed by ToolNode. Calls to propose_scrape are intercepted
by the graph's route_after_agent conditional edge and routed directly to validate_proposal.
"""

from __future__ import annotations

import logging
from typing import Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def propose_scrape(
    source: str,
    category: Optional[str] = None,
    city: Optional[str] = None,
    us_state: Optional[str] = None,
    quantity: int = 20,
) -> dict:
    """Propose running a web scraper to collect new leads or contracts.

    IMPORTANT: You MUST call search_leads FIRST to check if verified data already
    exists in the database. Only call propose_scrape when search_leads returns
    insufficient results.

    This tool triggers the user confirmation flow before any scraping job is enqueued.

    Args:
        source: Scraper source ID (e.g. "bonfire", "dasny", "jwiz", "nyscr").
        category: Industry, trade, or keyword for the scrape.
        city: Geographic target city (e.g. "Dallas", "New York").
        us_state: Two-letter US state code (e.g. "TX", "NY").
        quantity: Desired number of records to target (1-1000; default 20).

    Returns:
        Dict confirming proposal registration.
    """
    # Schema-only declaration. The validate_proposal node intercepts this tool call.
    return {
        "status": "proposal_registered",
        "source": source,
        "category": category,
        "city": city,
        "us_state": us_state,
        "quantity": quantity,
        "message": "Scrape proposal submitted for validation and user confirmation.",
    }
