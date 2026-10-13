"""
agents/graph/nodes/finalize.py
──────────────────────────────
Final response synthesis, dangling call cleanup, groundedness check, and persistence.
Complies with Phase P11.4 finalize and P11.8.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage

from agents.graph.nodes.load_context import build_system_prompt
from agents.graph.persist import save_turn
from agents.graph.state import AgentState
from agents.graph.utils import normalize_content
from agents.llm.chat_model import get_chat_model, invoke_llm

logger = logging.getLogger(__name__)


def validate_record_counts(reply_text, factual_counts):
    """Reject explicit collection-count claims that contradict database/worker facts."""
    plain = re.sub(r'[*_`]', '', reply_text)
    claims = re.findall(
        r'\b(?:found|returned|retrieved|delivered|collected|scraped|saved|here are|there are)\s+'
        r'(?:(?:only|exactly|the|all)\s+|a total of\s+)?(\d+)\s+'
        r'(?:(?:matching|verified|roofing|contractor|new|current|bid|business|available)\s+){0,5}'
        r'(?:records?|companies|leads?|contractors?|opportunities|bids?)\b', plain, re.I)
    return all(int(number) in factual_counts for number in claims)


def grounded_reply(model, messages, facts, answer):
    """Give the provider one chance to repair an incorrect factual count."""
    import json
    from agents.llm.chat_model import LLMUnavailable
    counts = {int(value) for key, value in facts.items()
        if key in {'available', 'returned', 'recordsFound', 'recordsDelivered', 'initialRecordsDelivered', 'requestTotalDelivered',
                   'matchingRecordsDelivered', 'recoveredRecords'} and value is not None}
    if not counts or validate_record_counts(normalize_content(answer.content), counts):
        return answer
    correction = invoke_llm(model, [*messages, SystemMessage(content=
        'Correct the reply using these authoritative collection facts: ' + json.dumps(facts)
        + '. Distinguish requested quantity from available and delivered counts. Do not invent records or claim success when zero were returned.')])
    if not validate_record_counts(normalize_content(correction.content), counts):
        raise LLMUnavailable('provider_error', 'Response contradicted verified record counts')
    return AIMessage(content=normalize_content(correction.content), id=answer.id)


def _check_groundedness(reply_text: str, messages: List[BaseMessage]) -> None:
    """Verify that numbers mentioned in reply are present in tool or RAG contexts."""
    if not reply_text:
        return

    # Extract all numbers from tool messages
    context_numbers: Set[str] = set()
    for m in messages:
        if isinstance(m, ToolMessage) or getattr(m, "type", "") == "tool":
            nums = re.findall(r"\b\d+\b", str(m.content))
            context_numbers.update(nums)

    # Numbers in assistant reply
    reply_numbers = set(re.findall(r"\b\d+\b", reply_text))

    # Allow harmless conversational numbers (years, pagination default 20, small ordinals)
    whitelist = {"1", "2", "3", "5", "10", "20", "50", "100", "2024", "2025", "2026"}
    ungrounded = (reply_numbers - context_numbers) - whitelist
    if ungrounded:
        logger.warning(
            "groundedness_warning: numbers %s in reply not grounded in tool/RAG outputs",
            sorted(ungrounded),
        )


def finalize(state: AgentState) -> Dict[str, Any]:
    """
    Cleans up dangling tool calls, generates final answer if needed,
    checks groundedness, and saves turn to database.
    """
    messages = list(state.get("messages", []))
    cleaned_messages: List[BaseMessage] = []

    # 1. Resolve any dangling tool calls from step-limit
    if messages:
        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", None) or []
        for call in tool_calls:
            call_id = call.get("id", "")
            cleaned_messages.append(
                ToolMessage(
                    content="not executed: step limit",
                    tool_call_id=call_id,
                )
            )

    all_msgs = messages + cleaned_messages

    # 2. If last message isn't a plain AI message, synthesize final answer
    last_msg = all_msgs[-1] if all_msgs else None
    needs_final_answer = (
        last_msg is None
        or isinstance(last_msg, ToolMessage)
        or bool(getattr(last_msg, "tool_calls", None))
    )

    final_reply_msg = None
    if needs_final_answer:
        model = get_chat_model()
        system_prompt = build_system_prompt(state)
        final_reply_msg = invoke_llm(model, [SystemMessage(content=system_prompt), *all_msgs], max_retries=1)
        all_msgs.append(final_reply_msg)

    # 3. Groundedness validation
    reply_text = getattr(final_reply_msg, "content", "") if final_reply_msg else getattr(last_msg, "content", "")
    # AIMessage.content can be a list of content blocks (e.g. from Gemini);
    # normalise to a plain string so regex operations in _check_groundedness work.
    reply_text = normalize_content(reply_text)
    search = state.get('last_search')
    if search and (final_reply_msg or isinstance(last_msg, AIMessage)):
        original = final_reply_msg or last_msg
        checked = grounded_reply(get_chat_model(), [SystemMessage(content=build_system_prompt(state)), *all_msgs],
            {'available': search.get('total', 0), 'returned': len(search.get('items') or [])}, original)
        if checked is not original:
            final_reply_msg = checked
            all_msgs[-1] = checked
            reply_text = normalize_content(checked.content)
    _check_groundedness(reply_text, all_msgs)

    # 4. State updates and persistence
    updated_state: AgentState = dict(state)
    updated_state["messages"] = all_msgs

    save_turn(updated_state)

    result: Dict[str, Any] = {}
    if cleaned_messages or final_reply_msg:
        to_add = []
        if cleaned_messages:
            to_add.extend(cleaned_messages)
        if final_reply_msg:
            to_add.append(final_reply_msg)
        result["messages"] = to_add

    return result
