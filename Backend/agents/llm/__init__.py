"""
agents/llm/__init__.py
──────────────────────
Single-provider LLM abstraction layer.
All public API is in chat_model.py.
"""

from agents.llm.chat_model import (
    LLMUnavailable,
    get_chat_model,
    build_chat_model,
    invoke_llm,
    invoke_structured,
    probe,
    llm_health_check,
    clear_cache,
)

__all__ = [
    "LLMUnavailable",
    "get_chat_model",
    "build_chat_model",
    "invoke_llm",
    "invoke_structured",
    "probe",
    "llm_health_check",
    "clear_cache",
]
