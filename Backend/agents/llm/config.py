"""
agents/llm/config.py
────────────────────
Per-provider configuration resolution.

Reads environment variables for each LLM provider without ever hard-coding
secrets.  Providers whose API key is absent are marked NOT_CONFIGURED so they
can be gracefully skipped during fallback without crashing the application.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ProviderStatus(str, Enum):
    """Readiness status of a single provider instance."""

    READY = "READY"                # API key present, URL set — can be used
    NOT_CONFIGURED = "NOT_CONFIGURED"  # Missing API key — skip silently
    DISABLED = "DISABLED"          # Explicitly disabled by config


@dataclass
class ProviderConfig:
    """
    Resolved configuration for a single LLM provider.
    All secrets are sourced from environment variables; none are hard-coded.
    """

    name: str                          # Human label: "gemini", "deepseek", "nvidia"
    base_url: str                      # OpenAI-compatible completions base URL
    model: str                         # Model name sent to the API
    api_key: str                       # Bearer token; empty string → NOT_CONFIGURED
    timeout: int                       # HTTP request timeout in seconds
    status: ProviderStatus = field(init=False)

    def __post_init__(self) -> None:
        key = (self.api_key or "").strip()
        if not key or key.upper() in ("", "EMPTY", "YOUR_KEY_HERE", "PLACEHOLDER"):
            self.status = ProviderStatus.NOT_CONFIGURED
        else:
            self.status = ProviderStatus.READY

    @property
    def is_ready(self) -> bool:
        return self.status == ProviderStatus.READY

    def masked_key(self) -> str:
        """Return a safely masked representation of the API key for logging."""
        key = (self.api_key or "").strip()
        if not key or self.status != ProviderStatus.READY:
            return "<not set>"
        if len(key) <= 8:
            return "****"
        return key[:4] + "****" + key[-4:]


# ---------------------------------------------------------------------------
# Individual provider resolvers
# ---------------------------------------------------------------------------

def _gemini_config() -> ProviderConfig:
    """
    Gemini uses the OpenAI-compatible endpoint.
    Primary env vars: GEMINI_API_KEY, GEMINI_BASE_URL, GEMINI_MODEL.
    Falls back to legacy LLM_* vars so existing .env continues to work.
    """
    api_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("LLM_API_KEY", "")
    )
    base_url = (
        os.getenv("GEMINI_BASE_URL")
        or os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    )
    model = (
        os.getenv("GEMINI_MODEL")
        or os.getenv("LLM_MODEL", "gemini-2.0-flash")
    )
    timeout = int(
        os.getenv("GEMINI_TIMEOUT")
        or os.getenv("LLM_TIMEOUT", "30")
    )
    return ProviderConfig(
        name="gemini",
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key,
        timeout=timeout,
    )


def _deepseek_config() -> ProviderConfig:
    """
    DeepSeek uses an OpenAI-compatible endpoint.
    If DEEPSEEK_API_KEY is absent the provider is marked NOT_CONFIGURED.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    timeout = int(os.getenv("DEEPSEEK_TIMEOUT", "30"))
    return ProviderConfig(
        name="deepseek",
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key,
        timeout=timeout,
    )


def _nvidia_config() -> ProviderConfig:
    """
    NVIDIA NIM uses an OpenAI-compatible endpoint.
    If NVIDIA_API_KEY is absent the provider is marked NOT_CONFIGURED.
    """
    api_key = os.getenv("NVIDIA_API_KEY", "")
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
    timeout = int(os.getenv("NVIDIA_TIMEOUT", "30"))
    return ProviderConfig(
        name="nvidia",
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Provider ordering helpers
# ---------------------------------------------------------------------------

_RESOLVER_MAP = {
    "gemini": _gemini_config,
    "deepseek": _deepseek_config,
    "nvidia": _nvidia_config,
}


def get_provider_config(name: str) -> ProviderConfig:
    """Return ProviderConfig for a named provider."""
    name = name.lower().strip()
    resolver = _RESOLVER_MAP.get(name)
    if resolver is None:
        # Unknown provider — return a NOT_CONFIGURED placeholder so the
        # factory can skip it gracefully.
        return ProviderConfig(
            name=name,
            base_url="",
            model="",
            api_key="",
            timeout=30,
        )
    return resolver()


def resolve_provider_chain() -> List[ProviderConfig]:
    """
    Build the ordered provider chain from environment variables.

    LLM_PRIMARY_PROVIDER  — primary provider name (default: gemini)
    LLM_FALLBACK_PROVIDERS — comma-separated fallback names (default: deepseek,nvidia)

    Providers that are NOT_CONFIGURED are included in the chain so they can be
    logged as skipped rather than silently omitted from audit trails.
    """
    primary_name = os.getenv("LLM_PRIMARY_PROVIDER", "gemini").lower().strip()

    fallback_raw = os.getenv("LLM_FALLBACK_PROVIDERS", "deepseek,nvidia")
    fallback_names = [n.strip().lower() for n in fallback_raw.split(",") if n.strip()]

    # Legacy compatibility: if LLM_PROVIDER is set and points to something
    # other than "gemini" or "openai_compatible", honour it as primary.
    legacy = os.getenv("LLM_PROVIDER", "").lower().strip()
    if legacy and legacy not in ("", "openai_compatible", "openai", "ollama", "vllm", "localai"):
        primary_name = legacy

    seen: set = set()
    chain: List[ProviderConfig] = []

    for name in [primary_name] + fallback_names:
        if name in seen:
            continue
        seen.add(name)
        chain.append(get_provider_config(name))

    return chain
