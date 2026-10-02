"""
Database/normalize.py
─────────────────────
Pure normalization functions for deduplication.

All functions are stateless, idempotent, and return None for invalid input.
Used by the ingestion pipeline (P3.2) and backfill migration (P2.4).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional
from urllib.parse import urlparse


# Legal suffixes to strip from company names
_LEGAL_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|l\.l\.c|l\.l\.c\.|ltd|limited|corp|corporation|"
    r"co|company|plc|lp|l\.p\.|pllc|p\.l\.l\.c|dba|d/b/a)\b\.?",
    re.IGNORECASE,
)

# Collapse multiple whitespace
_MULTI_SPACE = re.compile(r"\s+")

# Non-alphanumeric (except spaces) for name normalization
_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_name(s: Optional[str]) -> Optional[str]:
    """
    Normalize a company/organization name for dedup matching.

    Steps:
    1. NFKC unicode normalization
    2. Lowercase
    3. Strip punctuation (keep alphanumeric + spaces)
    4. Remove legal suffixes (inc, llc, corp, etc.)
    5. Collapse whitespace, strip
    """
    if not s or not s.strip():
        return None
    # NFKC normalization
    result = unicodedata.normalize("NFKC", s)
    result = result.lower()
    # Remove punctuation
    result = _NON_ALNUM.sub(" ", result)
    # Remove legal suffixes
    result = _LEGAL_SUFFIXES.sub("", result)
    # Collapse whitespace
    result = _MULTI_SPACE.sub(" ", result).strip()
    return result if result else None


def normalize_domain(url: Optional[str]) -> Optional[str]:
    """
    Extract and normalize a domain from a URL.

    Returns bare hostname without 'www.' prefix, or None if invalid.
    """
    if not url or not url.strip():
        return None
    url = url.strip()
    # Add scheme if missing so urlparse works
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return None
        # Strip www. prefix
        if host.startswith("www."):
            host = host[4:]
        # Must have at least one dot
        if "." not in host:
            return None
        return host.lower()
    except Exception:
        return None


def normalize_phone(raw: Optional[str], region: str = "US") -> Optional[str]:
    """
    Normalize a phone number to E.164 format using the phonenumbers library.

    Returns None if the input is invalid or unparseable.
    Falls back to digit-only normalization if phonenumbers is not installed.
    """
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    try:
        import phonenumbers
        parsed = phonenumbers.parse(raw, region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return None
    except ImportError:
        # Fallback: strip to digits, prepend +1 if 10 digits
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        elif len(digits) >= 10:
            return f"+{digits}"
        return None
    except Exception:
        return None


def normalize_email(s: Optional[str]) -> Optional[str]:
    """
    Normalize an email address: strip, lowercase, basic validation.

    Returns None if the input doesn't look like a valid email.
    """
    if not s or not s.strip():
        return None
    s = s.strip().lower()
    # Basic email pattern check
    if not re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", s):
        return None
    return s


def fingerprint(
    name: Optional[str] = None,
    domain: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[str]:
    """
    Generate a SHA-256 fingerprint from normalized parts.

    Used for lead deduplication. Returns None if all inputs are None/empty.
    The fingerprint is computed from the pipe-joined normalized values.
    """
    parts = [
        normalize_name(name) or "",
        normalize_domain(domain) if domain else "",
        normalize_phone(phone) if phone else "",
        normalize_email(email) if email else "",
    ]
    # If all parts are empty, no fingerprint possible
    if not any(parts):
        return None
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
