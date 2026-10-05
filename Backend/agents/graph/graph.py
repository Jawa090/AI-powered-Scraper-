"""
agents/graph/graph_v2.py
────────────────────────
LangGraph v2 — LLM tool-calling agent graph.

Replaces keyword-based routing with a proper LLM agent loop:
    load_context → agent (LLM + tools) ↔ tools → scrape_gate → finalize

The old graph.py remains as fallback for degraded mode.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any, Annotated, Dict, List, Optional

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, END, add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from agents.graph.tools import READ_TOOLS, ALL_TOOLS

logger = logging.getLogger(__name__)

MAX_TOOL_STEPS = int(os.environ.get("MAX_TOOL_STEPS", "6"))

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentStateV2(dict):
    """LangGraph v2 agent state with message accumulation."""
    pass

# We use TypedDict for proper LangGraph integration
from typing import TypedDict

class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    session_id: str
    department_id: str
    tool_steps: int
    degraded: bool


# ---------------------------------------------------------------------------
# Load system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
_SYSTEM_PROMPT_CACHE: Optional[str] = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is None:
        if _SYSTEM_PROMPT_PATH.exists():
            _SYSTEM_PROMPT_CACHE = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        else:
            _SYSTEM_PROMPT_CACHE = "You are a helpful data operations assistant."
            logger.warning("System prompt not found at %s", _SYSTEM_PROMPT_PATH)
    return _SYSTEM_PROMPT_CACHE


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def call_model(state: AgentState) -> dict:
    """Call the LLM with tools bound. This is the 'agent' node."""
    from agents.llm.chat_models import build_chat_model

    messages = state.get("messages", [])
    tool_steps = state.get("tool_steps", 0)

    # Build system message
    system_text = _get_system_prompt()
    system_msg = SystemMessage(content=system_text)

    try:
        model = build_chat_model(tools=ALL_TOOLS)
        response = model.invoke([system_msg, *messages])
        return {
            "messages": [response],
            "tool_steps": tool_steps + 1,
            "degraded": False,
        }
    except Exception as e:
        logger.error("LLM call failed: %s", e, exc_info=True)
        # Degraded mode — return a plain text response
        from langchain_core.messages import AIMessage
        fallback_msg = AIMessage(content=(
            "I'm having trouble connecting to the AI service right now. "
            "You can still search for leads using the filters panel. "
            "Please try again in a moment."
        ))
        return {
            "messages": [fallback_msg],
            "degraded": True,
        }


def scrape_gate(state: AgentState) -> dict:
    """
    Intercept propose_scrape tool calls. Validate preconditions,
    then enqueue the scrape job.
    """
    messages = state.get("messages", [])
    user_id = state.get("user_id", "")

    # Find the propose_scrape tool call in the last AI message
    last_msg = messages[-1] if messages else None
    if not last_msg or not hasattr(last_msg, "tool_calls"):
        return {"messages": []}

    results = []
    for call in (last_msg.tool_calls or []):
        if call["name"] == "propose_scrape":
            args = call.get("args", {})
            source = args.get("source", "")
            category = args.get("category")
            location = args.get("location")
            limit = args.get("limit", 20)

            # Validate source
            valid_sources = {"bonfire", "dasny", "jwiz", "nyscr"}
            if source not in valid_sources:
                results.append(ToolMessage(
                    content=json.dumps({"error": f"Unknown source '{source}'. Valid: {sorted(valid_sources)}"}),
                    tool_call_id=call["id"],
                ))
                continue

            # Enqueue the job
            try:
                from scraper_manager import scraper_manager
                import uuid

                job_id = scraper_manager.create_job(
                    script_id=source,
                    parameters={
                        "category": category,
                        "location": location,
                        "limit": min(max(1, limit), 200),
                    },
                    created_by=user_id,
                    department_id=state.get("department_id", ""),
                    query_id="",
                    idempotency_key=str(uuid.uuid4()),
                )
                results.append(ToolMessage(
                    content=json.dumps({
                        "job_id": job_id,
                        "status": "Queued",
                        "source": source,
                        "message": f"Scrape job queued successfully. Job ID: {job_id}",
                    }),
                    tool_call_id=call["id"],
                ))
            except Exception as e:
                logger.error("scrape_gate enqueue error: %s", e, exc_info=True)
                results.append(ToolMessage(
                    content=json.dumps({"error": f"Failed to enqueue scrape: {str(e)}"}),
                    tool_call_id=call["id"],
                ))
        else:
            # Non-scrape tool call in the same message — tell LLM to run separately
            results.append(ToolMessage(
                content=json.dumps({"error": "Please call this tool separately, not alongside propose_scrape."}),
                tool_call_id=call["id"],
            ))

    return {"messages": results}


def route_after_agent(state: AgentState) -> str:
    """Route after the agent node: tools, scrape_gate, or end."""
    messages = state.get("messages", [])
    if not messages:
        return END

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None) or []

    if not tool_calls:
        return END

    # Check tool step limit
    if state.get("tool_steps", 0) >= MAX_TOOL_STEPS:
        logger.warning("Tool step limit reached (%d)", MAX_TOOL_STEPS)
        return END

    # Check if any call is propose_scrape
    if any(c["name"] == "propose_scrape" for c in tool_calls):
        return "scrape_gate"

    return "tools"


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------

def build_agent_graph():
    """Build the v2 LangGraph agent with LLM tool-calling."""
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(READ_TOOLS, handle_tool_errors=True))
    graph.add_node("scrape_gate", scrape_gate)

    # Edges
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent, {
        "tools": "tools",
        "scrape_gate": "scrape_gate",
        END: END,
    })
    graph.add_edge("tools", "agent")
    graph.add_edge("scrape_gate", "agent")

    from agents.graph.checkpointer import checkpointer
    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Module-level compiled graph (singleton)
# ---------------------------------------------------------------------------

_compiled_graph = None


def get_compiled_graph():
    """Return the compiled LangGraph (lazy singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
        logger.info("LangGraph agent graph compiled successfully.")
    return _compiled_graph
