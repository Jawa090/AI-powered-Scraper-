"""
agents/intent/validator.py
──────────────────────────
IntentValidator: Enforces backend policies, registry checks, filter security,
and bounds checking on StructuredIntent before reaching planning or execution.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from execution.registry import SCRIPTS_REGISTRY
from agents.intent.models import IntentType, StructuredIntent

# Allowed filter fields for database queries
ALLOWED_FILTER_FIELDS = {
    "title", "organization_name", "category", "location", "status",
    "has_email", "has_phone", "source", "dataset_id", "limit", "offset",
    "industry", "notes"
}

# Dangerous patterns to sanitize
SQL_INJECTION_PATTERN = re.compile(
    r"(\b(UNION\s+ALL|UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|EXECUTE|SHUTDOWN)\b|--|\bOR\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?|;|OR\s+['\"][^'\"]*['\"]\s*=\s*['\"][^'\"]*['\"])",
    re.IGNORECASE,
)


class IntentValidationError(ValueError):
    """Raised when structured intent violates backend policies."""
    pass


class IntentValidator:
    """
    Validates StructuredIntent against authoritative backend registry and safety policies.
    """

    @classmethod
    def validate(cls, intent: StructuredIntent) -> Tuple[bool, List[str]]:
        """
        Validates intent and returns (is_valid, error_messages).
        """
        errors: List[str] = []

        # 1. Validate Scraper ID if specified
        if intent.scraper_id:
            known_ids = {s["id"] for s in SCRIPTS_REGISTRY}
            if intent.scraper_id not in known_ids:
                errors.append(
                    f"Invalid scraper_id '{intent.scraper_id}'. Known scrapers: {sorted(list(known_ids))}"
                )

        # 2. Validate Quantity Bounds
        if intent.quantity is not None:
            if intent.quantity < 1:
                errors.append(f"Quantity must be at least 1, received {intent.quantity}")
            elif intent.quantity > 50000:
                errors.append(f"Quantity exceeds maximum allowable limit (50,000), received {intent.quantity}")

        # 3. Validate Filters Structure and Whitelist
        if intent.filters:
            if not isinstance(intent.filters, dict):
                errors.append("Filters must be a JSON object (dictionary)")
            else:
                for k, v in intent.filters.items():
                    if k not in ALLOWED_FILTER_FIELDS:
                        errors.append(f"Filter field '{k}' is not in allowed fields whitelist")
                    # Check for injection in string values
                    if isinstance(v, str) and SQL_INJECTION_PATTERN.search(v):
                        errors.append(f"Potentially unsafe SQL pattern detected in filter '{k}'")

        # 4. Validate Job ID format if present
        if intent.job_id:
            if not re.match(r"^[a-zA-Z0-9_\-]+$", intent.job_id):
                errors.append(f"Invalid characters in job_id '{intent.job_id}'")

        # 5. Validate Dataset ID format if present
        if intent.dataset_id:
            if not re.match(r"^[a-zA-Z0-9_\-]+$", intent.dataset_id):
                errors.append(f"Invalid characters in dataset_id '{intent.dataset_id}'")

        # 6. Validate Required Fields by Intent Type
        if intent.intent == IntentType.JOB_STATUS:
            # If job_status, user should either provide job_id or request recent jobs
            pass
        elif intent.intent == IntentType.SCRAPER_REQUEST:
            if not intent.scraper_id and not intent.category and not intent.location:
                errors.append("Scraper request requires at least a category, location, or scraper_id")

        return len(errors) == 0, errors

    @classmethod
    def sanitize_and_correct(cls, intent: StructuredIntent) -> StructuredIntent:
        """
        Sanitizes and corrects benign intent discrepancies.
        """
        # Align scraper_id if category/location strongly point to one
        if not intent.scraper_id:
            loc = (intent.location or "").lower()
            cat = (intent.category or "").lower()
            user_text = (intent.user_request or "").lower()

            if "bonfire" in user_text or ("dallas" in loc and ("bid" in user_text or "bonfire" in user_text)):
                intent.scraper_id = "bonfire"
            elif "dasny" in user_text or "dormitory" in user_text or ("dasny" in cat):
                intent.scraper_id = "dasny"
            elif "jwiz" in user_text or "directory" in user_text:
                intent.scraper_id = "jwiz"
            elif "nyscr" in user_text or "contract reporter" in user_text:
                intent.scraper_id = "nyscr"

        # Sanitize quantity default and clamp to allowable bounds (1 - 50000)
        if intent.quantity is not None:
            intent.quantity = max(1, min(50000, intent.quantity))
        elif intent.needs_database or intent.needs_scraping:
            intent.quantity = 20

        return intent
