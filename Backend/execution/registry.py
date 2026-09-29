"""
execution/registry.py
─────────────────────
Controlled Scraper Registry and Dispatch Validator.
Ensures only verified, registered scraper engines can be executed.
Rejects arbitrary filepaths or unapproved script identifiers.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Verified Scraper Engine Registry
SCRIPTS_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "bonfire",
        "name": "Dallas City Hall Bonfire Scraper",
        "version": "v1.2.0",
        "file": "dallas_bonfire_scraper.py",
        "status": "Active",
        "category": "Government & Municipal Bids",
        "department": "Procurement & Bids",
        "usedBy": ["Sales 1", "Public Sector", "Operations"],
        "capabilities": [
            "City procurement extraction",
            "Reference number parsing",
            "Closing date & days left tracker",
            "RFP / ITB scope extraction",
        ],
        "description": "Autonomous extractor for open opportunities, RFP bids, and commodity procurement from Dallas City Hall Bonfire Hub.",
        "successRate": "99.2%",
        "defaultLimit": 20,
    },
    {
        "id": "dasny",
        "name": "DASNY RFP & Bid Opportunities Scraper",
        "version": "v2.0.1",
        "file": "dasny_scraper.py",
        "status": "Active",
        "category": "State Authority RFPs",
        "department": "Research & Sales",
        "usedBy": ["Sales 1", "Sales 2", "Estimating"],
        "capabilities": [
            "Dormitory Authority of NY bids",
            "Public listing extraction",
            "Contact email parsing",
            "Planholders & Interested subs identification",
        ],
        "description": "Extracts construction, engineering, and architectural bid opportunities and contacts from the State of New York Dormitory Authority.",
        "successRate": "98.8%",
        "defaultLimit": 20,
    },
    {
        "id": "jwiz",
        "name": "JWiz Commercial & Services Directory Scraper",
        "version": "v3.1.0",
        "file": "jwiz.py",
        "status": "Active",
        "category": "Commercial B2B Directory",
        "department": "Sales & Email Outreach",
        "usedBy": ["Sales 1", "Email Marketing", "Business Development"],
        "capabilities": [
            "Direct business discovery",
            "City & State geographic targeting",
            "Phone & Email validation",
            "Social / LinkedIn profiling",
        ],
        "description": "High-throughput directory extractor gathering verified commercial contractors, service providers, phone numbers, and emails.",
        "successRate": "99.4%",
        "defaultLimit": 50,
    },
    {
        "id": "nyscr",
        "name": "NYSCR State Contract Reporter Scraper",
        "version": "v2.4.0",
        "file": "final_scraper.py",
        "status": "Active",
        "category": "Statewide Contracts",
        "department": "Procurement & Enterprise",
        "usedBy": ["Research", "Business Development"],
        "capabilities": [
            "New York State Contract Reporter extraction",
            "Agency issuing organization discovery",
            "Bid deadlines and submission criteria",
            "Verified procurement contact capture",
        ],
        "description": "Official New York State procurement portal scraper for state agency contracts, open bids, and contractor opportunities.",
        "successRate": "97.9%",
        "defaultLimit": 25,
    },
]

_REGISTRY_MAP = {s["id"]: s for s in SCRIPTS_REGISTRY}


def is_registered(script_id: str) -> bool:
    """Return True if script_id is in the approved registry."""
    return script_id.strip().lower() in _REGISTRY_MAP


def get_registered_script(script_id: str) -> Dict[str, Any]:
    """
    Retrieve metadata for an approved script ID.
    Raises ValueError if script_id is not registered.
    """
    clean_id = script_id.strip().lower()
    if clean_id not in _REGISTRY_MAP:
        raise ValueError(
            f"Unregistered scraper engine: '{script_id}'. "
            f"Only approved engines ({list(_REGISTRY_MAP.keys())}) may be executed."
        )
    return _REGISTRY_MAP[clean_id]


def list_registered_scripts() -> List[Dict[str, Any]]:
    """Return list of all registered scraper definitions."""
    return list(SCRIPTS_REGISTRY)


# Procurement categories that only exist as municipal bids (Bonfire)
_BONFIRE_CATEGORIES = ("sweep", "paving", "flags", "stagehand")
_PROCUREMENT_WORDS = re.compile(
    r"\b(contracts?|bids?|rfps?|rfqs?|procurements?|tenders?|solicitations?)\b"
)


def recommend_scraper(
    category: Optional[str] = None,
    location: Optional[str] = None,
    text: Optional[str] = None,
) -> str:
    """
    Pick the registered scraper that can actually serve a request.

    - An explicitly named source always wins.
    - Procurement requests (bids / RFPs / contracts) go to Bonfire for Dallas
      and DASNY for New York; the other scrapers carry no such data.
    - Everything else is a business-directory lookup, which only JWiz serves.
    """
    cat = (category or "").lower()
    loc = (location or "").lower()
    txt = (text or "").lower()

    if "bonfire" in txt or "city hall" in txt:
        return "bonfire"
    if "dasny" in txt or "dormitory" in txt:
        return "dasny"
    if "nyscr" in txt or "contract reporter" in txt:
        return "nyscr"
    if "jwiz" in txt or "directory" in txt or "yellow page" in txt:
        return "jwiz"

    is_procurement = (
        bool(_PROCUREMENT_WORDS.search(txt))
        or cat == "all open opportunities"
        or any(c in cat for c in _BONFIRE_CATEGORIES)
    )
    if is_procurement:
        return "bonfire" if ("dallas" in loc or "texas" in loc) else "dasny"
    return "jwiz"
