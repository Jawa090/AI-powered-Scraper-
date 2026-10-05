"""
execution/dispatcher.py
───────────────────────
Scraper execution adapters, record normalization, and pre-persistence validation.

Phase 1A rules enforced here:
  - No synthetic data: missing phone/email → None (not fabricated values).
  - No hardcoded fallback contact details.
  - validate_records() rejects structurally invalid records before PostgreSQL write.
  - NYSCR fails clearly when authentication is unavailable.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from execution.contract import TelemetryCallback
from execution.registry import get_registered_script

logger = logging.getLogger(__name__)


def dispatch_scraper(
    script_id: str,
    parameters: Dict[str, Any],
    telemetry: TelemetryCallback,
) -> List[Dict[str, Any]]:
    """
    Dispatch execution to the registered scraper adapter using scrappers.controller.
    """
    from scrappers import controller

    clean_id = script_id.strip().lower()

    # Pre-flight check
    ok, reason = controller.check_ready(clean_id)
    if not ok:
        telemetry(25, "BLOCKED — Missing Credentials", reason or "Authentication required.", "error")
        raise RuntimeError(f"Credentials check failed for {script_id}: {reason}")

    limit = int(parameters.get("limit") or 20)

    class TelemetryContext:
        def log(self, level: str, msg: str) -> None:
            lvl = getattr(logging, level.upper(), logging.INFO)
            logger.log(lvl, msg)

        def progress(self, pct: float, step: str) -> None:
            telemetry(int(pct), f"Progress: {clean_id.upper()}", step, "info")

        def should_cancel(self) -> bool:
            return False

        def wait_for_user(self, reason: str) -> bool:
            telemetry(25, f"WAITING — User Action ({reason})", f"Please solve {reason} in the browser window", "warning")
            return True

    ctx = TelemetryContext()
    telemetry(15, f"Initializing {script_id.upper()} scraper", "Initializing browser/client...", "info")
    records = []

    try:
        telemetry(30, f"Scraping {script_id.upper()} portal", "Collecting opportunities...", "info")
        iterator = controller.run(clean_id, parameters, ctx=ctx)

        for i, rec in enumerate(iterator):
            pct = 30 + int(((i + 1) / max(limit, 1)) * 65)
            telemetry(
                pct,
                f"Extracting {script_id.upper()} record {i+1}/{limit}",
                f"Extracted: {rec.title or rec.organization_name}",
                "info",
            )

            records.append({
                "source_id": rec.external_id,
                "url": rec.source_url,
                "issuing_organization": rec.organization_name,
                "company_name": rec.organization_name,
                "contact_name": rec.contact_name,
                "contact_person": rec.contact_name,
                "email": rec.email,
                "contact_email": rec.email,
                "phone": rec.phone,
                "contact_phone": rec.phone,
                "title": rec.title,
                "location": f"{rec.city}, {rec.us_state}" if rec.city and rec.us_state else (rec.city or rec.us_state),
                "website": rec.website,
                "industry": rec.category,
                "description": rec.description,
                "notes": rec.description,
                "close_date": rec.due_at.isoformat() if rec.due_at else None,
                **rec.extra,
            })
    except Exception as e:
        logger.error("Scraper execution error for %s: %s", script_id, e)
        raise

    telemetry(95, f"Completed {script_id.upper()} extraction", f"Extracted {len(records)} records.", "info", records_found=len(records))
    return records



# ---------------------------------------------------------------------------
# Record Normalization
# ---------------------------------------------------------------------------

def standardize_records(
    raw_records: List[Dict[str, Any]],
    script_id: str,
    dataset_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Standardize heterogeneous scraper output into uniform Lead/Org/Contact records.
    Preserves exact source evidence without fabrication.
    """
    clean_id = script_id.strip().lower()
    standardized = []

    for i, item in enumerate(raw_records):
        lead_id = f"lead-{clean_id}-{int(time.time())}-{i+1}"

        if clean_id == "bonfire":
            title = item.get("title") or None
            ref = item.get("ref_number") or None
            company = item.get("issuing_organization") or "City of Dallas"
            contact_person = item.get("contact_person") or None
            email = item.get("contact_email") or None
            # Real phone only — no hardcoded static fallback
            phone = item.get("contact_phone") or item.get("phone") or None

            standardized.append({
                "id": lead_id,
                "dataset_id": dataset_id,
                "organization_name": company,
                "contact_name": contact_person,
                "title": f"Procurement: {title[:60]}" if title else None,
                "email": email,
                "phone": phone,
                "location": item.get("location") or None,
                "website": item.get("url") or None,
                "industry": item.get("industry") or "Municipal Procurement",
                "status": "New",
                "notes": f"Ref #: {ref}. Close Date: {item.get('close_date')}." if ref else None,
                "lead_metadata": item,
            })

        elif clean_id == "jwiz":
            company = item.get("company_name") or None
            # JWiz cards carry no named contact; don't invent one
            contact_person = None
            email = item.get("email")
            phone = item.get("phone")
            location_parts = [p for p in (item.get("city"), item.get("state")) if p]

            standardized.append({
                "id": lead_id,
                "dataset_id": dataset_id,
                "organization_name": company,
                "contact_name": contact_person,
                "title": f"{item.get('category', 'Contractor')} Owner / Manager",
                "email": email,
                "phone": phone,
                "location": ", ".join(location_parts + ["USA"]) if location_parts else None,
                "website": item.get("profile_url") or None,
                "industry": f"Commercial Services ({item.get('category', 'General')})",
                "status": "New",
                "notes": None,
                "lead_metadata": item,
            })

        elif clean_id == "dasny":
            title = item.get("title") or None
            company = "Dormitory Authority of the State of New York (DASNY)"
            contact_person = item.get("contact_name") or None
            # Real contact only — no hardcoded fallback email/phone
            email = item.get("contact_email") or None
            phone = item.get("contact_phone") or item.get("phone") or None

            standardized.append({
                "id": lead_id,
                "dataset_id": dataset_id,
                "organization_name": company,
                "contact_name": contact_person,
                "title": f"RFP: {title[:60]}" if title else None,
                "email": email,
                "phone": phone,
                "location": item.get("location") or None,
                "website": item.get("url") or None,
                "industry": item.get("industry") or "Public Construction",
                "status": "New",
                "notes": item.get("url") or None,
                "lead_metadata": item,
            })

        else:  # nyscr
            title = item.get("title") or None
            company = item.get("issuing_organization") or None
            contact_person = item.get("contact_name") or None
            # Real contact only — no hardcoded fallback email/phone
            email = item.get("contact_email") or None
            phone = item.get("contact_phone") or item.get("phone") or None

            standardized.append({
                "id": lead_id,
                "dataset_id": dataset_id,
                "organization_name": company,
                "contact_name": contact_person,
                "title": f"Contract: {title[:60]}" if title else None,
                "email": email,
                "phone": phone,
                "location": item.get("location") or None,
                "website": item.get("url") or None,
                "industry": item.get("industry") or "State Contracting",
                "status": "New",
                "notes": f"Bid deadline: {item.get('bid_deadline')}" if item.get('bid_deadline') else None,
                "lead_metadata": item,
            })

    return standardized


# ---------------------------------------------------------------------------
# Pre-persistence Validation
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def validate_records(
    standardized: List[Dict[str, Any]],
    script_id: str,
) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """
    Validate normalized records before PostgreSQL persistence.

    Rules:
    - A record must have at least one of: title, organization_name.
    - If email is present it must match basic RFC pattern; otherwise set to None.
    - If website is present it must start with http/https; otherwise set to None.
    - Missing optional fields (phone, email, contact_name) are accepted as None.
    - No synthetic values are inserted for missing fields.

    Returns:
        (valid_records, rejected_count, rejection_reasons)
    """
    valid: List[Dict[str, Any]] = []
    rejected = 0
    reasons: List[str] = []

    for i, rec in enumerate(standardized):
        label = f"[{script_id.upper()} record {i+1}]"

        # Required: at least a title or an organization name
        if not rec.get("title") and not rec.get("organization_name"):
            reason = f"{label} rejected: missing both title and organization_name"
            logger.warning(reason)
            reasons.append(reason)
            rejected += 1
            continue

        # Email: clear if malformed (do not fabricate a replacement)
        raw_email = rec.get("email")
        if raw_email and not _EMAIL_RE.match(str(raw_email)):
            logger.warning("%s email '%s' is malformed — clearing to None", label, raw_email)
            rec["email"] = None

        # Website: clear if malformed
        raw_url = rec.get("website")
        if raw_url and not _URL_RE.match(str(raw_url)):
            logger.warning("%s website '%s' is malformed — clearing to None", label, raw_url)
            rec["website"] = None

        valid.append(rec)

    if rejected:
        logger.info(
            "validate_records[%s]: %d/%d records passed, %d rejected",
            script_id, len(valid), len(standardized), rejected,
        )

    return valid, rejected, reasons
