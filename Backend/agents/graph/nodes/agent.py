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

from agents.graph.nodes.load_context import build_system_prompt
from agents.graph.state import AgentState
from agents.graph.tools import ALL_TOOLS
from agents.llm.chat_model import get_chat_model, invoke_llm
from settings import settings

logger = logging.getLogger(__name__)


def _sanitize_trimmed_history(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Ensure the message history never begins with an orphan ToolMessage
    or splits an AIMessage from its corresponding ToolMessages.
    """
    if not messages:
        return []

    # If first message is a ToolMessage, drop it or find the preceding HumanMessage
    first_idx = 0
    while first_idx < len(messages) and isinstance(messages[first_idx], ToolMessage):
        first_idx += 1

    return messages[first_idx:]


def call_model(state: AgentState) -> Dict[str, Any]:
    """
    Executes the LLM turn with all tools bound.
    Propagates LLMUnavailable on unrecoverable/exhausted API errors.
    """
    system_text = build_system_prompt(state)
    system_msg = SystemMessage(content=system_text)

    history = state.get("messages", [])
    budget = getattr(settings, "HISTORY_TOKEN_BUDGET", 8000)

    try:
        # Trim messages to token budget, ensuring it starts on a human turn
        trimmed = trim_messages(
            history,
            max_tokens=budget,
            strategy="last",
            token_counter=len,  # message-count based bounding
            start_on="human",
            include_system=False,
        )
        safe_messages = _sanitize_trimmed_history(trimmed)
    except Exception as e:
        logger.debug("Message trimming fallback to full history: %s", e)
        safe_messages = history

    model = get_chat_model(tools=ALL_TOOLS)
    response = invoke_llm(model, [system_msg, *safe_messages])

    tool_steps = state.get("tool_steps", 0) + 1

    return {
        "messages": [response],
        "tool_steps": tool_steps,
    }
