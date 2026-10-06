"""
agents/graph/tools/catalog.py
──────────────────────────────
Source catalog and dataset listing tools for the LangGraph agent.
Complies with Phase P11.5 and Decision D9 scoping.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from sqlalchemy import select

logger = logging.getLogger(__name__)


@tool
def list_sources() -> Dict[str, Any]:
    """List all available scraping sources and their capabilities.

    Returns registered web scrapers, coverage, fields, and operational readiness.
    Use this to answer questions about what data sources and scrapers are supported.
    """
    from scrappers.controller import describe_for_llm

    sources = describe_for_llm()
    return {"sources": sources, "count": len(sources)}


@tool
def list_datasets(
    limit: int = 20,
    offset: int = 0,
    state: Annotated[dict, InjectedState] = None,
) -> Dict[str, Any]:
    """List datasets created from scraper runs, scoped to the current user.

    Args:
        limit: Max datasets to return (1-50). Default 20.
        offset: Pagination offset. Default 0.

    Returns:
        Dict with dataset summaries.
    """
    from Database.controller import session_scope
    from Database.models.dataset import Dataset

    st = state or {}
    user_id = st.get("user_id")
    user_role = st.get("user_role", "user")

    limit = min(max(1, limit), 50)
    offset = max(0, offset)

    try:
        with session_scope() as session:
            stmt = select(Dataset).order_by(Dataset.created_at.desc())
            if user_role != "admin" and user_id:
                stmt = stmt.where(Dataset.created_by == user_id)
            stmt = stmt.offset(offset).limit(limit)
            datasets = list(session.scalars(stmt).all())

            items = []
            for d in datasets:
                items.append({
                    "id": d.id,
                    "name": d.name,
                    "records_count": d.records_count or 0,
                    "verified_count": d.verified_count or 0,
                    "status": d.status,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                })

            return {"datasets": items, "count": len(items)}
    except Exception as e:
        logger.error("list_datasets error: %s", e)
        return {"datasets": [], "count": 0, "error": str(e)}


@tool
def get_dataset_leads(
    dataset_id: str,
    limit: int = 20,
    offset: int = 0,
    state: Annotated[dict, InjectedState] = None,
) -> Dict[str, Any]:
    """Retrieve leads belonging to a specific dataset, scoped to the current user.

    Args:
        dataset_id: Unique ID of the dataset.
        limit: Max leads to return (1-50). Default 20.
        offset: Pagination offset. Default 0.

    Returns:
        Dict with list of lead items.
    """
    from Database.controller import Repositories, session_scope

    st = state or {}
    user_id = st.get("user_id")
    user_role = st.get("user_role", "user")

    limit = min(max(1, limit), 50)
    offset = max(0, offset)

    try:
        with session_scope() as session:
            repo = Repositories(session).leads
            leads = repo.list_by_dataset(dataset_id, limit=limit, offset=offset)

            items = []
            for lead in leads:
                items.append({
                    "id": lead.id,
                    "title": lead.title,
                    "organization": lead.organization.name if lead.organization else None,
                    "contact": lead.contact.full_name if lead.contact else None,
                    "status": lead.status,
                })

            return {"dataset_id": dataset_id, "leads": items, "count": len(items)}
    except Exception as e:
        logger.error("get_dataset_leads error: %s", e)
        return {"dataset_id": dataset_id, "leads": [], "count": 0, "error": str(e)}
