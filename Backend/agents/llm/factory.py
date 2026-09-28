"""
agents/llm/factory.py
─────────────────────
LLM Provider Factory with Multi-Provider Fallback.

Responsibilities:
  - Build the ordered provider chain from environment configuration.
  - Return a FallbackLLMProvider that tries each configured provider in order.
  - Skip providers that are NOT_CONFIGURED (missing API key) without crashing.
  - Fall back to the deterministic QueryParser (via IntentEngine) on total failure.
  - Never expose API keys in logs.

Environment variables (see agents/llm/config.py for full documentation):
  LLM_PRIMARY_PROVIDER   — default "gemini"
  LLM_FALLBACK_PROVIDERS — default "deepseek,nvidia"
  GEMINI_API_KEY / LLM_API_KEY  — Gemini authentication
  DEEPSEEK_API_KEY              — DeepSeek authentication (optional)
  NVIDIA_API_KEY                — NVIDIA NIM authentication (optional)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type, TypeVar

import requests
from pydantic import BaseModel

from agents.llm.provider import LLMProvider
from agents.llm.openai_compatible import OpenAICompatibleProvider
from agents.llm.config import ProviderConfig, ProviderStatus, resolve_provider_chain

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# HTTP status codes that warrant trying the next provider (transient/provider issues)
_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

# Exception types that indicate provider unavailability (not application bugs)
_RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError)


class FallbackLLMProvider(LLMProvider):
    """
    A meta-provider that wraps an ordered list of configured providers and
    tries each one in sequence, skipping NOT_CONFIGURED providers silently
    and falling back on transient network/HTTP errors.

    This class intentionally does NOT catch ValidationError or ValueError from
    schema parsing — those indicate implementation bugs, not provider failures.
    """

    def __init__(self, providers: List[OpenAICompatibleProvider], configs: List[ProviderConfig]):
        if len(providers) != len(configs):
            raise ValueError("providers and configs lists must have the same length")
        self._providers = providers
        self._configs = configs

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        last_error: Optional[Exception] = None
        for provider, cfg in zip(self._providers, self._configs):
            if cfg.status != ProviderStatus.READY:
                logger.debug(
                    "Skipping provider '%s' (status=%s).",
                    cfg.name,
                    cfg.status.value,
                )
                continue
            try:
                return provider.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except _RETRYABLE_EXCEPTIONS as e:
                logger.warning(
                    "Provider '%s' failed with retryable error: %s. Trying next provider.",
                    cfg.name,
                    type(e).__name__,
                )
                last_error = e
                continue
        # All providers exhausted
        raise ConnectionError(
            f"All configured LLM providers exhausted. Last error: {last_error}"
        ) from last_error

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> T:
        last_error: Optional[Exception] = None
        for provider, cfg in zip(self._providers, self._configs):
            if cfg.status != ProviderStatus.READY:
                logger.debug(
                    "Skipping provider '%s' for structured generation (status=%s).",
                    cfg.name,
                    cfg.status.value,
                )
                continue
            try:
                return provider.generate_structured(
                    prompt=prompt,
                    schema=schema,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )
            except _RETRYABLE_EXCEPTIONS as e:
                logger.warning(
                    "Provider '%s' failed with retryable error (%s); trying configured fallback provider.",
                    cfg.name,
                    type(e).__name__,
                )
                last_error = e
                continue
        # All providers exhausted — raise to trigger IntentEngine QueryParser fallback
        raise ConnectionError(
            f"All configured LLM providers exhausted. Last error: {last_error}"
        ) from last_error

    def health_check(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        overall_available = False
        for provider, cfg in zip(self._providers, self._configs):
            if cfg.status != ProviderStatus.READY:
                results.append({
                    "provider": cfg.name,
                    "available": False,
                    "status": cfg.status.value,
                    "details": "Provider not configured (missing API key)",
                })
                continue
            check = provider.health_check()
            check["provider"] = cfg.name
            check["status"] = cfg.status.value
            results.append(check)
            if check.get("available"):
                overall_available = True
        return {
            "available": overall_available,
            "providers": results,
        }

    def get_provider_statuses(self) -> List[Dict[str, str]]:
        """Return a summary of all provider statuses (safe for logging/health APIs)."""
        return [
            {
                "name": cfg.name,
                "status": cfg.status.value,
                "model": cfg.model,
                "base_url": cfg.base_url,
            }
            for cfg in self._configs
        ]


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_cached_provider: Optional[LLMProvider] = None


def get_llm_provider(force_refresh: bool = False) -> LLMProvider:
    """
    Returns the configured LLMProvider instance.

    On first call (or when force_refresh=True), resolves the provider chain
    from environment variables and builds a FallbackLLMProvider.  Providers
    without API keys are skipped silently.

    If only a single provider is READY and the legacy code path is preferred,
    the inner OpenAICompatibleProvider is returned directly.
    """
    global _cached_provider
    if _cached_provider is not None and not force_refresh:
        return _cached_provider

    chain: List[ProviderConfig] = resolve_provider_chain()

    providers: List[OpenAICompatibleProvider] = []
    for cfg in chain:
        providers.append(
            OpenAICompatibleProvider(
                base_url=cfg.base_url,
                model=cfg.model,
                api_key=cfg.api_key,
                timeout=cfg.timeout,
            )
        )
        status_msg = (
            f"API key configured, model={cfg.model!r}"
            if cfg.is_ready
            else "NOT_CONFIGURED (no API key)"
        )
        logger.info("LLM provider '%s': %s", cfg.name, status_msg)

    if not providers:
        # Absolute fallback — no providers at all; IntentEngine will use QueryParser
        logger.warning("No LLM providers configured. Intent engine will use QueryParser fallback.")
        fallback = OpenAICompatibleProvider()
        _cached_provider = fallback
        return fallback

    _cached_provider = FallbackLLMProvider(providers=providers, configs=chain)
    return _cached_provider
