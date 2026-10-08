"""DeepSeek, Gemini and OpenRouter fallbacks for plain, tool and typed AI calls.

Every provider uses bounded retries. Exhaustion returns the same HTTP 503 contract.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel

from settings import settings

logger = logging.getLogger(__name__)

# Default short backoff between retry attempts (configurable / mockable in tests)
_DEFAULT_RETRY_DELAY: float = 0.05

# Cache for chat model instances: (provider, model, tools_key) -> instance
_model_cache: dict[tuple, Any] = {}


class LLMUnavailable(Exception):
    """
    Exception raised when LLM service is unavailable, unconfigured,
    or has exhausted transient retry attempts.
    Conforms to Decision D4.
    """

    def __init__(self, reason: str, detail: str = ""):
        # reason: not_configured | timeout | auth_error | rate_limited | provider_error
        self.reason = reason
        self.detail = detail
        super().__init__(f"LLM unavailable ({reason}): {detail}" if detail else f"LLM unavailable ({reason})")

    @property
    def status_code(self) -> int:
        return 503

    def to_dict(self) -> dict:
        """Returns standard Decision D4 error payload."""
        return {
            "success": False,
            "error": {
                "code": "LLM_UNAVAILABLE",
                "reason": self.reason,
                "message": "The AI API is not responding. Please try again.",
            },
        }

    def to_response(self):
        """Converts to a FastAPI 503 JSONResponse."""
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=self.to_dict())


def _classify_error(exc: Exception) -> tuple[str, bool]:
    """
    Classify exception according to P8 error mapping table:
    | Error               | Reason         | Retry? |
    | auth / permission   | auth_error     | no     |
    | 429 / quota         | rate_limited   | yes    |
    | timeout / connection| timeout        | yes    |
    | 5xx                 | provider_error | yes    |
    | anything else       | provider_error | no     |

    Returns:
        tuple[str, bool]: (reason, is_retryable)
    """
    # 1. Explicit status code checks on exception attributes
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        status_code = getattr(exc, "code", None)
    if status_code is None:
        status_code = getattr(exc, "http_status", None)
    if status_code is None and hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        status_code = exc.response.status_code

    if isinstance(status_code, int):
        if status_code in (401, 403):
            return "auth_error", False
        if status_code == 429:
            return "rate_limited", True
        if status_code in (408, 504):
            return "timeout", True
        if 500 <= status_code <= 599:
            return "provider_error", True

    # 2. Known exception types
    try:
        import httpx
        if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            return "timeout", True
        if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
            return "timeout", True
    except ImportError:
        if isinstance(exc, TimeoutError):
            return "timeout", True

    if isinstance(exc, PermissionError):
        return "auth_error", False

    # Check google.genai error types if available
    try:
        from google.genai.errors import APIError, ServerError
        if isinstance(exc, ServerError):
            return "provider_error", True
        if isinstance(exc, APIError):
            code = getattr(exc, "code", None)
            if code in (401, 403):
                return "auth_error", False
            if code == 429:
                return "rate_limited", True
            if code in (408, 504):
                return "timeout", True
            if isinstance(code, int) and 500 <= code <= 599:
                return "provider_error", True
    except ImportError:
        pass

    # Check openai error types if available
    try:
        import openai
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return "auth_error", False
        if isinstance(exc, openai.RateLimitError):
            return "rate_limited", True
        if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
            return "timeout", True
        if isinstance(exc, openai.InternalServerError):
            return "provider_error", True
    except ImportError:
        pass

    # 3. Class name and message matching
    cls_name = exc.__class__.__name__.lower()
    msg = str(exc).lower()

    if any(k in cls_name for k in ("unauthenticated", "permissiondenied", "authenticationerror")):
        return "auth_error", False
    if any(k in cls_name for k in ("resourceexhausted", "ratelimit")):
        return "rate_limited", True
    if any(k in cls_name for k in ("deadlineexceeded", "timeout", "connecterror")):
        return "timeout", True
    if any(k in cls_name for k in ("internalservererror", "serviceunavailable", "badgateway")):
        return "provider_error", True

    if any(k in msg for k in ("unauthorized", "invalid api key", "permission denied", "forbidden", "401", "403")):
        return "auth_error", False
    if any(k in msg for k in ("429", "rate limit", "quota", "resource_exhausted", "resourceexhausted")):
        return "rate_limited", True
    if any(k in msg for k in ("timed out", "timeout", "deadline exceeded", "connection error", "connection reset", "connecterror")):
        return "timeout", True
    if any(k in msg for k in ("500", "502", "503", "504", "server error", "internal server error", "service unavailable", "bad gateway")):
        return "provider_error", True

    # Anything else: provider_error (with detail), no retry
    return "provider_error", False


def clear_cache() -> None:
    """Clear all cached chat model instances."""
    global _model_cache
    _model_cache.clear()


def _build_model(
    tools: Optional[Sequence[Any]] = None,
    force_refresh: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[int] = None,
    thinking_level: Optional[str] = None,
) -> BaseChatModel:
    """
    Instantiate and return the single configured chat model provider.
    Cached per tool-name tuple.
    Empty LLM_MODEL or LLM_API_KEY raises LLMUnavailable('not_configured').
    Strictly NO fallback chains (.with_fallbacks is never used).
    """
    global _model_cache

    prov = provider or getattr(settings, "LLM_PROVIDER", "")
    mdl = model or getattr(settings, "LLM_MODEL", "")
    key = api_key if api_key is not None else getattr(settings, "LLM_API_KEY", "")

    if not key or not mdl:
        raise LLMUnavailable(
            reason="not_configured",
            detail="LLM_MODEL or LLM_API_KEY is not configured.",
        )

    tools_key = None
    if tools:
        tools_key = tuple(sorted(getattr(t, "name", str(t)) for t in tools))

    cache_key = (prov, mdl, key, base_url, timeout, thinking_level, tools_key)

    if not force_refresh and cache_key in _model_cache:
        return _model_cache[cache_key]

    if prov == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        t_level = (
            thinking_level
            if thinking_level is not None
            else getattr(settings, "LLM_THINKING_LEVEL", "")
        )
        kwargs: dict[str, Any] = {
            "model": mdl,
            "google_api_key": key,
            "timeout": timeout if timeout is not None else getattr(settings, "LLM_TIMEOUT_S", 30),
            "max_retries": 0,
        }
        if t_level:
            budget_map = {"low": 1024, "medium": 4096, "high": 8192}
            budget = budget_map.get(str(t_level).lower())
            if budget is not None:
                kwargs["thinking_budget"] = budget

        chat_instance = ChatGoogleGenerativeAI(**kwargs)

    elif prov == "openai_compatible":
        from langchain_openai import ChatOpenAI

        b_url = base_url if base_url is not None else getattr(settings, "LLM_BASE_URL", "")
        if not b_url:
            raise LLMUnavailable(
                reason="not_configured",
                detail="LLM_BASE_URL is required when LLM_PROVIDER is 'openai_compatible'.",
            )

        chat_instance = ChatOpenAI(
            model=mdl,
            api_key=key,
            base_url=b_url,
            timeout=timeout if timeout is not None else getattr(settings, "LLM_TIMEOUT_S", 30),
            max_retries=0,
        )
    else:
        raise LLMUnavailable(
            reason="not_configured",
            detail=f"Unsupported LLM provider: '{prov}'",
        )

    # Bind tools if provided (no fallbacks!)
    if tools:
        chat_instance = chat_instance.bind_tools(tools)

    _model_cache[cache_key] = chat_instance
    return chat_instance


class ProviderChain:
    """Try DeepSeek, Gemini, then OpenRouter including construction failures."""
    def __init__(self, tools=None, timeout=None):
        self.tools, self.timeout = tools, timeout

    def _candidates(self):
        generic_provider = getattr(settings, 'LLM_PROVIDER', '')
        generic_url = getattr(settings, 'LLM_BASE_URL', '')
        generic_key = getattr(settings, 'LLM_API_KEY', '')
        generic_model = getattr(settings, 'LLM_MODEL', '')
        deep_key = getattr(settings, 'DEEPSEEK_API_KEY', '')
        # Preserve an explicitly configured compatible endpoint as the primary.
        yield ('deepseek', 'openai_compatible', getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-chat') if deep_key else generic_model,
            deep_key or (generic_key if generic_provider == 'openai_compatible' else ''),
            'https://api.deepseek.com' if deep_key else generic_url)
        yield ('gemini', 'gemini', getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash') if getattr(settings, 'GEMINI_API_KEY', '') else (generic_model if generic_provider == 'gemini' else getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')),
            getattr(settings, 'GEMINI_API_KEY', '') or (generic_key if generic_provider == 'gemini' else ''), '')
        yield ('openrouter', 'openai_compatible', getattr(settings, 'OPENROUTER_MODEL', ''),
            getattr(settings, 'OPENROUTER_API_KEY', ''), 'https://openrouter.ai/api/v1')

    def invoke(self, messages, schema=None, **kwargs):
        failures = []
        for name, provider, model, key, base in self._candidates():
            if not key or not model:
                failures.append((name, 'not_configured'))
                continue
            try:
                instance = _build_model(provider=provider, model=model, api_key=key,
                    base_url=base, tools=self.tools, timeout=self.timeout)
                if schema is not None:
                    instance = _get_structured_model(instance, schema)
                started = time.perf_counter()
                response = _invoke_one(instance, messages, **kwargs)
                if schema is None and not getattr(response, 'tool_calls', None) and not str(getattr(response, 'content', '')).strip():
                    raise LLMUnavailable('provider_error', 'Empty provider response')
                logger.info('provider_call', extra={'provider': name, 'model': model,
                    'latency_ms': round((time.perf_counter() - started)*1000, 2), 'structured': schema is not None})
                return response
            except Exception as exc:
                reason = exc.reason if isinstance(exc, LLMUnavailable) else _classify_error(exc)[0]
                failures.append((name, reason))
                logger.warning('AI provider %s unavailable: %s', name, reason)
        reason = next((reason for _, reason in reversed(failures) if reason != 'not_configured'), 'not_configured')
        raise LLMUnavailable(reason, 'All configured providers exhausted')


def get_chat_model(tools=None, force_refresh=False, provider=None, model=None, api_key=None,
                   base_url=None, timeout=None, thinking_level=None):
    if provider is not None or model is not None or api_key is not None:
        return _build_model(tools, force_refresh, provider, model, api_key, base_url, timeout, thinking_level)
    return ProviderChain(tools, timeout)


def _invoke_one(model, messages, max_retries=None, retry_delay=None, **kwargs):
    retries = max_retries if max_retries is not None else settings.LLM_MAX_RETRIES
    delay = retry_delay if retry_delay is not None else _DEFAULT_RETRY_DELAY
    for attempt in range(retries + 1):
        try:
            return model.invoke(messages, **kwargs)
        except LLMUnavailable:
            raise
        except Exception as exc:
            reason, transient = _classify_error(exc)
            if transient and attempt < retries:
                time.sleep(delay)
                continue
            raise LLMUnavailable(reason, 'Provider invocation failed') from exc


def invoke_llm(model, messages, max_retries=None, retry_delay=None, **kwargs):
    if isinstance(model, ProviderChain):
        return model.invoke(messages, max_retries=max_retries, retry_delay=retry_delay, **kwargs)
    return _invoke_one(model, messages, max_retries=max_retries, retry_delay=retry_delay, **kwargs)


def _get_structured_model(model, schema):
    if model.__class__.__name__ == 'ChatOpenAI':
        return model.with_structured_output(schema, method='function_calling')
    return model.with_structured_output(schema)


def invoke_structured(schema, messages, tools=None, model=None, max_retries=None, retry_delay=None, **kwargs):
    model = model if model is not None else get_chat_model(tools=tools)
    if isinstance(model, ProviderChain):
        return model.invoke(messages, schema=schema, max_retries=max_retries, retry_delay=retry_delay, **kwargs)
    try:
        structured = _get_structured_model(model, schema)
        return _invoke_one(structured, messages, max_retries=max_retries, retry_delay=retry_delay, **kwargs)
    except LLMUnavailable:
        raise
    except Exception as exc:
        raise LLMUnavailable(_classify_error(exc)[0], 'Structured output failed') from exc


def probe(timeout: int = 5) -> dict:
    """
    Probe the configured LLM provider with a 1-token / test invocation.
    Returns: {provider, model, reachable, latency_ms, reason}
    Never returns credentials or API keys.
    """
    provider = getattr(settings, "LLM_PROVIDER", "")
    model_name = getattr(settings, "LLM_MODEL", "")
    api_key = getattr(settings, "LLM_API_KEY", "")

    if not any(key and model for _, _, model, key, _ in ProviderChain()._candidates()):
        return {
            "provider": provider,
            "model": model_name,
            "reachable": False,
            "latency_ms": 0.0,
            "reason": "not_configured",
        }

    t0 = time.perf_counter()
    try:
        model = get_chat_model(timeout=timeout)
        from langchain_core.messages import HumanMessage
        invoke_llm(model, [HumanMessage(content="hi")], max_retries=0)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "provider": provider,
            "model": model_name,
            "reachable": True,
            "latency_ms": latency_ms,
            "reason": "",
        }
    except LLMUnavailable as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "provider": provider,
            "model": model_name,
            "reachable": False,
            "latency_ms": latency_ms,
            "reason": exc.reason,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        reason, _ = _classify_error(exc)
        return {
            "provider": provider,
            "model": model_name,
            "reachable": False,
            "latency_ms": latency_ms,
            "reason": reason,
        }


def llm_health_check(probe_mode: bool = False) -> dict:
    """
    Health check for LLM provider configuration and availability.
    If probe_mode=True, calls probe() to verify reachability.
    Never exposes API keys or secrets.
    """
    if probe_mode:
        return probe()

    return {
        "provider": getattr(settings, "LLM_PROVIDER", ""),
        "model": getattr(settings, "LLM_MODEL", ""),
        "configured": any(key and model for _, _, model, key, _ in ProviderChain()._candidates()),
        "providers": [{'provider': name, 'model': model, 'configured': bool(key and model)}
            for name, _, model, key, _ in ProviderChain()._candidates()],
    }


def build_chat_model(tools: Optional[Sequence[Any]] = None) -> BaseChatModel:
    """Compatibility alias for get_chat_model."""
    return get_chat_model(tools=tools)
