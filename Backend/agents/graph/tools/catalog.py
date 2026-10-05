"""
agents/graph/tools/catalog.py
──────────────────────────────
Source catalog and dataset listing tools for the LangGraph agent.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def list_sources() -> dict:
    """List all available scraping sources and their capabilities.

    Returns information about each registered scraper including name,
    category, capabilities, and whether credentials are configured.
    Use this to answer questions about what data sources are available.

    Returns:
        Dict with list of source descriptors.
    """
    from execution.registry import SCRIPTS_REGISTRY

    sources = []
    for s in SCRIPTS_REGISTRY:
        sources.append({
            "id": s["id"],
            "name": s["name"],
            "category": s.get("category", ""),
            "description": s.get("description", ""),
            "capabilities": s.get("capabilities", []),
            "status": s.get("status", "Unknown"),
        })

    return {"sources": sources, "count": len(sources)}


@tool
def list_datasets(limit: int = 20, offset: int = 0) -> dict:
    """List datasets created from scraper runs.

    Args:
        limit: Max datasets to return (1-50). Default 20.
        offset: Pagination offset.

    Returns:
        Dict with dataset summaries.
    """
    from Database.controller import session_scope
    from Database.models.dataset import Dataset
    from sqlalchemy import select

    limit = min(max(1, limit), 50)
    offset = max(0, offset)

    try:
        with session_scope() as session:
            stmt = select(Dataset).order_by(Dataset.created_at.desc()).offset(offset).limit(limit)
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
        logger.error("list_datasets tool error: %s", e, exc_info=True)
        return {"datasets": [], "count": 0, "error": str(e)}
