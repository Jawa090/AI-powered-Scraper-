"""
agents/llm package
──────────────────
Multi-provider LLM abstraction layer.

Exports:
  LLMProvider              — abstract base class
  OpenAICompatibleProvider — concrete OpenAI-compatible HTTP provider
  FallbackLLMProvider      — ordered chain with per-provider fallback
  get_llm_provider         — factory function (use this everywhere)
  ProviderConfig           — per-provider configuration dataclass
  ProviderStatus           — READY | NOT_CONFIGURED | DISABLED
"""

from agents.llm.provider import LLMProvider
from agents.llm.openai_compatible import OpenAICompatibleProvider
from agents.llm.factory import FallbackLLMProvider, get_llm_provider
from agents.llm.config import ProviderConfig, ProviderStatus

__all__ = [
    "LLMProvider",
    "OpenAICompatibleProvider",
    "FallbackLLMProvider",
    "get_llm_provider",
    "ProviderConfig",
    "ProviderStatus",
]
