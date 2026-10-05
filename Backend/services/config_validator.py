"""
services/config_validator.py
────────────────────────────
Runtime configuration validation and audit service.
Provides clean status inspections using settings.
"""

from typing import Dict, Any, List, Tuple
from settings import settings


def mask_secret(val: str, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """Masks sensitive strings for safe diagnostic logging."""
    if not val or val == "EMPTY":
        return "[NOT SET]"
    if len(val) <= (visible_prefix + visible_suffix):
        return "***"
    return f"{val[:visible_prefix]}...{val[-visible_suffix:]}"


def mask_database_url(url: str) -> str:
    """Masks database password in connection URL for safe logging."""
    if not url:
        return "[NOT SET]"
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        netloc = f"{p.username}:***@{p.hostname}"
        if p.port:
            netloc += f":{p.port}"
        return f"{p.scheme}://{netloc}{p.path}"
    except Exception:
        return "[UNPARSEABLE DATABASE URL]"


class ConfigValidator:
    """
    Validates and audits runtime configuration using settings.
    """

    @classmethod
    def validate_database_config(cls) -> Tuple[bool, List[str]]:
        errors = []
        db_url = settings.DATABASE_URL
        if not db_url:
            errors.append("DATABASE_URL is missing.")
            return False, errors
        if not db_url.startswith("postgresql"):
            errors.append("DATABASE_URL must specify a PostgreSQL database scheme.")
        return len(errors) == 0, errors

    @classmethod
    def validate_llm_config(cls) -> Dict[str, Any]:
        return {
            "provider": settings.LLM_PROVIDER,
            "base_url": settings.LLM_BASE_URL,
            "model": settings.LLM_MODEL,
            "has_api_key": bool(settings.LLM_API_KEY),
            "api_key_masked": mask_secret(settings.LLM_API_KEY) if settings.LLM_API_KEY else "[NONE SET]",
            "timeout_seconds": settings.LLM_TIMEOUT_S,
        }

    @classmethod
    def audit_scraper_credentials(cls) -> Dict[str, Dict[str, Any]]:
        nyscr_ready = bool(settings.NYSCR_USERNAME and settings.NYSCR_PASSWORD)
        missing_nyscr = []
        if not settings.NYSCR_USERNAME:
            missing_nyscr.append("NYSCR_USERNAME")
        if not settings.NYSCR_PASSWORD:
            missing_nyscr.append("NYSCR_PASSWORD")

        return {
            "bonfire": {"requires_auth": False, "status": "READY", "missing": []},
            "dasny": {"requires_auth": False, "status": "READY", "missing": []},
            "jwiz": {"requires_auth": False, "status": "READY", "missing": []},
            "nyscr": {
                "requires_auth": True,
                "status": "READY" if nyscr_ready else "BLOCKED",
                "missing": missing_nyscr,
            },
        }

    @classmethod
    def get_sanitized_environment_summary(cls) -> Dict[str, Any]:
        db_valid, db_errors = cls.validate_database_config()
        return {
            "database": {
                "configured": db_valid,
                "url_masked": mask_database_url(settings.DATABASE_URL),
                "errors": db_errors,
            },
            "llm": cls.validate_llm_config(),
            "scrapers": cls.audit_scraper_credentials(),
            "environment": settings.ENVIRONMENT,
            "log_level": settings.LOG_LEVEL,
        }
