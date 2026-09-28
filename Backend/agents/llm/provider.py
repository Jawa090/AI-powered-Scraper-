"""
agents/llm/provider.py
──────────────────────
Abstract Base Class for LLM Providers.
Decouples the agent system from any single commercial or open-source model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """
    Abstract interface for LLM interaction.
    Any provider (OpenAI-compatible, Ollama, vLLM, LocalAI, etc.) must implement this interface.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generates free-form text response from the model.
        """
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        """
        Generates structured output validated against a Pydantic model schema.
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Verifies connectivity and readiness of the LLM endpoint.
        Returns a dict: {"available": bool, "provider": str, "model": str, "details": str}
        """
        pass
