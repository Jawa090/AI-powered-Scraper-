"""
Database/normalize.py
─────────────────────
Pure normalization functions for deduplication.

All functions are stateless, idempotent, and return None for invalid input.
Used by the ingestion pipeline (P5) and backfill migration (P4.2).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

import phonenumbers
from phonenumbers import NumberParseException
from dateutil.parser import ParserError, parse as parse_date


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

# 50 US States + DC + standard US territories
_US_STATES = {
    "AL": "AL", "ALABAMA": "AL",
    "AK": "AK", "ALASKA": "AK",
    "AZ": "AZ", "ARIZONA": "AZ",
    "AR": "AR", "ARKANSAS": "AR",
    "CA": "CA", "CALIFORNIA": "CA",
    "CO": "CO", "COLORADO": "CO",
    "CT": "CT", "CONNECTICUT": "CT",
    "DE": "DE", "DELAWARE": "DE",
    "FL": "FL", "FLORIDA": "FL",
    "GA": "GA", "GEORGIA": "GA",
    "HI": "HI", "HAWAII": "HI",
    "ID": "ID", "IDAHO": "ID",
    "IL": "IL", "ILLINOIS": "IL",
    "IN": "IN", "INDIANA": "IN",
    "IA": "IA", "IOWA": "IA",
    "KS": "KS", "KANSAS": "KS",
    "KY": "KY", "KENTUCKY": "KY",
    "LA": "LA", "LOUISIANA": "LA",
    "ME": "ME", "MAINE": "ME",
    "MD": "MD", "MARYLAND": "MD",
    "MA": "MA", "MASSACHUSETTS": "MA",
    "MI": "MI", "MICHIGAN": "MI",
    "MN": "MN", "MINNESOTA": "MN",
    "MS": "MS", "MISSISSIPPI": "MS",
    "MO": "MO", "MISSOURI": "MO",
    "MT": "MT", "MONTANA": "MT",
    "NE": "NE", "NEBRASKA": "NE",
    "NV": "NV", "NEVADA": "NV",
    "NH": "NH", "NEW HAMPSHIRE": "NH",
    "NJ": "NJ", "NEW JERSEY": "NJ",
    "NM": "NM", "NEW MEXICO": "NM",
    "NY": "NY", "NEW YORK": "NY",
    "NC": "NC", "NORTH CAROLINA": "NC",
    "ND": "ND", "NORTH DAKOTA": "ND",
    "OH": "OH", "OHIO": "OH",
    "OK": "OK", "OKLAHOMA": "OK",
    "OR": "OR", "OREGON": "OR",
    "PA": "PA", "PENNSYLVANIA": "PA",
    "RI": "RI", "RHODE ISLAND": "RI",
    "SC": "SC", "SOUTH CAROLINA": "SC",
    "SD": "SD", "SOUTH DAKOTA": "SD",
    "TN": "TN", "TENNESSEE": "TN",
    "TX": "TX", "TEXAS": "TX",
    "UT": "UT", "UTAH": "UT",
    "VT": "VT", "VERMONT": "VT",
    "VA": "VA", "VIRGINIA": "VA",
    "WA": "WA", "WASHINGTON": "WA",
    "WV": "WV", "WEST VIRGINIA": "WV",
    "WI": "WI", "WISCONSIN": "WI",
    "WY": "WY", "WYOMING": "WY",
    "DC": "DC", "DISTRICT OF COLUMBIA": "DC",
    # Territories
    "PR": "PR", "PUERTO RICO": "PR",
    "VI": "VI", "VIRGIN ISLANDS": "VI",
    "GU": "GU", "GUAM": "GU",
    "AS": "AS", "AMERICAN SAMOA": "AS",
    "MP": "MP", "NORTHERN MARIANA ISLANDS": "MP",
}

_ZIP_RE = re.compile(r"\b(\d{5}(?:-\d{4})?)\b")
_TRAILING_COUNTRY_RE = re.compile(r",?\s*(?:USA|US|United States)\b\.?$", re.IGNORECASE)


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
    if not s or not isinstance(s, str) or not s.strip():
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
    if not url or not isinstance(url, str) or not url.strip():
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
    except ValueError:
        return None


def normalize_phone(raw: Optional[str], region: str = "US") -> Optional[str]:
    """
    Normalize a phone number to E.164 format using the phonenumbers library.

    Returns None if the input is invalid or unparseable.
    """
    if not raw or not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    try:
        parsed = phonenumbers.parse(raw, region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return None
    except NumberParseException:
        return None


def normalize_email(s: Optional[str]) -> Optional[str]:
    """
    Normalize an email address: strip, lowercase, basic validation.

    Returns None if the input doesn't look like a valid email.
    """
    if not s or not isinstance(s, str) or not s.strip():
        return None
    s = s.strip().lower()
    # Basic email pattern check
    if not re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", s):
        return None
    return s


def normalize_state(raw: Optional[str]) -> Optional[str]:
    """
    Normalize a US state or territory name/abbreviation to its 2-letter uppercase postal code.
    Returns None if raw is None, empty, or not a recognized US state/territory.
    """
    if not raw or not isinstance(raw, str) or not raw.strip():
        return None
    cleaned = raw.strip().upper().rstrip(".")
    return _US_STATES.get(cleaned)


def parse_location(raw: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse a raw location string into (city, state, postal).
    Returns (None, None, None) if raw is empty or unparseable.
    """
    if not raw or not isinstance(raw, str) or not raw.strip():
        return (None, None, None)

    s = raw.strip()
    # Strip trailing country if present
    s = _TRAILING_COUNTRY_RE.sub("", s).strip().rstrip(",")

    # Extract postal code if present
    postal = None
    zip_match = _ZIP_RE.search(s)
    if zip_match:
        postal = zip_match.group(1)
        # Remove postal code from string
        s = s[:zip_match.start()] + s[zip_match.end():]
        s = s.strip().rstrip(",")

    city: Optional[str] = None
    state: Optional[str] = None

    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) >= 2:
            candidate_state = normalize_state(parts[-1])
            if candidate_state:
                state = candidate_state
                city = ", ".join(parts[:-1]).strip()
            else:
                city = ", ".join(parts).strip()
        elif len(parts) == 1:
            candidate_state = normalize_state(parts[0])
            if candidate_state:
                state = candidate_state
            else:
                city = parts[0]
    else:
        # Check if entire string is a state
        candidate_state = normalize_state(s)
        if candidate_state:
            state = candidate_state
        else:
            # Check if last token is a state abbreviation or full name
            words = s.split()
            if len(words) >= 2:
                # Check 2 words for state name like "New York"
                if len(words) >= 3:
                    candidate_2w = normalize_state(" ".join(words[-2:]))
                    if candidate_2w:
                        state = candidate_2w
                        city = " ".join(words[:-2]).strip()
                if not state:
                    candidate_1w = normalize_state(words[-1])
                    if candidate_1w:
                        state = candidate_1w
                        city = " ".join(words[:-1]).strip()
            if not state and not city and s.strip():
                city = s.strip()

    city = city if city else None
    state = state if state else None
    postal = postal if postal else None
    return (city, state, postal)


def parse_due_date(raw: Any) -> Optional[datetime]:
    """
    Parse a due date / closing date string or datetime into a datetime object.
    Uses python-dateutil parser.
    Returns None if unparseable, empty, or None.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime.combine(raw, datetime.min.time())
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return parse_date(s)
    except (ParserError, ValueError, OverflowError, TypeError):
        return None


def org_key(
    name: Optional[str] = None,
    domain: Optional[str] = None,
    phone: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
) -> Optional[str]:
    """
    Generate a 64-character SHA-256 deduplication key for an organization.
    Returns None if name cannot be normalized.
    """
    norm_name = normalize_name(name)
    if not norm_name:
        return None
    parts = [
        norm_name,
        normalize_domain(domain) or "",
        normalize_phone(phone) or "",
        (city.strip().lower() if city and isinstance(city, str) and city.strip() else ""),
        (normalize_state(state) or (state.strip().upper() if state and isinstance(state, str) and state.strip() else "")),
    ]
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def lead_identity(
    kind: Optional[str] = None,
    source_code: Optional[str] = None,
    external_id: Optional[str] = None,
    fingerprint: Optional[str] = None,
) -> Optional[str]:
    """
    Generate the unique identity_key for a Lead record according to D7:
    - opportunity: src:<source_code>:<external_id>
    - company: fp:<fingerprint>
    Returns None if required fields are missing.
    """
    clean_kind = kind.strip().lower() if kind and isinstance(kind, str) else ""
    if clean_kind in ("opportunity", "bid", "rfp"):
        if source_code and external_id:
            src = source_code.strip().lower()
            ext = str(external_id).strip()
            # Strip legacy source prefix if present, e.g. "nyscr_12345"
            if ext.lower().startswith(f"{src}_"):
                ext = ext[len(src) + 1:]
            if src and ext:
                return f"src:{src}:{ext}"
        return None
    elif clean_kind in ("company", "contractor", "business"):
        if fingerprint and isinstance(fingerprint, str) and fingerprint.strip():
            return f"fp:{fingerprint.strip()}"
        return None
    else:
        # Fallback if kind is not specified: infer from available fields
        if source_code and external_id:
            src = source_code.strip().lower()
            ext = str(external_id).strip()
            if ext.lower().startswith(f"{src}_"):
                ext = ext[len(src) + 1:]
            if src and ext:
                return f"src:{src}:{ext}"
        if fingerprint and isinstance(fingerprint, str) and fingerprint.strip():
            return f"fp:{fingerprint.strip()}"
        return None


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
        normalize_domain(domain) or "",
        normalize_phone(phone) or "",
        normalize_email(email) or "",
    ]
    # If all parts are empty, no fingerprint possible
    if not any(parts):
        return None
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


__all__ = [
    "normalize_name",
    "normalize_domain",
    "normalize_phone",
    "normalize_email",
    "normalize_state",
    "parse_location",
    "parse_due_date",
    "org_key",
    "lead_identity",
    "fingerprint",
]
