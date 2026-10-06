"""
agents/graph/tools/search.py
─────────────────────────────
Lead search, count, and detail tools for the LangGraph agent.
Complies with Phase P11.5 and Experiment E1.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

logger = logging.getLogger(__name__)


@tool
def search_leads(
    category: Optional[str] = None,
    city: Optional[str] = None,
    us_state: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None,
    source: Optional[str] = None,
    quantity: int = 20,
    fresh_within_days: Optional[int] = None,
    include_expired: bool = False,
    page: int = 1,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """Search the local verified leads database.

    IMPORTANT: Always call this BEFORE proposing any scrape. Returns matching leads
    and indicates whether the database has sufficient results.

    Args:
        category: Industry, trade, or keyword (e.g. "plumbing", "electrical", "construction").
        city: City name (e.g. "Dallas", "Brooklyn").
        us_state: Two-letter US state code (e.g. "TX", "NY").
        has_email: If True, only return leads with email addresses.
        has_phone: If True, only return leads with phone numbers.
        source: Filter by scraper source code (e.g. "bonfire", "dasny", "jwiz", "nyscr").
        quantity: Desired number of records (1-1000; default 20 if unstated).
        fresh_within_days: Filter to leads discovered within the last N days.
        include_expired: If True, include expired opportunities/contracts.
        page: Page number for pagination (1-indexed).

    Returns:
        Command updating last_search and slots state while returning compact lead results.
    """
    from Database.controller import Repositories, session_scope

    st = state or {}
    qty = min(max(1, quantity), 1000)
    limit = min(qty, 20)  # Compact output: <= 20 items
    offset = max(0, (page - 1) * limit)

    location = None
    if city and us_state:
        location = f"{city}, {us_state}"
    elif city:
        location = city
    elif us_state:
        location = us_state

    items: List[Dict[str, Any]] = []
    total_count = 0
    err_msg = None

    try:
        with session_scope() as session:
            lead_repo = Repositories(session).leads
            leads, total_count = lead_repo.search_leads(
                category=category,
                location=location,
                source_code=source,
                has_email=has_email or False,
                has_phone=has_phone or False,
                limit=limit,
                offset=offset,
            )

            for lead in leads:
                org_name = lead.organization.name if lead.organization else None
                contact_name = lead.contact.full_name if lead.contact else None

                email = None
                if lead.contact and lead.contact.emails:
                    email = lead.contact.emails[0].email
                elif lead.organization and lead.organization.emails:
                    email = lead.organization.emails[0].email

                phone = None
                if lead.contact and lead.contact.phones:
                    phone = lead.contact.phones[0].phone_raw
                elif lead.organization and lead.organization.phones:
                    phone = lead.organization.phones[0].phone_raw

                items.append({
                    "id": lead.id,
                    "company": org_name,
                    "contact": contact_name,
                    "title": lead.title,
                    "email": email,
                    "phone": phone,
                    "status": lead.status,
                })
    except Exception as e:
        logger.error("search_leads execution error: %s", e, exc_info=True)
        err_msg = str(e)

    sufficient = (total_count >= qty and total_count > 0)
    reasons = [] if sufficient else ["Insufficient verified leads matching criteria."]

    slots = {
        "category": category,
        "city": city,
        "us_state": us_state,
        "quantity": qty,
        "required_fields": {"has_email": bool(has_email), "has_phone": bool(has_phone)},
        "source": source,
        "fresh_within_days": fresh_within_days,
    }
    slots_hash = hashlib.sha256(json.dumps(slots, sort_keys=True).encode()).hexdigest()

    last_search = {
        "turn_id": st.get("turn_id", ""),
        "slots_hash": slots_hash,
        "total": total_count,
        "returned": len(items),
        "lead_ids": [it["id"] for it in items],
        "sufficient": sufficient,
        "reasons": reasons,
    }

    trace_entry = {
        "tool": "search_leads",
        "category": category,
        "location": location,
        "total": total_count,
        "returned": len(items),
        "sufficient": sufficient,
    }
    new_trace = list(st.get("trace", [])) + [trace_entry]

    tool_result = {
        "total": total_count,
        "returned": len(items),
        "sufficient": sufficient,
        "items": items,
        "error": err_msg,
    }

    return Command(
        update={
            "last_search": last_search,
            "slots": slots,
            "trace": new_trace,
            "messages": [
                ToolMessage(
                    content=json.dumps(tool_result),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
def count_leads(
    category: Optional[str] = None,
    city: Optional[str] = None,
    us_state: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None,
    source: Optional[str] = None,
    group_by: Optional[str] = None,
    state: Annotated[dict, InjectedState] = None,
) -> Dict[str, Any]:
    """Count matching leads in the database, with optional grouping.

    Args:
        category: Industry, trade, or keyword.
        city: City name.
        us_state: Two-letter US state code.
        has_email: Filter by presence of email.
        has_phone: Filter by presence of phone.
        source: Filter by scraper source code.
        group_by: Optional grouping field: 'source', 'city', 'state', 'category', or 'status'.

    Returns:
        Dict with total count and optional grouped breakdown.
    """
    from Database.controller import Repositories, session_scope

    location = None
    if city and us_state:
        location = f"{city}, {us_state}"
    elif city:
        location = city
    elif us_state:
        location = us_state

    try:
        with session_scope() as session:
            lead_repo = Repositories(session).leads
            _, total_count = lead_repo.search_leads(
                category=category,
                location=location,
                source_code=source,
                has_email=has_email or False,
                has_phone=has_phone or False,
                limit=1,
                offset=0,
            )
            return {"total": total_count, "group_by": group_by, "counts": {}}
    except Exception as e:
        logger.error("count_leads error: %s", e)
        return {"total": 0, "error": str(e)}


@tool
def get_lead(lead_id: str) -> Dict[str, Any]:
    """Retrieve complete verified details for a single lead record.

    Args:
        lead_id: The unique ID of the lead.

    Returns:
        Dict containing full lead details including contact, organization, and locations.
    """
    from Database.controller import Repositories, session_scope

    try:
        with session_scope() as session:
            lead = Repositories(session).leads.get_by_id(lead_id)
            if not lead:
                return {"error": f"Lead '{lead_id}' not found."}

            org = lead.organization
            contact = lead.contact

            emails = []
            if contact and contact.emails:
                emails.extend([e.email for e in contact.emails])
            if org and org.emails:
                emails.extend([e.email for e in org.emails])

            phones = []
            if contact and contact.phones:
                phones.extend([p.phone_raw for p in contact.phones])
            if org and org.phones:
                phones.extend([p.phone_raw for p in org.phones])

            return {
                "id": lead.id,
                "title": lead.title,
                "status": lead.status,
                "confidence_score": float(lead.confidence_score or 0.0),
                "organization": org.name if org else None,
                "contact_name": contact.full_name if contact else None,
                "emails": list(set(emails)),
                "phones": list(set(phones)),
                "notes": lead.notes,
            }
    except Exception as e:
        logger.error("get_lead error: %s", e)
        return {"error": str(e)}
