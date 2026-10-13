"""
tests/unit/test_agent_graph.py
──────────────────────────────
Unit and workflow tests for the LangGraph agent graph, checkpointer,
nodes, tools, and confirmation interrupt flow.
Complies with Phase P11.
"""

from __future__ import annotations

import json
import uuid
import pytest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.graph.graph import (
    build_agent_graph,
    get_compiled_graph,
    route_after_agent,
    route_after_confirmation,
    route_after_validate,
)
from agents.graph.nodes.agent import _sanitize_trimmed_history
from agents.graph.nodes.confirmation import ask_confirmation, await_confirmation
from agents.graph.nodes.enqueue_job import enqueue_job
from agents.graph.nodes.finalize import _check_groundedness, finalize
from agents.graph.nodes.load_context import build_system_prompt, load_context
from agents.graph.nodes.rag_retrieve import rag_retrieve
from agents.graph.nodes.validate_proposal import validate_proposal
from agents.graph.runner import classify_confirmation
from agents.graph.state import AgentState
from agents.graph.tools import ALL_TOOLS, READ_TOOLS


# ---------------------------------------------------------------------------
# Test Graph Construction & Routing
# ---------------------------------------------------------------------------

def test_graph_compiles_successfully():
    """Verify that StateGraph builds and compiles cleanly with all required nodes."""
    memory_cp = MemorySaver()
    g = build_agent_graph(checkpointer_instance=memory_cp)
    assert g is not None

    nodes = g.get_graph().nodes
    expected_nodes = {
        "load_context",
        "rag_retrieve",
        "agent",
        "tools",
        "validate_proposal",
        "ask_confirmation",
        "await_confirmation",
        "enqueue_job",
        "finalize",
    }
    assert expected_nodes.issubset(set(nodes.keys()))


def test_route_after_agent():
    """Test conditional routing after the agent node."""
    # 1. No tool calls -> finalize
    state_no_calls: AgentState = {
        "messages": [AIMessage(content="Hello there!")],
        "tool_steps": 1,
    }
    assert route_after_agent(state_no_calls) == "finalize"

    # 2. Step limit exceeded -> finalize
    state_limit: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_leads", "args": {}, "id": "tc1"}],
            )
        ],
        "tool_steps": 10,
    }
    assert route_after_agent(state_limit) == "finalize"

    # 3. propose_scrape tool call -> validate_proposal
    state_scrape: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "propose_scrape", "args": {"source": "bonfire"}, "id": "tc2"}],
            )
        ],
        "tool_steps": 1,
    }
    assert route_after_agent(state_scrape) == "validate_proposal"

    # 4. Read tools -> tools
    state_read: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_leads", "args": {}, "id": "tc3"}],
            )
        ],
        "tool_steps": 1,
    }
    assert route_after_agent(state_read) == "tools"


def test_route_after_validate():
    """Test conditional routing after validate_proposal."""
    # Refusal written (pending_proposal is None) -> agent
    assert route_after_validate({"pending_proposal": None}) == "agent"

    # Valid proposal without confirmed -> ask_confirmation
    assert route_after_validate({"pending_proposal": {"id": "p1"}, "confirmed": False}) == "ask_confirmation"

    # Valid proposal with confirmed=True -> enqueue_job
    assert route_after_validate({"pending_proposal": {"id": "p1"}, "confirmed": True}) == "enqueue_job"


def test_route_after_confirmation():
    """Test conditional routing after await_confirmation."""
    # Approved -> enqueue_job
    assert route_after_confirmation({"confirmed": True, "decision": "APPROVED", "pending_proposal": {"id": "p1"}}) == "enqueue_job"

    # Modified -> validate_proposal
    assert route_after_confirmation({"confirmed": True, "decision": None, "pending_proposal": {"id": "p1"}}) == "validate_proposal"

    # Rejected / unrelated -> agent
    assert route_after_confirmation({"confirmed": False, "decision": "DECLINED"}) == "agent"


# ---------------------------------------------------------------------------
# Test Nodes & Logic
# ---------------------------------------------------------------------------

def test_load_context_resets_steps():
    """Test load_context resets tool_steps and trace."""
    state: AgentState = {
        "tool_steps": 5,
        "trace": [{"old": "trace"}],
        "confirmed": True,
    }
    res = load_context(state)
    assert res["tool_steps"] == 0
    assert res["trace"] == []
    assert res["confirmed"] is False


def test_build_system_prompt():
    """Test dynamic system prompt generation contains catalog and rules."""
    state: AgentState = {
        "slots": {"category": "HVAC", "quantity": 25},
        "last_search": {"total": 5, "returned": 5, "sufficient": False},
    }
    prompt = build_system_prompt(state)
    assert "Operating Rules" in prompt
    assert "HVAC" in prompt
    assert "Available Scraper Sources" in prompt


def test_rag_retrieve_graceful_on_unavailable():
    """Verify rag_retrieve does not raise when RAG is not configured/available."""
    state: AgentState = {
        "messages": [HumanMessage(content="Find roofing contracts in Dallas")],
    }
    with patch("services.rag.rag_client.status", return_value={"state": "not_configured", "available": False}):
        res = rag_retrieve(state)
        assert res["rag_status"]["available"] is False
        assert res["rag_hits"] == []
        assert any(t["tool"] == "rag_retrieve" for t in res["trace"])


def test_validate_proposal_requires_db_search_first():
    """Verify propose_scrape is refused if search_leads was not run for this turn."""
    state: AgentState = {
        "turn_id": "turn-100",
        "last_search": None,  # No search performed
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "propose_scrape", "args": {"source": "bonfire"}, "id": "c1"}],
            )
        ],
    }
    res = validate_proposal(state)
    assert res["pending_proposal"] is None
    msgs = res["messages"]
    assert len(msgs) == 1
    assert "Proposal refused" in msgs[0].content
    assert msgs[0].tool_call_id == "c1"


def test_validate_proposal_success():
    """Verify propose_scrape creates pending_proposal when search was insufficient."""
    turn_id = str(uuid.uuid4())
    state: AgentState = {
        "session_id": "sess-1",
        "query_id": "q-1",
        "turn_id": turn_id,
        "last_search": {
            "turn_id": turn_id,
            "sufficient": False,
            "total": 2,
        },
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_scrape",
                        "args": {"source": "bonfire", "category": "construction", "quantity": 30},
                        "id": "c2",
                    }
                ],
            )
        ],
    }
    from Database.search import SearchCriteria
    state['slots'] = {'category': 'construction', 'quantity': 30, 'record_kind': 'opportunity'}
    state['last_search']['slots_hash'] = SearchCriteria.from_slots(state['slots']).fingerprint()
    state['last_search']['error'] = None
    res = validate_proposal(state)
    assert res["pending_proposal"] is not None
    assert res["pending_proposal"]["source"] == "bonfire"
    assert res["pending_proposal"]["tool_call_id"] == "c2"


def test_confirmation_outage_never_authorizes_with_heuristics():
    from agents.llm.chat_model import LLMUnavailable
    with patch('agents.graph.runner.invoke_structured', side_effect=LLMUnavailable('timeout')):
        with pytest.raises(LLMUnavailable):
            classify_confirmation('yes', {'question': 'Run scrape?'})


def test_safe_history_sanitizer():
    """Verify message sanitizer never leaves an orphaned ToolMessage."""
    t_msg = ToolMessage(content="result", tool_call_id="call1")
    h_msg = HumanMessage(content="hello")
    sanitized = _sanitize_trimmed_history([t_msg, h_msg])
    assert sanitized == [h_msg]


def test_groundedness_checker(caplog):
    """Verify groundedness check warns on fabricated numbers."""
    tool_m = ToolMessage(content="Found 14 records in Dallas", tool_call_id="c1")
    from unittest.mock import patch
    with patch("agents.graph.nodes.finalize.logger.warning") as mock_warn:
        _check_groundedness("We found 999 records.", [tool_m])
        assert mock_warn.called


# ---------------------------------------------------------------------------
# End-to-End Interrupt & Confirmation Flow (with MemorySaver)
# ---------------------------------------------------------------------------

def test_interrupt_requires_a_typed_approval():
    from langgraph.graph import StateGraph, START, END
    g = StateGraph(AgentState)
    g.add_node('approval', await_confirmation)
    g.add_edge(START, 'approval'); g.add_edge('approval', END)
    graph = g.compile(checkpointer=MemorySaver())
    config = {'configurable': {'thread_id': str(uuid.uuid4())}}
    proposal = {'tool_call_id': 'proposal-1', 'question': 'Run 10 roofing records?'}
    graph.invoke({'pending_proposal': proposal, 'messages': []}, config)
    assert graph.get_state(config).interrupts
    graph.invoke(Command(resume={'decision': 'modify', 'edits': {'quantity': 5}, 'text': 'Only five'}), config)
    state = graph.get_state(config).values
    assert state['slots']['quantity'] == 5
    assert state['confirmed'] is False
    assert state['pending_proposal'] is None
