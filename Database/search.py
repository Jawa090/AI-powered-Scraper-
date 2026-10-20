"""Canonical search criteria shared by chat, completion and persistence."""
from google.genai._gaos.types.credentials import environmentvariableupdateconfig
import hashlib
import json
import re
from pydantic import BaseModel, Field, field_validator
from Database.normalize import normalize_state
import sys
from pathlib import Path

dir=Path(__file__).resolve().parent.parent


def category_terms(value):
    text = (value or "").lower()
    text = re.sub(r"\broofers?\b", "roofing", text)
    words = re.findall(r"[a-z0-9]+", text)
    generic = {"contractor", "contractors", "constructor", "constructors", "companies", "company", "business", "businesses"}
    return [word for word in words if word not in generic] or words


def normalize_city(value: str | None) -> str | None:
    if not value: return None
    value = re.sub(r"[^\w\s-]", "", str(value))
    return " ".join(value.split()).title()


class SearchCriteria(BaseModel):
    category: str | None = None
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
        if not value: return None
        value = re.sub(r"\s+", " ", str(value).strip())
        return None if value.casefold() in {'contractor', 'contractors', 'constructor', 'constructors', 'company', 'companies'} else value

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
