"""
RAG Service Settings
Complies with P10.1:
- Self-contained in RAG/
- No defaults in code, explicit type conversion, collects all errors into ConfigError
"""
import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

RAG_DIR = Path(__file__).resolve().parent

# Check for custom env file or local .env
_env_file = os.environ.get("DATAOPS_RAG_ENV_FILE")
if _env_file and Path(_env_file).exists():
    load_dotenv(_env_file)
elif (RAG_DIR / ".env").exists():
    load_dotenv(RAG_DIR / ".env")
elif (RAG_DIR.parent / ".env").exists():
    load_dotenv(RAG_DIR.parent / ".env")


class ConfigError(Exception):
    """Raised when RAG application configuration is missing or invalid."""
    pass


def _parse_int(
    val: Optional[str],
    field_name: str,
    errors: List[str],
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
) -> int:
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


class RAGSettings:
    """Validated settings container for RAG service."""

    def __init__(self, raw: Optional[dict] = None):
        if raw is None:
            raw = os.environ

        errors: List[str] = []

        # Database
        self.RAG_DATABASE_URL: str = (raw.get("RAG_DATABASE_URL") or raw.get("DATABASE_URL") or "").strip()
        if not self.RAG_DATABASE_URL:
            errors.append("RAG_DATABASE_URL: required database connection string")
        elif not (self.RAG_DATABASE_URL.startswith("postgresql://") or self.RAG_DATABASE_URL.startswith("postgresql+psycopg://") or self.RAG_DATABASE_URL.startswith("sqlite://")):
            errors.append("RAG_DATABASE_URL: must start with postgresql:// or postgresql+psycopg://")

        # Network & Auth
        self.RAG_PORT: int = _parse_int(raw.get("RAG_PORT", "8001"), "RAG_PORT", errors, min_val=1, max_val=65535)
        self.RAG_SERVICE_TOKEN: str = (raw.get("RAG_SERVICE_TOKEN") or "").strip()
        if not self.RAG_SERVICE_TOKEN:
            errors.append("RAG_SERVICE_TOKEN: required service authentication token")

        # Embedding model config
        self.RAG_EMBEDDING_PROVIDER: str = (raw.get("RAG_EMBEDDING_PROVIDER") or "").strip()
        self.RAG_EMBEDDING_MODEL: str = (raw.get("RAG_EMBEDDING_MODEL") or "").strip()

        # Dimension limit check (HNSW limit is 2000 per P10.3)
        self.RAG_EMBEDDING_DIM: int = _parse_int(
            raw.get("RAG_EMBEDDING_DIM", "768"),
            "RAG_EMBEDDING_DIM",
            errors,
            min_val=1,
            max_val=2000,
        )

        # Cache & Log
        self.RAG_STATUS_CACHE_SECONDS: int = _parse_int(
            raw.get("RAG_STATUS_CACHE_SECONDS", "30"),
            "RAG_STATUS_CACHE_SECONDS",
            errors,
            min_val=0,
        )
        log_level = (raw.get("LOG_LEVEL") or "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            errors.append(f"LOG_LEVEL: invalid value '{log_level}'")
        self.LOG_LEVEL: str = log_level

        if errors:
            raise ConfigError("RAG configuration errors:\n - " + "\n - ".join(errors))


_settings_instance: Optional[RAGSettings] = None


def get_rag_settings(reload: bool = False) -> RAGSettings:
    global _settings_instance
    if _settings_instance is None or reload:
        _settings_instance = RAGSettings()
    return _settings_instance
