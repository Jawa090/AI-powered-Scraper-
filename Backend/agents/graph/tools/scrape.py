"""
agents/graph/tools/scrape.py
─────────────────────────────
Scrape proposal tool for the LangGraph agent.

This tool is NOT executed by the ToolNode — instead, when the LLM calls it,
the scrape_gate node intercepts and handles the logic (DB-first validation,
user confirmation via interrupt, then enqueue).
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
    location: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """Propose running a web scraper to fetch new data.

    IMPORTANT: You must call search_leads FIRST to check if the database
    already has enough data. Only propose a scrape when search_leads shows
    insufficient results.

    This tool does not execute immediately — it triggers a confirmation
    flow where the user can approve, modify, or reject the scrape.

    Args:
        source: Scraper source ID. Must be one of: "bonfire", "dasny", "jwiz", "nyscr".
        category: Industry or trade to search for (e.g. "plumbing", "construction").
        location: Geographic target (e.g. "Dallas", "New York").
        limit: Number of records to target (default 20, max 200).

    Returns:
        Dict confirming the proposal was registered.
    """
    # This function body is a placeholder — scrape_gate handles the actual logic.
    # If this somehow runs via ToolNode, return a safe message.
    return {
        "status": "proposal_registered",
        "source": source,
        "category": category,
        "location": location,
        "limit": min(max(1, limit), 200),
        "message": "Scrape proposal registered. Awaiting confirmation.",
    }
