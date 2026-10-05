"""
agents/llm/chat_models.py
──────────────────────────
LangChain Chat Model factory with seamless Gemini ↔ DeepSeek fallback.

This replaces the custom OpenAICompatibleProvider for the new LangGraph agent.
The old provider code (factory.py, openai_compatible.py) remains for legacy
nodes until Phase 14 migration is complete.

Usage:
    from agents.llm.chat_models import build_chat_model, get_chat_model

    # With tools (for agent graph):
    model = build_chat_model(tools=[search_leads, propose_scrape])

    # Without tools (for simple generation):
    model = build_chat_model()
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _get_env(key: str, default: str = "") -> str:
    """Read from settings or active environment override, strip whitespace."""
    if key in os.environ:
        return os.environ[key].strip()
    from settings import settings
    val = getattr(settings, key, None)
    if val is None:
        val = default
    return str(val).strip()


def build_chat_model(tools: Optional[Sequence[Any]] = None):
    """
    Build a LangChain chat model with automatic fallback.

    - Primary: ChatGoogleGenerativeAI (Gemini) — uses GEMINI_API_KEY
    - Fallback: ChatOpenAI (DeepSeek) — uses DEEPSEEK_API_KEY

    If tools are provided, they are bound BEFORE wrapping with fallbacks
    (each model gets its own tool binding).

    Returns a single model object. If only one provider is configured,
    returns that provider directly. If both are configured, returns
    primary.with_fallbacks([fallback]).

    Raises EnvironmentError if NO provider has an API key.
    """
    models = []

    # ── Gemini (primary) ──────────────────────────────────────────────────
    gemini_key = _get_env("GEMINI_API_KEY") or _get_env("LLM_API_KEY")
    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            gemini_model = _get_env("GEMINI_MODEL") or _get_env("LLM_MODEL", "gemini-2.0-flash")
            gemini_timeout = int(_get_env("GEMINI_TIMEOUT") or _get_env("LLM_TIMEOUT", "30"))

            primary = ChatGoogleGenerativeAI(
                model=gemini_model,
                google_api_key=gemini_key,
                timeout=gemini_timeout,
                max_retries=1,
                temperature=0,
            )
            models.append(("gemini", primary))
            logger.info("LLM provider 'gemini' configured: model=%s", gemini_model)
        except Exception as e:
            logger.warning("Failed to initialize Gemini provider: %s", e)

    # ── DeepSeek (fallback) ───────────────────────────────────────────────
    deepseek_key = _get_env("DEEPSEEK_API_KEY")
    if deepseek_key:
        try:
            from langchain_openai import ChatOpenAI

            deepseek_model = _get_env("DEEPSEEK_MODEL", "deepseek-chat")
            deepseek_base = _get_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            deepseek_timeout = int(_get_env("DEEPSEEK_TIMEOUT", "30"))

            # DeepSeek is OpenAI-compatible
            fallback = ChatOpenAI(
                model=deepseek_model,
                base_url=deepseek_base,
                api_key=deepseek_key,
                timeout=deepseek_timeout,
                max_retries=1,
                temperature=0,
            )
            models.append(("deepseek", fallback))
            logger.info("LLM provider 'deepseek' configured: model=%s", deepseek_model)
        except Exception as e:
            logger.warning("Failed to initialize DeepSeek provider: %s", e)

    # ── NVIDIA (optional extra fallback) ──────────────────────────────────
    nvidia_key = _get_env("NVIDIA_API_KEY")
    if nvidia_key:
        try:
            from langchain_openai import ChatOpenAI

            nvidia_model = _get_env("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
            nvidia_base = _get_env("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            nvidia_timeout = int(_get_env("NVIDIA_TIMEOUT", "30"))

            fb = ChatOpenAI(
                model=nvidia_model,
                base_url=nvidia_base,
                api_key=nvidia_key,
                timeout=nvidia_timeout,
                max_retries=1,
                temperature=0,
            )
            models.append(("nvidia", fb))
            logger.info("LLM provider 'nvidia' configured: model=%s", nvidia_model)
        except Exception as e:
            logger.warning("Failed to initialize NVIDIA provider: %s", e)

    if not models:
        raise EnvironmentError(
            "No LLM provider configured. Set at least one of: "
            "GEMINI_API_KEY, DEEPSEEK_API_KEY, NVIDIA_API_KEY in your .env file."
        )

    # ── Bind tools if provided ────────────────────────────────────────────
    if tools:
        bound_models = []
        for name, m in models:
            try:
                bound_models.append((name, m.bind_tools(tools)))
            except Exception as e:
                logger.warning("Provider '%s' failed to bind tools: %s", name, e)
                # Still include without tools as last resort
                bound_models.append((name, m))
        models = bound_models

    # ── Build fallback chain ──────────────────────────────────────────────
    if len(models) == 1:
        logger.info("Single LLM provider active: %s", models[0][0])
        return models[0][1]

    primary_name, primary_model = models[0]
    fallback_names = [name for name, _ in models[1:]]
    fallback_models = [m for _, m in models[1:]]

    logger.info(
        "LLM fallback chain: %s → %s",
        primary_name,
        " → ".join(fallback_names),
    )
    return primary_model.with_fallbacks(fallback_models)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cached_chat_model = None
_cached_chat_model_with_tools = None


def get_chat_model(tools: Optional[Sequence[Any]] = None, force_refresh: bool = False):
    """
    Return a cached chat model instance.

    If tools are provided, returns a tools-bound version (cached separately).
    """
    global _cached_chat_model, _cached_chat_model_with_tools

    if tools:
        if _cached_chat_model_with_tools is None or force_refresh:
            _cached_chat_model_with_tools = build_chat_model(tools=tools)
        return _cached_chat_model_with_tools
    else:
        if _cached_chat_model is None or force_refresh:
            _cached_chat_model = build_chat_model()
        return _cached_chat_model


def llm_health_check() -> dict:
    """
    Health check for LLM providers.

    Returns provider info and reachability without exposing keys.
    """
    providers = []

    gemini_key = _get_env("GEMINI_API_KEY") or _get_env("LLM_API_KEY")
    providers.append({
        "provider": "gemini",
        "model": _get_env("GEMINI_MODEL") or _get_env("LLM_MODEL", "gemini-2.0-flash"),
        "configured": bool(gemini_key),
        "role": "primary",
    })

    deepseek_key = _get_env("DEEPSEEK_API_KEY")
    providers.append({
        "provider": "deepseek",
        "model": _get_env("DEEPSEEK_MODEL", "deepseek-chat"),
        "configured": bool(deepseek_key),
        "role": "fallback",
    })

    nvidia_key = _get_env("NVIDIA_API_KEY")
    if nvidia_key:
        providers.append({
            "provider": "nvidia",
            "model": _get_env("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
            "configured": True,
            "role": "fallback",
        })

    any_configured = any(p["configured"] for p in providers)

    # Quick reachability test if requested via ?probe=true (done by caller)
    return {
        "available": any_configured,
        "providers": providers,
    }
