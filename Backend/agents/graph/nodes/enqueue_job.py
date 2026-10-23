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

from langchain_core.messages import ToolMessage, HumanMessage

from Database.controller import session_scope
from agents.graph.state import AgentState
from services.jobs import enqueue_scrape

logger = logging.getLogger(__name__)


def enqueue_job(state: AgentState) -> Dict[str, Any]:
    """
    Invokes enqueue_scrape in a session_scope and resolves the open propose_scrape tool call.
    """
    proposal = state.get("pending_proposal") or {}
    from agents.graph.nodes.gather_requirements import missing_requirements
    missing = missing_requirements(state.get('slots')) if state.get('request_intent') == 'records' else []
    if missing:
        return {'decision': 'CLARIFY', 'confirmed': False, 'pending_proposal': None,
            'requirements_met': False, 'missing_requirements': missing,
            'messages': [ToolMessage(content='Requirements incomplete: ' + '; '.join(missing),
                tool_call_id=proposal.get('tool_call_id', ''))]}
    from Database.search import SearchCriteria
    evidence = state.get('last_search') or {}
    criteria = SearchCriteria.from_slots(state.get('slots'))
    if not state.get('confirmed') or proposal.get('criteria_hash') != criteria.fingerprint() or evidence.get('turn_id') != state.get('turn_id') or evidence.get('sufficient') or evidence.get('error'):
        raise ValueError('Approved validated same-request search evidence is required')
    tool_call_id = proposal.get("tool_call_id", "")
    args = proposal.get("args") or {}

    source = proposal.get("source") or args.get("source", "")
    attempted = list(args.get("attempted_scrapers") or state.get("attempted_scrapers") or (state.get("slots") or {}).get("attempted_scrapers") or [])
    if source and source not in attempted:
        attempted.append(source)
    category = args.get("category")
    city = args.get("city") or (state.get("slots") or {}).get("city")
    us_state = args.get("us_state") or (state.get("slots") or {}).get("us_state")
    qty = args.get("quantity")
    if qty is None:
        qty=100
    # Location mapping
    location = None
    if city and us_state:
        location = f"{city}, {us_state}"
    elif city:
        location = city
    elif us_state:
        location = us_state

    # Scrapers search ONLY with the user-given keyword, never with aliases
    user_kw = (
        args.get("user_keyword")
        or (state.get("slots") or {}).get("user_keyword")
        or (category.split(",")[0].strip() if category else None)
    )
    scraper_keyword = user_kw or category
    params = {
        "keyword": scraper_keyword,
        "category": scraper_keyword,
        "city": city,
        "location": location,
        "us_state": us_state,
        "limit": max(100, qty),
        "attempted_scrapers": attempted,
    }

    try:
        with session_scope() as session:
            job, created = enqueue_scrape(
                session,
                user=state.get("user_id"),
                script_id=source,
                params=params,
                query_id=proposal.get('query_id') or state.get("query_id"),
                idempotency_key=proposal.get("id"),
            )
            from Database.models.query import Query
            confirmation = session.get(Query, state.get('query_id'))
            if confirmation:
                confirmation.job_id = job.id
                confirmation.parameters = {
                    **(confirmation.parameters or {}),
                    'attempted_scrapers': attempted,
                }
            orig_id = proposal.get('query_id')
            if orig_id and orig_id != state.get('query_id'):
                orig_q = session.get(Query, orig_id)
                if orig_q:
                    orig_q.job_id = job.id
                    orig_q.parameters = {
                        **(orig_q.parameters or {}),
                        'attempted_scrapers': attempted,
                    }
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
                "messages": [tool_msg, HumanMessage(content=state.get('user_text') or 'Approved this proposal.')],
                "active_job_id": job.id,
                "decision": decision,
                "pending_proposal": None,
                "intent_interpreted": True,
                "attempted_scrapers": attempted,
            }

    except Exception as e:
        logger.error("enqueue_job failed: %s", e, exc_info=True)
        err_msg = ToolMessage(
            content=json.dumps({"error": "The scrape could not be queued. Please retry."}),
            tool_call_id=tool_call_id,
        )
        return {
            "messages": [err_msg],
            "pending_proposal": None,
        }
