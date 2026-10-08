"""
agents/graph/tools/scrape.py
─────────────────────────────
Scrape proposal schema tool for the LangGraph agent.
Complies with Phase P11.5.

NOTE: This tool is NOT executed by ToolNode. Calls to propose_scrape are intercepted
by the graph's route_after_agent conditional edge and routed directly to validate_proposal.
"""

import logging
from typing import Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def propose_scrape(
    source: str,
    quantity: Optional[int] = None,
) -> dict:
    """Propose running a web scraper to collect new leads or contracts.

    IMPORTANT: You MUST call search_leads FIRST to check if verified data already
    exists in the database. Only call propose_scrape when search_leads returns
    insufficient results.

    This tool triggers the user confirmation flow before any scraping job is enqueued.

    Args:
        source: Scraper source ID (e.g. "bonfire", "dasny", "jwiz", "nyscr").
        quantity: Missing number of matching records to collect (1-1000).

    Category, city, state, record type, and required fields come from the exact
    validated search in this turn. Do not change filters in a proposal. To change
    or remove a filter, call search_leads again with the correct criteria first.

    Returns:
        Dict confirming proposal registration.
    """
    # Schema-only declaration. The validate_proposal node intercepts this tool call.
    return {
        "status": "proposal_registered",
        "source": source,
        "quantity": quantity,
        "message": "Scrape proposal submitted for validation and user confirmation.",
    }
