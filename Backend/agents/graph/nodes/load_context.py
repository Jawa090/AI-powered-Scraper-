"""
agents/graph/nodes/load_context.py
───────────────────────────────────
Context preparation node for each LangGraph agent turn.
Complies with Phase P11.4 load_context.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from Database.controller import session_scope
from Database.models.message import AgentMessage
from agents.graph.state import AgentState
from scrappers.controller import describe_for_llm
from settings import settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
_BASE_PROMPT_CACHE: Optional[str] = None


def get_base_prompt() -> str:
    global _BASE_PROMPT_CACHE
    if _BASE_PROMPT_CACHE is None:
        if _PROMPT_PATH.exists():
            _BASE_PROMPT_CACHE = _PROMPT_PATH.read_text(encoding="utf-8").strip()
        else:
            _BASE_PROMPT_CACHE = "You are a helpful Data Operations AI Assistant."
    return _BASE_PROMPT_CACHE


def build_system_prompt(state: AgentState) -> str:
    """
    Dynamically compile system prompt for the current turn:
    - Base prompt rules
    - Registered source catalog
    - Knowledge Base status & excerpts
    - Current slots & last search summary
    - Unseen system notifications
    """
    sections = [get_base_prompt()]

    # 1. Registered Scraper Catalog
    try:
        catalog = describe_for_llm()
        cat_lines = ["\n## Available Scraper Sources:"]
        for s in catalog:
            ready_str = "READY" if s.get("ready") else f"UNREADY ({s.get('unready_reason')})"
            cat_lines.append(
                f"- **{s['name']}** (`{s['id']}`): {s.get('description', '')} "
                f"[{ready_str}] Coverage: {s.get('coverage')}, Supports: {s.get('supports')}"
            )
        sections.append("\n".join(cat_lines))
    except Exception as e:
        logger.warning("Failed to render scraper catalog for prompt: %s", e)

    # 2. Knowledge Base Context & Excerpts
    rag_status = state.get("rag_status") or {}
    rag_hits = state.get("rag_hits") or []
    kb_lines = [f"\n## Knowledge Base Status: {rag_status.get('state', 'not_checked')}"]
    if rag_hits:
        kb_lines.append("Relevant Knowledge Excerpts:")
        for h in rag_hits:
            chunk_id = h.get("chunkId", "unknown")
            title = h.get("title", "Document")
            content = h.get("content", "")[:300]
            kb_lines.append(f"- [kb:{chunk_id}] {title}: {content}")
    sections.append("\n".join(kb_lines))

    # 3. Current Slots & Last Search
    slots = state.get("slots") or {}
    if slots:
        sections.append(f"\n## Active Requirement Slots:\n{json.dumps(slots, indent=2)}")

    last_search = state.get("last_search") or {}
    if last_search:
        sections.append(
            f"\n## Last Database Search Summary:\n"
            f"Total available: {last_search.get('total', 0)}, "
            f"Returned: {last_search.get('returned', 0)}, "
            f"Sufficient: {last_search.get('sufficient', False)}"
        )

    # 4. Summary of previous turns
    summary = state.get("summary")
    if summary:
        sections.append(f"\n## Prior Conversation Summary:\n{summary}")

    return "\n\n".join(sections)


def load_context(state: AgentState) -> Dict[str, Any]:
    """
    Prepares context for the turn: resets step counters and flags.
    System prompt is dynamically assembled and not stored in messages.
    """
    session_id = state.get("session_id")

    # Fetch any unnotified system events
    unseen_events: List[str] = []
    if session_id:
        try:
            with session_scope() as session:
                msgs = session.scalars(
                    select(AgentMessage)
                    .where(AgentMessage.session_id == session_id)
                    .where(AgentMessage.role == "system_event")
                ).all()
                for m in msgs:
                    meta = m.message_metadata or {}
                    if not meta.get("notified"):
                        unseen_events.append(m.text)
        except Exception as e:
            logger.debug("Error checking unseen events: %s", e)

    return {
        "tool_steps": 0,
        "trace": [],
        "confirmed": False,
    }
