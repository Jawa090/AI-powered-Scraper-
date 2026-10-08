"""
agents/graph/nodes/confirmation.py
──────────────────────────────────
Confirmation nodes for LangGraph agent (ask_confirmation and await_confirmation).
Complies with Phase P11.4 and Experiment E4.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt

from agents.graph.state import AgentState
from agents.graph.utils import normalize_content
from agents.llm.chat_model import get_chat_model, invoke_llm

logger = logging.getLogger(__name__)


def ask_confirmation(state: AgentState) -> Dict[str, Any]:
    """
    Generates a concise confirmation question in the user's language.
    Stored in pending_proposal['question']; does not append to messages.
    """
    proposal = state.get("pending_proposal")
    if not proposal:
        return {}

    args = proposal.get("args") or {}
    source = proposal.get("source", "")
    qty = args.get("quantity")
    category = args.get("category") or "relevant"
    location = args.get("city") or args.get("us_state") or ""
    loc_str = f" in {location}" if location else ""

    model = get_chat_model()
    prompt = ('Ask for explicit permission to START this proposed scrape. It has not run yet. '
        'State the quantity and filters accurately; ask whether to proceed. '
        'Do not report results, invent an outcome, or ask whether a past scrape succeeded. '
        'Use the language of these actual user messages; use English for English messages: '
        + str([str(m.content) for m in state.get('messages', []) if getattr(m, 'type', '') == 'human'][-3:])
        + f'. Proposal: {proposal}')
    resp = invoke_llm(model, [HumanMessage(content=prompt)], max_retries=1)
    question = normalize_content(getattr(resp, 'content', '')).strip()
    if not question:
        from agents.llm.chat_model import LLMUnavailable
        raise LLMUnavailable('provider_error', 'Empty confirmation response')

    updated_proposal = dict(proposal)
    updated_proposal["question"] = question

    return {"pending_proposal": updated_proposal}


def await_confirmation(state: AgentState) -> Dict[str, Any]:
    """
    Suspends execution awaiting user confirmation decision.
    Upon resumption, processes approve, reject, modify, or unrelated decisions.
    """
    proposal = state.get("pending_proposal") or {}
    tool_call_id = proposal.get("tool_call_id", "")
    question = proposal.get("question") or "Do you want to proceed with this scrape?"

    # Suspend execution via LangGraph interrupt
    resumed = interrupt({
        "type": "scrape_confirmation",
        "proposal": proposal,
        "question": question,
    })

    # Resumed decision handling
    decision_type = "unrelated"
    edits = None
    text = ""

    if isinstance(resumed, dict):
        decision_type = resumed.get("decision", "unrelated").lower().strip()
        edits = resumed.get("edits")
        text = resumed.get("text", "")
    elif isinstance(resumed, str):
        # Only the typed classifier result may authorize execution.
        text = resumed

    if decision_type == "approve":
        return {
            "confirmed": True,
            "decision": "APPROVED",
        }

    elif decision_type == "reject":
        tool_msg = ToolMessage(
            content="User declined the scrape.",
            tool_call_id=tool_call_id,
        )
        return {
            "messages": [tool_msg, HumanMessage(content=text)],
            "decision": "DECLINED",
            "pending_proposal": None,
        }

    elif decision_type == "modify":
        slots = dict(state.get('slots') or {})
        if isinstance(edits, dict):
            slots.update(edits)
        return {'slots': slots, 'confirmed': False, 'pending_proposal': None, 'last_search': None,
            'messages': [ToolMessage(content='Proposal changed. Search again and request fresh confirmation.', tool_call_id=tool_call_id),
                         HumanMessage(content=text)]}

    else:
        # Unrelated message: answer open call and append new human message
        tool_msg = ToolMessage(
            content="User did not confirm; their new message follows.",
            tool_call_id=tool_call_id,
        )
        new_msgs = [tool_msg]
        if text:
            new_msgs.append(HumanMessage(content=text))
        return {
            "messages": new_msgs,
            "pending_proposal": None,
        }
