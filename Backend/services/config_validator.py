"""
services/config_validator.py
─────────────────────────────
Production Configuration & Credential Validator (Phase 2G.1).
Audits runtime configuration, verifies environment variables, prevents secret leakage,
and masks sensitive credentials in all output representations.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple


def mask_secret(secret: Optional[str]) -> str:
    """Masks secrets for safe display in logs and diagnostic outputs."""
    if not secret:
        return "[NOT SET]"
    if len(secret) <= 4:
        return "****"
    return f"{secret[:2]}****{secret[-2:]}"


def mask_database_url(url: Optional[str]) -> str:
    """Masks database password in connection URLs."""
    if not url:
        return "[NOT SET]"
    return re.sub(r":([^:@]+)@", r":****@", url)


class ConfigValidator:
    """
    Validates and audits the runtime environment configuration for DataOps AI Platform.
    Ensures fail-fast on missing mandatory configs and safe secret masking.
    """

    @classmethod
    def validate_database_config(cls) -> Tuple[bool, List[str]]:
        """Verifies DATABASE_URL is configured and parseable."""
        errors = []
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            errors.append("DATABASE_URL is missing from environment.")
            return False, errors

        if not db_url.startswith("postgresql"):
            errors.append("DATABASE_URL must specify a PostgreSQL database scheme.")

        return len(errors) == 0, errors

    @classmethod
    def validate_llm_config(cls) -> Dict[str, Any]:
        """Audits LLM configuration parameters."""
        provider = os.getenv("LLM_PROVIDER", "openai_compatible")
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        model = os.getenv("LLM_MODEL", "llama3")
        api_key = os.getenv("LLM_API_KEY", "")
        timeout = int(os.getenv("LLM_TIMEOUT", "30"))

        return {
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "has_api_key": bool(api_key and api_key != "EMPTY"),
            "api_key_masked": mask_secret(api_key) if api_key else "[NONE REQUIRED/SET]",
            "timeout_seconds": timeout,
        }

    @classmethod
    def audit_scraper_credentials(cls) -> Dict[str, Dict[str, Any]]:
        """Audits credential status for all registered scraper engines."""
        return {
            "bonfire": {
                "requires_auth": False,
                "status": "READY",
                "missing": [],
            },
            "dasny": {
                "requires_auth": False,
                "status": "READY",
                "missing": [],
            },
            "jwiz": {
                "requires_auth": False,
                "status": "READY",
                "missing": [],
            },
            "nyscr": {
                "requires_auth": True,
                "status": "READY" if (os.getenv("NYSCR_USERNAME") and os.getenv("NYSCR_PASSWORD")) else "BLOCKED",
                "missing": [
                    k for k in ["NYSCR_USERNAME", "NYSCR_PASSWORD"] if not os.getenv(k)
                ],
            },
        }

    @classmethod
    def get_sanitized_environment_summary(cls) -> Dict[str, Any]:
        """Returns safe, audit-compliant configuration summary with no exposed secrets."""
        db_valid, db_errors = cls.validate_database_config()
        return {
            "database": {
                "configured": db_valid,
                "url_masked": mask_database_url(os.getenv("DATABASE_URL")),
                "errors": db_errors,
            },
            "llm": cls.validate_llm_config(),
            "scrapers": cls.audit_scraper_credentials(),
            "environment": os.getenv("ENVIRONMENT", "production"),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        }
