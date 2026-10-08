"""
utils/pii.py
────────────
PII masking utilities for logging, Sentry, and trace summaries.
Masks emails and phone numbers in text to prevent accidental exposure.
"""

from __future__ import annotations

import re
from typing import Optional

# Patterns
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"
)


def mask_email(email: str) -> str:
    """Mask an email address: 'john.doe@acme.com' → 'j***@acme.com'."""
    if not email or "@" not in email:
        return email
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """Mask a phone number: '+12145550100' → '+1******0100'."""
    if not phone:
        return phone
    digits = re.sub(r"[^\d+]", "", phone)
    if len(digits) < 7:
        return phone
    # Keep first 2 and last 4 characters
    prefix = digits[:2]
    suffix = digits[-4:]
    middle_len = len(digits) - 6
    return f"{prefix}{'*' * middle_len}{suffix}"


def mask_text(text: Optional[str]) -> str:
    """Mask all emails and phone numbers found in a text string."""
    if not text:
        return text or ""
    result = _EMAIL_RE.sub(lambda m: mask_email(m.group()), text)
    result = _PHONE_RE.sub(lambda m: mask_phone(m.group()), result)
    return result


_SECRET_FIELD = re.compile(r"password|secret|token|authorization|cookie|api.?key|database.?url|checkpoint.?db.?url", re.I)


def mask_payload(value):
    """Protect nested extras, exception text and telemetry at the sink boundary."""
    if isinstance(value, dict):
        return {key: '[redacted]' if _SECRET_FIELD.search(str(key)) else mask_payload(item)
            for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_payload(item) for item in value]
    if isinstance(value, str):
        import sys
        config = getattr(sys.modules.get('settings'), 'settings', None)
        if config:
            for name in ['NYSCR_PASSWORD', 'NYSCR_USERNAME', 'JWT_SECRET', 'LLM_API_KEY', 'DEEPSEEK_API_KEY',
                'GEMINI_API_KEY', 'OPENROUTER_API_KEY', 'RAG_SERVICE_TOKEN', 'DATABASE_URL', 'CHECKPOINT_DB_URL']:
                secret = getattr(config, name, '')
                if secret and len(secret) >= 4:
                    value = value.replace(secret, '[redacted]')
        value = re.sub(r'(postgresql(?:\+psycopg)?://[^:\s]+:)[^@\s]+@', r'\1[redacted]@', value)
        return mask_text(value)
    return value
