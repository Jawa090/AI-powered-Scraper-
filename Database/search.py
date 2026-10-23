"""Canonical search criteria shared by chat, completion and persistence."""
import hashlib
import json
import re
from typing import List, Tuple, Union
from pydantic import BaseModel, Field, field_validator
from Database.normalize import normalize_state
import sys
from pathlib import Path

dir = Path(__file__).resolve().parent.parent

TRADE_ALIASES: dict[str, list[str]] = {
    "electrical": ["electric", "electrician", "electricians", "wiring", "lighting"],
    "electric": ["electrical", "electrician", "electricians", "wiring", "lighting"],
    "electrician": ["electrical", "electric", "electricians", "wiring", "lighting"],
    "electricians": ["electrical", "electric", "electrician", "wiring", "lighting"],
    "wiring": ["electrical", "electric", "electrician", "lighting"],
    "lighting": ["electrical", "electric", "wiring"],
    "roofing": ["roofer", "roofers"],
    "roofer": ["roofing", "roofers"],
    "roofers": ["roofing", "roofer"],
    "plumbing": ["plumber", "plumbers", "pipefitting", "pipefitter", "drainage"],
    "plumber": ["plumbing", "plumbers", "pipefitting", "pipefitter", "drainage"],
    "plumbers": ["plumbing", "plumber", "pipefitting", "drainage"],
    "hvac": ["heating", "ventilation", "air conditioning", "cooling", "ac"],
    "heating": ["hvac", "ventilation", "air conditioning", "cooling"],
    "cooling": ["hvac", "heating", "air conditioning"],
    "ventilation": ["hvac", "heating", "cooling"],
    "air conditioning": ["hvac", "cooling", "heating", "ac"],
    "ac": ["hvac", "air conditioning", "cooling", "heating"],
    "a c": ["hvac", "air conditioning", "cooling", "heating"],
    "refrigeration": ["hvac", "cooling", "cold storage"],
    "painting": ["painter", "painters"],
    "painter": ["painting", "painters"],
    "painters": ["painting", "painter"],
    "carpentry": ["carpenter", "carpenters", "woodworking", "framing"],
    "carpenter": ["carpentry", "carpenters", "woodworking", "framing"],
    "carpenters": ["carpentry", "carpenter", "framing"],
    "masonry": ["mason", "masons", "bricklayer", "bricklayers", "concrete"],
    "mason": ["masonry", "masons", "bricklayer", "concrete"],
    "masons": ["masonry", "mason", "bricklayer", "concrete"],
    "drywall": ["plaster", "plastering"],
    "plaster": ["drywall", "plastering"],
    "flooring": ["floor", "tile", "tiling", "carpet"],
    "tile": ["flooring", "tiling"],
    "landscaping": ["landscaper", "landscapers", "lawn care"],
    "landscaper": ["landscaping", "landscapers", "lawn care"],
    "landscapers": ["landscaping", "landscaper", "lawn care"],
    "demolition": ["wrecking", "excavation"],
    "excavation": ["earthwork", "demolition", "grading"],
    "concrete": ["cement", "masonry", "paving"],
    "paving": ["asphalt", "concrete", "pavement"],
}

_GENERIC_WORDS = {"contractor", "contractors", "constructor", "constructors", "companies", "company", "business", "businesses"}
_CONTRACTOR_WORDS = {"contractor", "contractors", "constructor", "constructors"}


def category_term_variations(value: Union[str, List[str], None]) -> Tuple[List[str], List[str]]:
    """Split category/trade into (contractor_terms, non_contractor_terms).

    - contractor_terms: variations containing 'contractor', 'contractors', 'constructor', etc.
    - non_contractor_terms: base trade terms and aliases without generic words.
    """
    if not value:
        return ([], [])

    if isinstance(value, (list, tuple, set)):
        raw_inputs = [str(item) for item in value if item]
    else:
        raw_inputs = [str(value)]

    # Split on commas or semicolons
    raw_items: List[str] = []
    for item in raw_inputs:
        for part in re.split(r"[,;]+", item):
            part = part.strip()
            if part:
                raw_items.append(part)

    contractor_terms: List[str] = []
    non_contractor_terms: List[str] = []

    def _clean_term(t: str) -> str:
        t = re.sub(r"\s+", " ", t.strip().lower())
        # Clean double contractor words e.g. "contractors contractors" -> "contractors"
        t = re.sub(r"\b(contractors?|constructors?)\s+(contractors?|constructors?)\b", r"\1", t)
        return t.strip()

    def _add_contractor(t: str) -> None:
        t = _clean_term(t)
        if t and t not in contractor_terms:
            contractor_terms.append(t)

    def _add_non_contractor(t: str) -> None:
        t = _clean_term(t)
        # Strip generic words if present at boundaries
        words = t.split()
        filtered = [w for w in words if w not in _GENERIC_WORDS]
        cleaned = " ".join(filtered).strip()
        if cleaned and cleaned not in non_contractor_terms:
            non_contractor_terms.append(cleaned)

    for raw in raw_items:
        # Normalize abbreviations like A/C -> ac
        norm_raw = re.sub(r"\ba\s*/\s*c\b", "ac", raw, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", norm_raw.strip().lower())
        if not text:
            continue

        words = re.findall(r"[a-z0-9]+", text)
        if not words:
            continue

        has_contractor_word = any(w in _CONTRACTOR_WORDS for w in words)
        base_words = [w for w in words if w not in _GENERIC_WORDS]
        base_trade = " ".join(base_words).strip()

        # Handle compound trades with '&', '/' or 'and'
        sub_trades = []
        if any(sep in raw for sep in ["&", "/", " and "]):
            compound_parts = re.split(r"(?:&|/|\band\b)", norm_raw, flags=re.IGNORECASE)
            for cp in compound_parts:
                cp_words = [w for w in re.findall(r"[a-z0-9]+", cp.lower()) if w not in _GENERIC_WORDS]
                if cp_words:
                    sub_trades.append(" ".join(cp_words).strip())

        lookup_trades = [base_trade] if base_trade else []
        for st in sub_trades:
            if st and st not in lookup_trades:
                lookup_trades.append(st)

        if has_contractor_word:
            # Preserve original contractor variation
            _add_contractor(text)
            if base_trade:
                _add_contractor(f"{base_trade} contractors")
                _add_contractor(f"{base_trade} contractor")
                _add_non_contractor(base_trade)
            else:
                _add_contractor("contractors")
                _add_contractor("contractor")
        else:
            _add_non_contractor(text)
            _add_contractor(f"{text} contractors")
            _add_contractor(f"{text} contractor")
            if base_trade and base_trade != text:
                _add_non_contractor(base_trade)
                _add_contractor(f"{base_trade} contractors")
                _add_contractor(f"{base_trade} contractor")

        for lt in lookup_trades:
            if lt:
                _add_non_contractor(lt)
                _add_contractor(f"{lt} contractors")
                _add_contractor(f"{lt} contractor")
                for alias in TRADE_ALIASES.get(lt, []):
                    _add_non_contractor(alias)
                    base_alias = re.sub(r"s$", "", alias) if alias.endswith("s") and not alias.endswith("ss") else alias
                    _add_contractor(f"{alias} contractors")
                    _add_contractor(f"{alias} contractor")
                    if base_alias != alias:
                        _add_contractor(f"{base_alias} contractors")
                        _add_contractor(f"{base_alias} contractor")

    # If base trade is roofing/roofer, ensure roofer/roofers are in non_contractor
    for term in list(non_contractor_terms):
        if "roofing" in term:
            _add_non_contractor("roofer")
            _add_non_contractor("roofers")
        elif "roofer" in term:
            _add_non_contractor("roofing")

    return contractor_terms, non_contractor_terms


def category_terms(value: Union[str, List[str], None]) -> List[str]:
    """Returns all category search terms, prioritizing contractor variations."""
    contractor_terms, non_contractor = category_term_variations(value)
    seen = set()
    result = []
    for term in contractor_terms + non_contractor:
        if term not in seen:
            seen.add(term)
            result.append(term)
    return result


def normalize_city(value: str | None) -> str | None:
    if not value: return None
    clean = re.sub(r"[^\w\s-]", "", str(value))
    clean = " ".join(clean.split()).title()
    if clean.lower().replace(" ", "") in {"newyorkcity", "nyc"}:
        return "New York"
    return clean


class SearchCriteria(BaseModel):
    category: str | None = None
    user_keyword: str | None = None
    us_state: str | None = None
    city: str | None = None
    record_kind: str | None = None
    quantity: int = Field(default=20, ge=1)
    has_email: bool = False
    has_phone: bool = False
    source: str | None = None
    fresh_within_days: int | None = Field(default=None, ge=1)
    include_expired: bool = False
    new_only: bool = False

    @field_validator("city", mode="before")
    @classmethod
    def clean_city(cls, value):
        return normalize_city(value)

    @field_validator("category", mode="before")
    @classmethod
    def clean_category(cls, value):
        if not value:
            return None
        if isinstance(value, (list, tuple, set)):
            items = [str(v).strip() for v in value if v and str(v).strip()]
            if not items:
                return None
            non_generic = [
                v for v in items
                if v.casefold() not in {'contractor', 'contractors', 'constructor', 'constructors', 'company', 'companies', 'business', 'businesses'}
            ]
            if not non_generic:
                return None
            value = ", ".join(items)
        value = re.sub(r"\s+", " ", str(value).strip())
        if not value:
            return None
        return None if value.casefold() in {'contractor', 'contractors', 'constructor', 'constructors', 'company', 'companies', 'business', 'businesses'} else value

    @field_validator("record_kind")
    @classmethod
    def clean_kind(cls, value):
        if value not in (None, 'company', 'opportunity'):
            raise ValueError('Record kind must be company or opportunity')
        return value

    @field_validator("source", mode="before")
    @classmethod
    def clean_source(cls, value):
        #return 'nyscr' if str(value).casefold() == 'ny' else str(value).strip().casefold() if value else None
        if not value:
            return None
        raw = str(value).strip().casefold()
        if raw == "ny":
            return "nyscr"
        compact = re.sub(r"[^a-z0-9]", "", raw)
        compact_no_suffix = re.sub(r"(scrappers?|scrapers?)$", "", compact)
        try:
            from Backend.scrappers.controller import list_scrapers
            for meta in list_scrapers():
                mid = meta.id.casefold()
                mname = re.sub(r"(scrappers?|scrapers?)$", "", re.sub(r"[^a-z0-9]", "", meta.name.casefold()))
                if compact in (mid, mname) or compact_no_suffix in (mid, mname):
                    return meta.id
        except Exception:
            pass
        return compact_no_suffix or compact or raw
    
    @field_validator("us_state", mode="before")
    @classmethod
    def clean_state(cls, value):
        if not value:
            return None
        state = normalize_state(value)
        if not state:
            raise ValueError("A valid US state name or code is required")
        return state

    @classmethod
    def from_slots(cls, slots):
        values = dict(slots or {})
        required = values.pop("required_fields", {}) or {}
        if "quantity" not in values and values.get("limit"): values["quantity"] = values["limit"]
        if "category" not in values and values.get("keyword"): values["category"] = values["keyword"]
        values.setdefault("has_email", bool(required.get("has_email") or required.get("email")))
        values.setdefault("has_phone", bool(required.get("has_phone") or required.get("phone")))
        return cls.model_validate({k: v for k, v in values.items() if k in cls.model_fields and v is not None})

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()
