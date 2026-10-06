"""
agents/graph/nodes/validate_proposal.py
───────────────────────────────────────
Validation node for scraper proposals.
Complies with Phase P11.4 validate_proposal.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import ToolMessage
from sqlalchemy import func, select

from Database.controller import session_scope
from Database.models.job import Job
from agents.graph.state import AgentState
from scrappers.controller import check_ready, get_meta, scraper_ids
from settings import settings

logger = logging.getLogger(__name__)


def validate_proposal(state: AgentState) -> Dict[str, Any]:
    """
    Validates a propose_scrape tool call preconditions before requesting confirmation.
    Non-propose_scrape tool calls in the same turn are answered with a refusal message.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_ai = messages[-1]
    tool_calls = getattr(last_ai, "tool_calls", None) or []
    if not tool_calls:
        return {}

    propose_call = None
    other_msgs: List[ToolMessage] = []

    for call in tool_calls:
        if call.get("name") == "propose_scrape":
            propose_call = call
        else:
            other_msgs.append(
                ToolMessage(
                    content="Not executed: call propose_scrape alone.",
                    tool_call_id=call.get("id", ""),
                )
            )

    if not propose_call:
        return {"messages": other_msgs}

    call_id = propose_call.get("id", "")
    args = propose_call.get("args") or {}

    source = args.get("source", "").lower().strip()
    category = args.get("category")
    city = args.get("city")
    us_state = args.get("us_state")
    quantity = args.get("quantity", 20)

    # 1. Check last_search preconditions
    last_search = state.get("last_search") or {}
    turn_id = state.get("turn_id", "")

    refusal_reason: Optional[str] = None

    if not last_search:
        refusal_reason = "No database search was performed. You must run search_leads before proposing a scrape."
    elif last_search.get("turn_id") != turn_id:
        refusal_reason = "Search results are from a previous turn. You must run search_leads first for this turn."
    elif last_search.get("sufficient", False) is True:
        refusal_reason = "The database already contains sufficient verified leads matching the criteria."

    # 2. Check source validity and readiness
    meta = None
    if not refusal_reason:
        valid_ids = scraper_ids()
        if source not in valid_ids:
            refusal_reason = f"Scraper source '{source}' is unknown. Supported sources: {sorted(valid_ids)}."
        else:
            meta = get_meta(source)
            ready, reason = check_ready(source)
            if not ready:
                refusal_reason = f"Scraper '{source}' is not currently ready: {reason}."

    # 3. Check parameter support against meta.supports
    if not refusal_reason and meta:
        supports = meta.supports or []
        if (city or us_state) and "location" not in supports:
            refusal_reason = f"Scraper '{source}' does not support location filtering. Supported: {supports}."

    # 4. Check hourly rate limit
    if not refusal_reason:
        user_id = state.get("user_id")
        if user_id:
            try:
                from datetime import datetime, timedelta, timezone

                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                with session_scope() as session:
                    count = session.scalar(
                        select(func.count(Job.id))
                        .where(Job.created_by == user_id)
                        .where(Job.created_at >= one_hour_ago)
                    ) or 0
                    max_scrapes = getattr(settings, "SCRAPES_PER_HOUR", 10)
                    if count >= max_scrapes:
                        refusal_reason = f"Hourly scrape rate limit of {max_scrapes} reached. Please try later."
            except Exception as e:
                logger.warning("Error checking scrape rate limit: %s", e)

    # Refusal handling: close tool call with refusal ToolMessage
    if refusal_reason:
        refusal_msg = ToolMessage(
            content=f"Proposal refused: {refusal_reason}",
            tool_call_id=call_id,
        )
        return {
            "messages": [refusal_msg, *other_msgs],
            "pending_proposal": None,
        }

    # Success: build pending_proposal (tool call stays open for user confirmation)
    normalized_args = {
        "source": source,
        "category": category,
        "city": city,
        "us_state": us_state,
        "quantity": quantity,
    }
    proposal_seed = f"{state.get('session_id')}:{state.get('query_id')}:{json.dumps(normalized_args, sort_keys=True)}"
    proposal_id = hashlib.sha256(proposal_seed.encode()).hexdigest()

    pending_proposal = {
        "id": proposal_id,
        "source": source,
        "args": normalized_args,
        "missing": [],
        "tool_call_id": call_id,
        "question": "",
    }

    return {
        "messages": other_msgs,
        "pending_proposal": pending_proposal,
    }
