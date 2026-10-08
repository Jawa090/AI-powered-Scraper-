"""Canonical search criteria shared by chat, completion and persistence."""
import hashlib
import json
import re
from pydantic import BaseModel, Field, field_validator
from Database.normalize import normalize_state


def normalize_city(value):
    if not value:
        return None
    clean = re.sub(r"\s+", " ", str(value).strip())
    if re.sub(r"[^a-z]", "", clean.lower()) in {"newyork", "newyorkcity", "nyc", "ny"}:
        return "New York"
    return clean


def category_terms(value):
    text = (value or "").lower()
    text = re.sub(r"\broofers?\b", "roofing", text)
    words = re.findall(r"[a-z0-9]+", text)
    generic = {"contractor", "contractors", "constructor", "constructors", "companies", "company", "business", "businesses"}
    return [word for word in words if word not in generic] or words


class SearchCriteria(BaseModel):
    category: str | None = None
    city: str | None = None
    us_state: str | None = None
    record_kind: str | None = None
    quantity: int = Field(default=20, ge=1)
    has_email: bool = False
    has_phone: bool = False
    source: str | None = None
    fresh_within_days: int | None = Field(default=None, ge=1)
    include_expired: bool = False
    new_only: bool = False

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
        return 'nyscr' if str(value).casefold() == 'ny' else str(value).strip().casefold() if value else None

    @field_validator("city", mode="before")
    @classmethod
    def clean_city(cls, value):
        return normalize_city(value)

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
