"""
agents/query/parser.py
──────────────────────
QueryParser: Extracts intent, category, location, quantity, requested fields,
and freshness from user messages without fabricating unsupported data.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from agents.query.models import NormalizedQuery

# Known category patterns (trades, procurement items, public works)
CATEGORY_PATTERNS = [
    (r"\b(commercial\s+general\s+contractors?)\b", "Commercial General Contractor"),
    (r"\b(commercial\s+contractors?)\b", "Commercial Contractor"),
    (r"\b(residential\s+contractors?)\b", "Residential Contractor"),
    (r"\b(commercial\s+construction)\b", "Commercial Construction"),
    (r"\b(residential\s+construction)\b", "Residential Construction"),
    (r"\b(roofing\s+contractors?)\b", "Roofing Contractors"),
    (r"\b(electrical\s+(?:sub)?contractors?)\b", "Electrical Contractors"),
    (r"\b(drywall(?:\s+(?:and|&)\s+sheetrock)?(?:\s+(?:sub)?contractors?)?|sheetrock\s+(?:sub)?contractors?)\b", "Drywall & Sheetrock Contractors"),
    (r"\b(general\s+contractors?)\b", "General Contractor"),
    (r"\b(subcontractors?)\b", "Subcontractor"),
    (r"\b(contractors?)\b", "Contractor"),
    (r"\b(construction)\b", "Construction"),
    (r"\b(plumbers?|plumbing)\b", "Plumber"),
    (r"\b(electricians?|electrical)\b", "Electrician"),
    (r"\b(carpenters?|carpentry)\b", "Carpenter"),
    (r"\b(roofers?|roofing)\b", "Roofing"),
    (r"\b(hvac|heating|air conditioning)\b", "HVAC"),
    (r"\b(street sweep(?:ing)?|sweeping)\b", "Street Sweeping"),
    (r"\b(paving|pavement|road repairs?|civil works?)\b", "Paving & Road Repairs"),
    (r"\b(stagehands?|labor|temporary labor)\b", "Stagehand & Labor"),
    (r"\b(architectural|architecture)\b", "Architectural Services"),
    (r"\b(engineering|civil engineering)\b", "Engineering Services"),
    (r"\b(facility maintenance|security)\b", "Facility Maintenance"),
    (r"\b(transportation|highway)\b", "Transportation"),
    (r"\b(flags?|pennants?)\b", "City Flags & Banners"),
    (r"\b(water works?|utilities)\b", "Water & Utilities"),
]

# Known location patterns
LOCATION_PATTERNS = [
    (r"\b(new york|newyork|nyc|ny|new-york)\b", "New York"),
    (r"\b(dallas|texas|tx)\b", "Dallas"),
    (r"\b(albany)\b", "Albany"),
    (r"\b(buffalo)\b", "Buffalo"),
    (r"\b(brooklyn)\b", "Brooklyn"),
    (r"\b(queens)\b", "Queens"),
    (r"\b(bronx)\b", "Bronx"),
    (r"\b(manhattan)\b", "Manhattan"),
    (r"\b(lakewood)\b", "Lakewood"),
    (r"\b(new jersey|jersey)\b", "New Jersey"),
    (r"\b(austin)\b", "Austin"),
    (r"\b(houston)\b", "Houston"),
    (r"\b(united states|usa|u\.s\.a\.|us)\b", "United States"),
]

# Freshness keywords
FRESHNESS_KEYWORDS = ["latest", "recent", "fresh", "newest", "live", "real-time", "today", "current"]


class QueryParser:
    """
    Extracts structured attributes from freeform text and multi-turn state.
    """

    @classmethod
    def parse(
        cls,
        text: str,
        context_requirement: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> NormalizedQuery:
        raw = text.strip()
        lower = raw.lower()

        # 1. Base values from previous turn context (if any)
        ctx = context_requirement or {}
        cat = ctx.get("industry")
        if cat in ["Not specified", "All Open Opportunities", None]:
            cat = None

        loc = ctx.get("location")
        if loc in ["Not specified", "Specified Region", None]:
            loc = None

        qty: Optional[int] = ctx.get("quantity") if ctx.get("quantity", 0) > 0 else None
        src: Optional[str] = ctx.get("selectedScript")
        comp_type: Optional[str] = ctx.get("companyType") or ctx.get("company_type") or None

        # Previous requested fields
        prev_fields = ctx.get("requiredFields")
        if isinstance(prev_fields, list):
            requested_fields = list(prev_fields)
        elif isinstance(prev_fields, dict):
            requested_fields = [k for k, v in prev_fields.items() if v]
        else:
            requested_fields = []

        # 2. Extract Company Type
        has_commercial = bool(re.search(r"\bcommercial\b", lower))
        has_residential = bool(re.search(r"\bresidential\b", lower))
        if has_commercial and has_residential:
            comp_type = "Commercial & Residential"
        elif has_commercial:
            comp_type = "Commercial"
        elif has_residential:
            comp_type = "Residential"

        # 3. Extract Category
        for pattern, standard_cat in CATEGORY_PATTERNS:
            if re.search(pattern, lower):
                cat = standard_cat
                break

        # If user explicitly specified commercial or residential in this message and category was generic
        if cat and "contractor" in cat.lower():
            if has_commercial and not has_residential and "commercial" not in cat.lower():
                cat = f"Commercial {cat}"
            elif has_residential and not has_commercial and "residential" not in cat.lower():
                cat = f"Residential {cat}"

        # 4. Extract Location
        for pattern, standard_loc in LOCATION_PATTERNS:
            if re.search(pattern, lower):
                loc = standard_loc
                break

        # 5. Extract Quantity
        # Matches formats: "500 contractors", "quantity: 50", "need 100", or standalone numbers
        qty_matches = re.findall(
            r"\b(?:give me|find|get|need|top|extract|target|quantity[:\s]*|volume[:\s]*)?\s*(\d{1,5})\s*(?:records?|leads?|bids?|rfps?|contracts?|contractors?|plumbers?|electricians?|items?)?",
            lower,
        )
        if qty_matches:
            for m in qty_matches:
                try:
                    v = int(m)
                    # Avoid false matching years like 2024, 2025 unless explicit
                    if 0 < v <= 50000:
                        qty = v
                        break
                except ValueError:
                    pass

        # 6. Extract Source Preference
        if any(k in lower for k in ["dallas", "bonfire"]):
            src = "bonfire"
        elif any(k in lower for k in ["dasny", "dormitory"]):
            src = "dasny"
        elif any(k in lower for k in ["jwiz", "jewish", "directory"]):
            src = "jwiz"
        elif any(k in lower for k in ["nyscr", "contract reporter"]):
            src = "nyscr"

        # 7. Extract Requested Fields
        if "email" in lower and "email" not in requested_fields:
            requested_fields.append("email")
        if any(k in lower for k in ["phone", "call", "direct dial"]) and "phone" not in requested_fields:
            requested_fields.append("phone")
        if any(k in lower for k in ["website", "url", "portal"]) and "website" not in requested_fields:
            requested_fields.append("website")
        if any(k in lower for k in ["contact", "person", "decision maker", "officer"]) and "contact_person" not in requested_fields:
            requested_fields.append("contact_person")
        if any(k in lower for k in ["address", "location", "zip"]) and "location" not in requested_fields:
            requested_fields.append("location")

        # 8. Extract Freshness
        freshness_requested = any(re.search(r"\b" + re.escape(w) + r"\b", lower) for w in FRESHNESS_KEYWORDS)

        # 9. Determine Intent
        intent = "lead_search"
        if any(k in lower for k in ["contract", "bid", "rfp", "procurement"]):
            intent = "contract_search"
        elif any(k in lower for k in ["directory", "yellow page", "listing"]):
            intent = "directory_search"
        elif any(k in lower for k in ["research", "analyze the market", "analyze market", "market research", "competitor analysis", "domain analysis", "market overview", "industry research"]):
            intent = "research_request"
        elif any(k in lower for k in ["growth", "scale", "expand", "market comparison", "acquisition"]):
            intent = "growth_strategy"
        elif any(k in lower for k in ["hello", "hi", "help", "who are you", "what can you do"]):
            intent = "general_inquiry"

        # 10. Evaluate Completeness (Only truly missing essential fields are flagged)
        missing_fields: List[str] = []
        if intent != "general_inquiry":
            if not cat:
                missing_fields.append("category")
            if not loc:
                missing_fields.append("location")
            if not qty:
                missing_fields.append("quantity")

        is_complete = len(missing_fields) == 0

        return NormalizedQuery(
            original_text=raw,
            intent=intent,
            entity_type="opportunity" if intent == "contract_search" else "lead",
            category=cat,
            location=loc,
            quantity=qty,
            requested_fields=requested_fields,
            source_preference=src,
            freshness_requested=freshness_requested,
            company_type=comp_type,
            session_id=session_id,
            is_complete=is_complete,
            missing_fields=missing_fields,
        )
