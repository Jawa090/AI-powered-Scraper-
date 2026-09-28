"""
agents/query/models.py
──────────────────────
Normalized Query Contracts and Data Models.
Provides strongly typed internal representations for user requests, Layer 7 DataAgent requests, and Layer 11 SalesAgent requests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from agents.sales_intelligence import SalesQueryContract


@dataclass
class NormalizedQuery:
    """
    Strongly typed representation of parsed user intent and parameters.
    """
    original_text: str
    intent: str = "lead_search"  # lead_search, contract_search, directory_search, general_inquiry
    entity_type: str = "lead"    # lead, organization, opportunity, contact
    category: Optional[str] = None
    location: Optional[str] = None
    quantity: Optional[int] = None
    requested_fields: List[str] = field(default_factory=list)
    status_requirement: Optional[str] = None
    source_preference: Optional[str] = None  # bonfire, dasny, jwiz, nyscr
    freshness_requested: bool = False
    freshness_max_days: Optional[int] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    company_type: Optional[str] = None  # commercial, residential, both
    session_id: Optional[str] = None
    department_id: Optional[str] = "dept-sales-1"
    is_complete: bool = False
    missing_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class DataQueryContract:
    """
    Structured internal query contract for Layer 7 DataAgent database operations.
    """
    category: Optional[str] = None
    location: Optional[str] = None
    source_code: Optional[str] = None
    status: Optional[str] = None
    quantity: int = 20
    offset: int = 0
    has_email: bool = False
    has_phone: bool = False
    requested_fields: List[str] = field(default_factory=list)
    freshness_requested: bool = False
    freshness_max_days: Optional[int] = None
    assigned_to: Optional[str] = None
    department_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_context(cls, normalized_dict: Optional[Dict[str, Any]], raw_message: str = "") -> "DataQueryContract":
        """
        Build a DataQueryContract from normalized_query dict and raw user message.
        """
        norm = normalized_dict or {}
        msg_lower = (raw_message or "").lower()

        category = norm.get("category")
        location = norm.get("location")
        quantity = norm.get("quantity") or 20
        requested_fields = norm.get("requested_fields") or []
        source_pref = norm.get("source_preference")
        freshness = norm.get("freshness_requested", False) or any(
            k in msg_lower for k in ["fresh", "latest", "recent", "updated"]
        )

        # Source code resolution
        source_code = source_pref
        if not source_code:
            for s_kw in ["bonfire", "dasny", "jwiz", "nyscr"]:
                if s_kw in msg_lower or (category and s_kw in category.lower()):
                    source_code = s_kw
                    break

        # Presence filters
        has_email = any(k in msg_lower for k in ["with email", "email address", "email", "emails"])
        has_phone = any(k in msg_lower for k in ["with phone", "phone number", "phone", "phones", "contact number"])

        # Offset / pagination from filters dict if passed
        filters = norm.get("filters") or {}
        offset = filters.get("offset", 0)

        return cls(
            category=category,
            location=location,
            source_code=source_code,
            status=norm.get("status_requirement"),
            quantity=min(max(1, quantity), 1000),
            offset=offset,
            has_email=has_email,
            has_phone=has_phone,
            requested_fields=requested_fields,
            freshness_requested=freshness,
            freshness_max_days=norm.get("freshness_max_days"),
            department_id=norm.get("department_id"),
        )
