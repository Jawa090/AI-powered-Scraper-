"""
agents/graph/nodes/enqueue_job.py
─────────────────────────────────
Job enqueueing node for confirmed scrape proposals.
Complies with Phase P11.4 enqueue_job and P7.1.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import ToolMessage

from Database.controller import session_scope
from agents.graph.state import AgentState
from services.jobs import enqueue_scrape

logger = logging.getLogger(__name__)


def enqueue_job(state: AgentState) -> Dict[str, Any]:
    """
    Invokes enqueue_scrape in a session_scope and resolves the open propose_scrape tool call.
    """
    proposal = state.get("pending_proposal") or {}
    tool_call_id = proposal.get("tool_call_id", "")
    args = proposal.get("args") or {}

    source = proposal.get("source") or args.get("source", "")
    category = args.get("category")
    city = args.get("city")
    us_state = args.get("us_state")
    qty = args.get("quantity", 20)

    # Location mapping
    location = None
    if city and us_state:
        location = f"{city}, {us_state}"
    elif city:
        location = city
    elif us_state:
        location = us_state

    # Map category -> keyword/category and location for scrapers
    params = {
        "keyword": category,
        "category": category,
        "location": location,
        "city": city,
        "us_state": us_state,
        "limit": min(max(1, qty), 200),
    }

    try:
        with session_scope() as session:
            job, created = enqueue_scrape(
                session,
                user=state.get("user_id"),
                script_id=source,
                params=params,
                query_id=state.get("query_id"),
                idempotency_key=proposal.get("id"),
            )
            session.commit()

            tool_msg = ToolMessage(
                content=json.dumps({
                    "job_id": job.id,
                    "status": job.status,
                    "created": created,
                    "message": f"Scrape job '{job.name}' ({job.id}) queued successfully.",
                }),
                tool_call_id=tool_call_id,
            )

            last_search = state.get("last_search") or {}
            total_found = last_search.get("total", 0)
            decision = "PARTIAL" if total_found > 0 else "SCRAPER"

            return {
                "messages": [tool_msg],
                "active_job_id": job.id,
                "decision": decision,
                "pending_proposal": None,
            }

    except Exception as e:
        logger.error("enqueue_job failed: %s", e, exc_info=True)
        err_msg = ToolMessage(
            content=json.dumps({"error": f"Failed to enqueue scrape: {str(e)}"}),
            tool_call_id=tool_call_id,
        )
        return {
            "messages": [err_msg],
            "pending_proposal": None,
        }
