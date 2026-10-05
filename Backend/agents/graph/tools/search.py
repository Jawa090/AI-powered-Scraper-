"""
agents/graph/tools/search.py
─────────────────────────────
Lead search, count, and detail tools for the LangGraph agent.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def search_leads(
    category: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None,
    source: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search the local verified leads database.

    Use this BEFORE proposing any scrape. Returns matching leads with
    counts so you can determine if the database already has enough data.

    Args:
        category: Industry or trade to filter by (e.g. "plumbing", "electrical", "construction").
        city: City name to filter by (e.g. "Brooklyn", "Dallas").
        state: State name or abbreviation (e.g. "New York", "NY", "Texas").
        has_email: If True, only leads with an email. If False, only leads without.
        has_phone: If True, only leads with a phone. If False, only leads without.
        source: Filter by scraper source code (e.g. "bonfire", "dasny", "jwiz", "nyscr").
        limit: Max records to return (1-50). Default 20.
        offset: Pagination offset. Default 0.

    Returns:
        Dict with total count and compact lead items.
    """
    from Database.controller import session_scope
    from Database.controller import Repositories

    limit = min(max(1, limit), 50)
    offset = max(0, offset)

    location = None
    if city and state:
        location = f"{city}, {state}"
    elif city:
        location = city
    elif state:
        location = state

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

            items = []
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

            requested_qty = limit + offset  # rough target
            sufficient = total_count >= limit and total_count > 0

            return {
                "total": total_count,
                "returned": len(items),
                "items": items,
                "sufficient": sufficient,
                "filters_used": {
                    "category": category,
                    "city": city,
                    "state": state,
                    "source": source,
                    "has_email": has_email,
                    "has_phone": has_phone,
                },
            }
    except Exception as e:
        logger.error("search_leads tool error: %s", e, exc_info=True)
        return {"total": 0, "returned": 0, "items": [], "sufficient": False, "error": str(e)}


@tool
def count_leads(
    category: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None,
    source: Optional[str] = None,
) -> dict:
    """Count matching leads in the database without fetching full records.

    Useful for quick availability checks before deciding to scrape.

    Args:
        category: Industry or trade to filter by.
        city: City name to filter by.
        state: State name or abbreviation.
        has_email: If True, only count leads with an email.
        has_phone: If True, only count leads with a phone.
        source: Filter by scraper source code.

    Returns:
        Dict with total count.
    """
    from Database.controller import session_scope
    from Database.controller import Repositories

    location = None
    if city and state:
        location = f"{city}, {state}"
    elif city:
        location = city
    elif state:
        location = state

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
            )
            return {"total": total_count}
    except Exception as e:
        logger.error("count_leads tool error: %s", e, exc_info=True)
        return {"total": 0, "error": str(e)}


@tool
def get_lead(lead_id: str) -> dict:
    """Get full details for a specific lead by its ID.

    Args:
        lead_id: The unique ID of the lead to retrieve.

    Returns:
        Full lead record with all available fields.
    """
    from Database.controller import session_scope
    from Database.models.lead import Lead

    try:
        with session_scope() as session:
            lead = session.get(Lead, lead_id)
            if not lead:
                return {"error": f"Lead '{lead_id}' not found."}

            org = lead.organization
            contact = lead.contact

            email = None
            if contact and contact.emails:
                email = contact.emails[0].email
            elif org and org.emails:
                email = org.emails[0].email

            phone = None
            if contact and contact.phones:
                phone = contact.phones[0].phone_raw
            elif org and org.phones:
                phone = org.phones[0].phone_raw

            return {
                "id": lead.id,
                "company": org.name if org else None,
                "contact": contact.full_name if contact else None,
                "title": lead.title,
                "email": email,
                "phone": phone,
                "website": org.website if org else None,
                "industry": org.industry if org else None,
                "status": lead.status,
                "notes": lead.notes,
                "dataset_id": lead.dataset_id,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
            }
    except Exception as e:
        logger.error("get_lead tool error: %s", e, exc_info=True)
        return {"error": str(e)}
