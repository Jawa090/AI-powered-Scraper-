"""
agents/graph/graph.py
─────────────────────
LangGraph StateGraph wiring for the DataOps AI agent.
Complies with Phase P11.3.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_core.runnables import RunnableConfig

from agents.graph.checkpointer import checkpointer
from agents.graph.nodes import (
    ask_confirmation,
    await_confirmation,
    call_model,
    enqueue_job,
    finalize,
    load_context,
    rag_retrieve,
    validate_proposal,
)
from agents.graph.state import AgentState
from agents.graph.tools import READ_TOOLS
from settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing Functions
# ---------------------------------------------------------------------------

def route_after_agent(state: AgentState) -> str:
    """
    Route after the 'agent' node:
    - no tool calls -> finalize
    - tool_steps >= MAX_TOOL_STEPS -> finalize
    - any propose_scrape call -> validate_proposal
    - otherwise -> tools
    """
    if state.get('request_intent') == 'records' and state.get('missing_requirements'):
        return 'finalize'
    messages = state.get("messages", [])
    if not messages:
        return "finalize"

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None) or []

    if not tool_calls:
        return "finalize"

    max_steps = getattr(settings, "MAX_TOOL_STEPS", 10)
    if state.get("tool_steps", 0) >= max_steps:
        logger.warning("Agent tool step limit reached (%d)", max_steps)
        return "finalize"

    if any(c.get("name") == "propose_scrape" for c in tool_calls):
        return "validate_proposal"

    return "tools"


def route_after_validate(state: AgentState) -> str:
    """
    Route after 'validate_proposal':
    - refusal written (pending_proposal is None) -> agent
    - valid and confirmed -> enqueue_job
    - valid -> ask_confirmation
    """
    pending = state.get("pending_proposal")
    if not pending:
        return "agent"

    if state.get("confirmed", False):
        return "enqueue_job"

    return "ask_confirmation"


def route_after_confirmation(state: AgentState) -> str:
    """
    Route after 'await_confirmation':
    - approve -> enqueue_job
    - modify -> validate_proposal
    - reject / unrelated -> agent
    """
    confirmed = state.get("confirmed", False)
    pending = state.get("pending_proposal")

    if confirmed:
        if pending and state.get("decision") != "APPROVED":
            # Modified arguments require re-validation
            return "validate_proposal"
        return "enqueue_job"

    return "agent"


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_agent_graph(checkpointer_instance: Optional[Any] = None) -> Any:
    """Construct and compile the LangGraph StateGraph."""
    g = StateGraph(AgentState)
    def guarded(node):
        def invoke(state: AgentState, config: RunnableConfig):
            from services.sessions import require_active
            require_active(state.get('session_id'))
            return node.invoke(state, config) if hasattr(node, 'invoke') else node(state)
        return invoke

    # Register Nodes
    g.add_node("load_context", guarded(load_context))
    from agents.graph.nodes.gather_requirements import interpret_request
    g.add_node("gather_requirements", guarded(interpret_request))
    g.add_node("rag_retrieve", guarded(rag_retrieve))
    g.add_node("agent", guarded(call_model))
    g.add_node("tools", guarded(ToolNode(READ_TOOLS, handle_tool_errors=False)))
    g.add_node("validate_proposal", guarded(validate_proposal))
    g.add_node("ask_confirmation", guarded(ask_confirmation))
    g.add_node("await_confirmation", guarded(await_confirmation))
    g.add_node("enqueue_job", guarded(enqueue_job))
    g.add_node("finalize", guarded(finalize))

    # Register Edges
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "gather_requirements")
    g.add_edge("gather_requirements", "rag_retrieve")
    g.add_edge("rag_retrieve", "agent")

    g.add_conditional_edges(
        "agent",
        route_after_agent,
        ["tools", "validate_proposal", "finalize"],
    )
    g.add_edge("tools", "agent")

    g.add_conditional_edges(
        "validate_proposal",
        route_after_validate,
        ["agent", "ask_confirmation", "enqueue_job"],
    )
    g.add_edge("ask_confirmation", "await_confirmation")

    g.add_conditional_edges(
        "await_confirmation",
        route_after_confirmation,
        ["enqueue_job", "validate_proposal", "agent"],
    )
    g.add_edge("enqueue_job", "agent")
    g.add_edge("finalize", END)

    cp = checkpointer_instance if checkpointer_instance is not None else checkpointer
    return g.compile(checkpointer=cp)


# ---------------------------------------------------------------------------
# Module Singleton
# ---------------------------------------------------------------------------

_compiled_graph = None


def get_compiled_graph(checkpointer_instance: Optional[Any] = None) -> Any:
    """Return the compiled LangGraph singleton."""
    global _compiled_graph
    if _compiled_graph is None or checkpointer_instance is not None:
        g = build_agent_graph(checkpointer_instance=checkpointer_instance)
        if checkpointer_instance is None:
            _compiled_graph = g
        return g
    return _compiled_graph


def export_mermaid(output_path: str = "docs/agent_graph.md") -> str:
    """Export the compiled LangGraph mermaid visualization to a markdown file."""
    graph = get_compiled_graph()
    mermaid_code = graph.get_graph().draw_mermaid()
    p = Path(output_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent.parent.parent / output_path
    p.parent.mkdir(parents=True, exist_ok=True)
    content = f"# Agent Graph Visualization (LangGraph)\n\n```mermaid\n{mermaid_code}\n```\n"
    p.write_text(content, encoding="utf-8")
    return mermaid_code
