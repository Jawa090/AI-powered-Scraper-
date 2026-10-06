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
    qty = args.get("quantity", 20)
    category = args.get("category") or "relevant"
    location = args.get("city") or args.get("us_state") or ""
    loc_str = f" in {location}" if location else ""

    fallback_question = f"Would you like me to scrape {qty} {category} leads from {source.upper()}{loc_str}?"

    try:
        model = get_chat_model()
        prompt = (
            f"You are asking the user for confirmation to execute a web scrape.\n"
            f"Parameters: source={source}, category={category}, location={location}, target_quantity={qty}.\n"
            f"Write a single, friendly, concise question in the user's language asking if they want to proceed."
        )
        resp = invoke_llm(model, [HumanMessage(content=prompt)], max_retries=1)
        question = getattr(resp, "content", "").strip() or fallback_question
    except Exception as e:
        logger.warning("Error generating confirmation question via LLM: %s", e)
        question = fallback_question

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
        t = resumed.strip().lower()
        if t in ["approve", "yes", "confirm"]:
            decision_type = "approve"
        elif t in ["reject", "no", "cancel"]:
            decision_type = "reject"
        else:
            decision_type = "unrelated"
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
            "messages": [tool_msg],
            "decision": "DECLINED",
            "pending_proposal": None,
        }

    elif decision_type == "modify":
        updated = dict(proposal)
        if isinstance(edits, dict):
            updated["args"].update(edits)
        return {
            "pending_proposal": updated,
            "confirmed": True,
        }

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
