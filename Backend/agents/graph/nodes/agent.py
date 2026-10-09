"""
agents/graph/nodes/agent.py
───────────────────────────
Primary model invocation node for the LangGraph agent graph.
Complies with Phase P11.4 agent / call_model.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.messages.utils import count_tokens_approximately

from agents.graph.nodes.load_context import build_system_prompt
from agents.graph.state import AgentState
from agents.graph.tools import ALL_TOOLS
from agents.llm.chat_model import get_chat_model, invoke_llm
from settings import settings

logger = logging.getLogger(__name__)


def _required_scrape_proposal(state):
    """Prepare a real confirmation instead of asking permission to propose one."""
    from Database.search import SearchCriteria
    from scrappers.controller import list_scrapers, check_ready, validate_params
    from scrappers.base import InvalidScrapeParams
    history = state.get('messages') or []
    if not history or not isinstance(history[-1], ToolMessage):
        return None
    last = history[-1]
    calls = [call for message in history if isinstance(message, AIMessage)
             for call in (message.tool_calls or [])]
    if not any(call['id'] == last.tool_call_id and call['name'] == 'search_leads' for call in calls):
        return None
    evidence = state.get('last_search') or {}
    criteria = SearchCriteria.from_slots(state.get('slots'))
    if (not evidence or evidence.get('error') or evidence.get('sufficient')
            or evidence.get('turn_id') != state.get('turn_id')
            or evidence.get('slots_hash') != criteria.fingerprint()):
        return None
    quantity = max(1, criteria.quantity - evidence.get('total', 0))
    candidates = [meta for meta in list_scrapers()
                  if meta.record_kind == criteria.record_kind
                  and (not criteria.source or meta.id == criteria.source)]
    eligible = []
    for meta in candidates:
        if not check_ready(meta.id)[0]:
            continue
        try:
            validate_params(meta.id, {'limit': quantity, 'keyword': criteria.category,
                                      'us_state': criteria.us_state})
        except InvalidScrapeParams:
            continue
        eligible.append(meta)
    # Respect an explicit source; otherwise use the first compatible ready adapter.
    # Its name and exact filters are shown before the user starts it.
    if not eligible:
        return None
    import uuid
    return AIMessage(content='', tool_calls=[{'id': 'proposal-' + uuid.uuid4().hex,
        'name': 'propose_scrape', 'args': {'source': eligible[0].id, 'quantity': quantity}}])


def _sanitize_trimmed_history(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Ensure the message history never begins with an orphan ToolMessage
    or splits an AIMessage from its corresponding ToolMessages.
    """
    safe = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if isinstance(message, ToolMessage):
            index += 1
            continue
        calls = getattr(message, 'tool_calls', []) or []
        if calls:
            end = index + 1
            results = []
            while end < len(messages) and isinstance(messages[end], ToolMessage):
                results.append(messages[end]); end += 1
            if {call['id'] for call in calls} == {result.tool_call_id for result in results}:
                safe.extend([message, *results])
            index = end
        else:
            safe.append(message); index += 1
    return safe


def bounded_history(history, budget):
    try:
        trimmed = trim_messages(history, max_tokens=budget, strategy='last',
            token_counter=count_tokens_approximately, start_on='human', include_system=False)
    except Exception:
        trimmed, used = [], 0
        for message in reversed(history):
            size = max(1, len(str(message.content)) // 3)
            if used + size > budget:
                break
            trimmed.insert(0, message); used += size
    if not trimmed and history:
        # A single very long input must remain bounded as well.
        last_human = next((message for message in reversed(history) if isinstance(message, HumanMessage)), None)
        if last_human:
            trimmed = [HumanMessage(content=str(last_human.content)[-budget * 3:])]
    return _sanitize_trimmed_history(trimmed)


def call_model(state: AgentState) -> Dict[str, Any]:
    """
    Executes the LLM turn with all tools bound.
    Propagates LLMUnavailable on unrecoverable/exhausted API errors.
    """
    interpretation = {}
    if state.get('tool_steps', 0) == 0 and not state.get('intent_interpreted'):
        from agents.graph.nodes.gather_requirements import interpret_request
        interpretation = interpret_request(state)
    working_state = {**state, **interpretation}
    from agents.graph.nodes.gather_requirements import missing_requirements
    is_records = working_state.get('request_intent') == 'records'
    record_missing = missing_requirements(working_state.get('slots')) if is_records else []
    current_missing = record_missing if is_records else (working_state.get('missing_requirements') or (missing_requirements(working_state.get('slots')) if working_state.get('slots') else []))
    working_state['missing_requirements'] = current_missing
    if is_records and not record_missing:
        targets = (working_state.get('slots') or {}).get('detail_record_ids') or []
        if targets and not working_state.get('served_lead_ids'):
            import uuid
            return {**interpretation, 'messages': [AIMessage(content='', tool_calls=[
                {'id': 'detail-' + uuid.uuid4().hex, 'name': 'get_lead', 'args': {'lead_id': lid}} for lid in targets])],
                'missing_requirements': [], 'requirements_met': True, 'tool_steps': state.get('tool_steps', 0) + 1}
        proposal = _required_scrape_proposal(working_state)
        if proposal is not None:
            return {**interpretation, 'messages': [proposal], 'missing_requirements': [],
                    'requirements_met': True, 'tool_steps': state.get('tool_steps', 0) + 1}
    system_text = build_system_prompt(working_state)
    system_msg = SystemMessage(content=system_text)

    history = state.get("messages", [])
    budget = getattr(settings, "HISTORY_TOKEN_BUDGET", 8000)

    safe_messages = bounded_history(history, budget)

    greeting = working_state.get('request_intent') == 'greeting'
    is_clarifying = is_records and bool(record_missing)
    if greeting:
        # Plain greeting calls must not replay prior tool protocol messages.
        safe_messages = [message for message in safe_messages
                         if not isinstance(message, ToolMessage) and not getattr(message, 'tool_calls', None)]
    if is_clarifying:
        # Plain clarification calls retain recent conversational user and assistant messages.
        # Exclude prior tool executions so old completed searches do not steer a clarification into inventing tool calls.
        last_tool_idx = max(
            (i for i, m in enumerate(history) if isinstance(m, ToolMessage) or getattr(m, 'tool_calls', None)),
            default=-1,
        )
        if last_tool_idx >= 0:
            conversational = history[last_tool_idx + 1:]
        else:
            conversational = history
        safe_messages = [
            m for m in conversational
            if isinstance(m, (HumanMessage, AIMessage)) and not getattr(m, 'tool_calls', None)
        ]
        while safe_messages and isinstance(safe_messages[0], AIMessage):
            safe_messages.pop(0)
        if not safe_messages:
            last_human = next((m for m in reversed(history) if isinstance(m, HumanMessage)), None)
            if last_human:
                safe_messages = [last_human]
        safe_messages = bounded_history(safe_messages, budget)
    from agents.graph.tools.search import get_lead
    tools = [get_lead] if (working_state.get('slots') or {}).get('detail_record_ids') else ALL_TOOLS
    model = get_chat_model() if (greeting or is_clarifying) else get_chat_model(tools=tools)
    response = invoke_llm(model, [system_msg, *safe_messages])

    tool_steps = state.get("tool_steps", 0) + 1

    return {
        **interpretation,
        **({'slots': dict(working_state['slots'])} if working_state.get('slots') else {}),
        'missing_requirements': current_missing,
        'requirements_met': is_records and not record_missing,
        **({'decision': 'CLARIFY'} if is_clarifying else {}),
        **({'decision': 'NONE'} if greeting else {}),
        "messages": [response],
        "tool_steps": tool_steps,
    }
