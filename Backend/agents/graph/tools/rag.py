"""
agents/graph/tools/rag.py
─────────────────────────
Knowledge Base (RAG) tools for the LangGraph agent.
Complies with Phase P11.5.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.tools import tool

from services.rag import rag_client

logger = logging.getLogger(__name__)


@tool
def knowledge_base_status() -> Dict[str, Any]:
    """Check the health and readiness status of the Knowledge Base.

    Returns whether the knowledge base is available and how many documents
    and chunks are indexed.
    """
    return rag_client.status()


@tool
def search_knowledge_base(query: str, top_k: int = 5) -> Dict[str, Any]:
    """Search the internal Knowledge Base for domain guidelines, procurement rules, or manuals.

    Use this tool when users ask questions about procurement rules, licensing requirements,
    or policies that may be covered in internal documentation.

    Args:
        query: The search query to locate relevant knowledge base excerpts.
        top_k: Number of relevant chunks to retrieve (1-10). Default 5.

    Returns:
        Dict with search hits or status message if the knowledge base is not ready.
    """
    status_info = rag_client.status()
    if not status_info.get("available", False):
        return {
            "status": "unavailable",
            "message": f"Knowledge base is not ready: {status_info.get('message', 'unavailable')}",
            "hits": [],
        }

    k = min(max(1, top_k), 10)
    hits = rag_client.search(query=query, top_k=k)
    return {
        "status": "success",
        "count": len(hits),
        "hits": hits,
    }
