"""
agents/llm/config.py
────────────────────
Multi-provider LLM configuration adapter for DataOps AI Platform.
Provides ProviderConfig mappings using centralized settings.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List
from settings import settings


class ProviderStatus(str, Enum):
    READY = "READY"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    ERROR = "ERROR"


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key: str
    timeout: int = 30

    @property
    def status(self) -> ProviderStatus:
        if self.name == "gemini":
            if self.api_key and self.api_key.strip():
                return ProviderStatus.READY
            return ProviderStatus.NOT_CONFIGURED
        elif self.name == "deepseek":
            if self.api_key and self.api_key.strip():
                return ProviderStatus.READY
            return ProviderStatus.NOT_CONFIGURED
        elif self.name == "nvidia":
            if self.api_key and self.api_key.strip():
                return ProviderStatus.READY
            return ProviderStatus.NOT_CONFIGURED
        return ProviderStatus.NOT_CONFIGURED

    @property
    def is_ready(self) -> bool:
        return self.status == ProviderStatus.READY


def _gemini_config() -> ProviderConfig:
    return ProviderConfig(
        name="gemini",
        base_url=(settings.LLM_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai/").rstrip("/"),
        model=settings.LLM_MODEL or "gemini-2.0-flash",
        api_key=settings.LLM_API_KEY,
        timeout=settings.LLM_TIMEOUT_S,
    )


def _deepseek_config() -> ProviderConfig:
    return ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="",
        timeout=30,
    )


def _nvidia_config() -> ProviderConfig:
    return ProviderConfig(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        model="meta/llama-3.1-8b-instruct",
        api_key="",
        timeout=30,
    )


_RESOLVER_MAP = {
    "gemini": _gemini_config,
    "deepseek": _deepseek_config,
    "nvidia": _nvidia_config,
}


def get_provider_config(name: str) -> ProviderConfig:
    name = name.lower().strip()
    resolver = _RESOLVER_MAP.get(name)
    if resolver is None:
        return ProviderConfig(
            name=name,
            base_url="",
            model="",
            api_key="",
            timeout=30,
        )
    return resolver()


def resolve_provider_chain() -> List[ProviderConfig]:
    primary_name = settings.LLM_PROVIDER.lower().strip()
    return [get_provider_config(primary_name)]
