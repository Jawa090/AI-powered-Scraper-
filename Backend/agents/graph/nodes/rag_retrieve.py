"""
agents/graph/nodes/rag_retrieve.py
───────────────────────────────────
RAG retrieval node executed once per human turn.
Complies with Phase P11.4 rag_retrieve.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.graph.state import AgentState
from services.rag import rag_client
from settings import settings

logger = logging.getLogger(__name__)


def rag_retrieve(state: AgentState) -> Dict[str, Any]:
    """
    Retrieves relevant Knowledge Base excerpts for the user query.
    Never raises an exception; records trace entry.
    """
    # Event turns don't require KB search
    if state.get("event_job_id"):
        return {}

    messages = state.get("messages", [])
    last_human_text = ""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            last_human_text = str(msg.content)
            break

    try:
        status_info = rag_client.status()
        hits: List[Dict[str, Any]] = []

        if status_info.get("available") and last_human_text:
            top_k = getattr(settings, "RAG_TOP_K", 5)
            hits = rag_client.search(last_human_text, top_k=top_k)

        trace_entry = {
            "tool": "rag_retrieve",
            "state": status_info.get("state"),
            "hit_ids": [h.get("chunkId") for h in hits if isinstance(h, dict)],
        }
        current_trace = list(state.get("trace", [])) + [trace_entry]

        return {
            "rag_status": status_info,
            "rag_hits": hits,
            "trace": current_trace,
        }
    except Exception as e:
        logger.warning("rag_retrieve unexpected error: %s", e)
        return {
            "rag_status": {"state": "error", "available": False, "message": str(e)},
            "rag_hits": [],
        }
