"""
Backend/settings.py — Centralized configuration management with strict validation.
Complies with P1.1 (no defaults in code, explicit type conversion, collects all errors into ConfigError).
"""
import os
import sys
from pathlib import Path
from typing import List, Optional

try:
    import _paths
except ImportError:
    try:
        from Backend import _paths
    except ImportError:
        pass

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent


class ConfigError(Exception):
    """Raised when application configuration is missing or invalid."""
    pass


def _parse_bool(val: str, field_name: str, errors: List[str]) -> bool:
    if val is None:
        errors.append(f"{field_name}: missing required boolean value ('true' or 'false')")
        return False
    lower = str(val).strip().lower()
    if lower == "true":
        return True
    elif lower == "false":
        return False
    errors.append(f"{field_name}: invalid boolean '{val}' (must be 'true' or 'false')")
    return False


def _parse_int(val: str, field_name: str, errors: List[str], min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    if val is None or str(val).strip() == "":
        errors.append(f"{field_name}: missing required integer value")
        return 0
    try:
        num = int(str(val).strip())
        if min_val is not None and num < min_val:
            errors.append(f"{field_name}: value {num} must be >= {min_val}")
        if max_val is not None and num > max_val:
            errors.append(f"{field_name}: value {num} must be <= {max_val}")
        return num
    except ValueError:
        errors.append(f"{field_name}: '{val}' is not a valid integer")
        return 0


def _parse_float(val: str, field_name: str, errors: List[str], min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    if val is None or str(val).strip() == "":
        errors.append(f"{field_name}: missing required float value")
        return 0.0
    try:
        num = float(str(val).strip())
        if min_val is not None and num < min_val:
            errors.append(f"{field_name}: value {num} must be >= {min_val}")
        if max_val is not None and num > max_val:
            errors.append(f"{field_name}: value {num} must be <= {max_val}")
        return num
    except ValueError:
        errors.append(f"{field_name}: '{val}' is not a valid float")
        return 0.0


class Settings:
    """Validated settings container for DataOps AI Platform."""

    def __init__(self, raw: dict):
        errors: List[str] = []

        # Database
        self.DATABASE_URL: str = (raw.get("DATABASE_URL") or "").strip()
        if not self.DATABASE_URL.startswith("postgresql+psycopg://"):
            errors.append(f"DATABASE_URL: must start with 'postgresql+psycopg://' (got '{self.DATABASE_URL[:25]}...')")

        self.CHECKPOINT_DB_URL: str = (raw.get("CHECKPOINT_DB_URL") or "").strip()
        if not self.CHECKPOINT_DB_URL.startswith("postgresql://"):
            errors.append(f"CHECKPOINT_DB_URL: must start with 'postgresql://' (got '{self.CHECKPOINT_DB_URL[:20]}...')")

        self.ENVIRONMENT: str = (raw.get("ENVIRONMENT") or "").strip()
        if self.ENVIRONMENT not in ("development", "test", "production"):
            errors.append(f"ENVIRONMENT: must be 'development', 'test', or 'production' (got '{self.ENVIRONMENT}')")

        self.LOG_LEVEL: str = (raw.get("LOG_LEVEL") or "").strip().upper()
        if self.LOG_LEVEL not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            errors.append(f"LOG_LEVEL: must be 'DEBUG', 'INFO', 'WARNING', or 'ERROR' (got '{self.LOG_LEVEL}')")

        raw_cors = raw.get("CORS_ORIGINS")
        if not raw_cors or not str(raw_cors).strip():
            errors.append("CORS_ORIGINS: must be a non-empty comma-separated list of origins")
            self.CORS_ORIGINS: List[str] = []
        else:
            self.CORS_ORIGINS = [orig.strip() for orig in str(raw_cors).split(",") if orig.strip()]
            if len(self.CORS_ORIGINS) < 1:
                errors.append("CORS_ORIGINS: must have >= 1 origin")

        self.API_HOST: str = (raw.get("API_HOST") or "").strip()
        if not self.API_HOST:
            errors.append("API_HOST: must be a non-empty string")

        self.API_PORT: int = _parse_int(raw.get("API_PORT"), "API_PORT", errors, min_val=1, max_val=65535)

        # Built-in accounts
        self.AUTH_ADMIN_USERNAME: str = (raw.get("AUTH_ADMIN_USERNAME") or "").strip()
        if not self.AUTH_ADMIN_USERNAME:
            errors.append("AUTH_ADMIN_USERNAME: must not be empty")

        self.AUTH_ADMIN_PASSWORD: str = raw.get("AUTH_ADMIN_PASSWORD", "")
        if not self.AUTH_ADMIN_PASSWORD:
            errors.append("AUTH_ADMIN_PASSWORD: must not be empty")

        self.AUTH_USER_USERNAME: str = (raw.get("AUTH_USER_USERNAME") or "").strip()
        if not self.AUTH_USER_USERNAME:
            errors.append("AUTH_USER_USERNAME: must not be empty")

        self.AUTH_USER_PASSWORD: str = raw.get("AUTH_USER_PASSWORD", "")
        if not self.AUTH_USER_PASSWORD:
            errors.append("AUTH_USER_PASSWORD: must not be empty")

        if self.AUTH_ADMIN_USERNAME and self.AUTH_USER_USERNAME:
            if self.AUTH_ADMIN_USERNAME.lower() == self.AUTH_USER_USERNAME.lower():
                errors.append(f"AUTH_ADMIN_USERNAME ('{self.AUTH_ADMIN_USERNAME}') and AUTH_USER_USERNAME ('{self.AUTH_USER_USERNAME}') must differ (case-insensitive)")

        self.JWT_SECRET: str = raw.get("JWT_SECRET", "")
        if len(self.JWT_SECRET) < 32:
            errors.append(f"JWT_SECRET: must be >= 32 characters long (got {len(self.JWT_SECRET)})")

        self.JWT_EXPIRE_HOURS: int = _parse_int(raw.get("JWT_EXPIRE_HOURS"), "JWT_EXPIRE_HOURS", errors, min_val=1)

        # LLM
        self.LLM_PROVIDER: str = (raw.get("LLM_PROVIDER") or "").strip()
        if self.LLM_PROVIDER not in ("gemini", "openai_compatible"):
            errors.append(f"LLM_PROVIDER: must be 'gemini' or 'openai_compatible' (got '{self.LLM_PROVIDER}')")

        self.LLM_MODEL: str = (raw.get("LLM_MODEL") or "").strip()
        self.LLM_API_KEY: str = raw.get("LLM_API_KEY", "")
        self.LLM_BASE_URL: str = (raw.get("LLM_BASE_URL") or "").strip()
        if self.LLM_PROVIDER == "openai_compatible" and not self.LLM_BASE_URL:
            errors.append("LLM_BASE_URL: required when LLM_PROVIDER is 'openai_compatible'")

        self.LLM_THINKING_LEVEL: str = (raw.get("LLM_THINKING_LEVEL") or "").strip().lower()
        if self.LLM_THINKING_LEVEL and self.LLM_THINKING_LEVEL not in ("low", "medium", "high"):
            errors.append(f"LLM_THINKING_LEVEL: must be 'low', 'medium', 'high', or empty (got '{self.LLM_THINKING_LEVEL}')")

        self.LLM_TIMEOUT_S: int = _parse_int(raw.get("LLM_TIMEOUT_S"), "LLM_TIMEOUT_S", errors, min_val=1)
        self.LLM_MAX_RETRIES: int = _parse_int(raw.get("LLM_MAX_RETRIES"), "LLM_MAX_RETRIES", errors, min_val=0)

        # Agent
        self.AUTO_SCRAPE: bool = _parse_bool(raw.get("AUTO_SCRAPE"), "AUTO_SCRAPE", errors)
        self.MAX_TOOL_STEPS: int = _parse_int(raw.get("MAX_TOOL_STEPS"), "MAX_TOOL_STEPS", errors, min_val=1)
        self.RECURSION_LIMIT: int = _parse_int(raw.get("RECURSION_LIMIT"), "RECURSION_LIMIT", errors, min_val=1)
        self.HISTORY_TOKEN_BUDGET: int = _parse_int(raw.get("HISTORY_TOKEN_BUDGET"), "HISTORY_TOKEN_BUDGET", errors, min_val=1)
        self.SUMMARY_TRIGGER_MESSAGES: int = _parse_int(raw.get("SUMMARY_TRIGGER_MESSAGES"), "SUMMARY_TRIGGER_MESSAGES", errors, min_val=1)
        self.SCRAPES_PER_HOUR: int = _parse_int(raw.get("SCRAPES_PER_HOUR"), "SCRAPES_PER_HOUR", errors, min_val=1)
        self.FRESHNESS_DAYS: int = _parse_int(raw.get("FRESHNESS_DAYS"), "FRESHNESS_DAYS", errors, min_val=1)
        self.LANGGRAPH_STRICT_MSGPACK: bool = _parse_bool(raw.get("LANGGRAPH_STRICT_MSGPACK"), "LANGGRAPH_STRICT_MSGPACK", errors)

        # Export strict msgpack to env before importing langgraph
        os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true" if self.LANGGRAPH_STRICT_MSGPACK else "false"

        # RAG
        self.RAG_SERVICE_URL: str = (raw.get("RAG_SERVICE_URL") or "").strip()
        self.RAG_SERVICE_TOKEN: str = (raw.get("RAG_SERVICE_TOKEN") or "").strip()
        if self.RAG_SERVICE_URL and not self.RAG_SERVICE_TOKEN:
            errors.append("RAG_SERVICE_TOKEN: required when RAG_SERVICE_URL is set")

        self.RAG_TIMEOUT_S: int = _parse_int(raw.get("RAG_TIMEOUT_S"), "RAG_TIMEOUT_S", errors, min_val=1)
        self.RAG_TOP_K: int = _parse_int(raw.get("RAG_TOP_K"), "RAG_TOP_K", errors, min_val=1, max_val=20)

        # Scrapers / Worker
        self.NYSCR_USERNAME: str = (raw.get("NYSCR_USERNAME") or "").strip()
        self.NYSCR_PASSWORD: str = raw.get("NYSCR_PASSWORD", "")
        self.SELENIUM_MODE: str = (raw.get("SELENIUM_MODE") or "").strip()
        if self.SELENIUM_MODE not in ("local", "remote"):
            errors.append(f"SELENIUM_MODE: must be 'local' or 'remote' (got '{self.SELENIUM_MODE}')")

        self.SELENIUM_REMOTE_URL: str = (raw.get("SELENIUM_REMOTE_URL") or "").strip()
        if self.SELENIUM_MODE == "remote" and not self.SELENIUM_REMOTE_URL:
            errors.append("SELENIUM_REMOTE_URL: required when SELENIUM_MODE is 'remote'")

        self.SCRAPER_MODE: str = (raw.get("SCRAPER_MODE") or "").strip()
        if self.SCRAPER_MODE not in ("live", "fixture"):
            errors.append(f"SCRAPER_MODE: must be 'live' or 'fixture' (got '{self.SCRAPER_MODE}')")
        if self.SCRAPER_MODE == "fixture" and self.ENVIRONMENT != "test":
            errors.append("SCRAPER_MODE: 'fixture' mode is only allowed when ENVIRONMENT='test'")

        self.WORKER_POLL_SECONDS: int = _parse_int(raw.get("WORKER_POLL_SECONDS"), "WORKER_POLL_SECONDS", errors, min_val=1)
        self.JOB_STALE_SECONDS: int = _parse_int(raw.get("JOB_STALE_SECONDS"), "JOB_STALE_SECONDS", errors, min_val=1)
        self.CAPTCHA_WAIT_SECONDS: int = _parse_int(raw.get("CAPTCHA_WAIT_SECONDS"), "CAPTCHA_WAIT_SECONDS", errors, min_val=1)
        self.CHECKPOINT_RETENTION_DAYS: int = _parse_int(raw.get("CHECKPOINT_RETENTION_DAYS"), "CHECKPOINT_RETENTION_DAYS", errors, min_val=1)

        # Monitoring
        self.SENTRY_DSN: str = (raw.get("SENTRY_DSN") or "").strip()
        self.SENTRY_TRACES_SAMPLE_RATE: float = _parse_float(raw.get("SENTRY_TRACES_SAMPLE_RATE"), "SENTRY_TRACES_SAMPLE_RATE", errors, min_val=0.0, max_val=1.0)

        if errors:
            raise ConfigError(f"Configuration validation failed with {len(errors)} error(s):\n" + "\n".join(f"  - {e}" for e in errors))


def _read_env_file(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    raw = {}
    content = path.read_text(encoding="utf-8", errors="ignore")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            raw[key.strip()] = val.strip()
    return raw


def load_settings() -> Settings:
    env_file_override = os.environ.get("DATAOPS_ENV_FILE")
    if env_file_override:
        path = Path(env_file_override)
    else:
        path = BACKEND_DIR / ".env"

    raw = _read_env_file(path)
    return Settings(raw)


# Module-level singleton
try:
    settings = load_settings()
except Exception as _e:
    # Allow test modules to import Settings class even if default env fails at import time
    settings = None
    _init_error = _e
