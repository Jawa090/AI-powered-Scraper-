"""
agents/intent/models.py
───────────────────────
Strongly Validated Structured Intent Models using Pydantic.
Enforces the LLM boundary: all LLM parsing must validate against these models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class IntentType(str, Enum):
    LEAD_DISCOVERY = "lead_discovery"
    DATABASE_SEARCH = "database_search"
    SCRAPER_REQUEST = "scraper_request"
    DATASET_QUERY = "dataset_query"
    JOB_STATUS = "job_status"
    GENERAL_INFORMATION = "general_information"


class StructuredIntent(BaseModel):
    """
    Strongly typed, validated schema representing the user's intent.
    Parsed by IntentEngine from LLM or controlled rule-based fallback.
    """

    intent: IntentType = Field(
        ...,
        description="Classified user intent type.",
    )
    needs_database: bool = Field(
        default=False,
        description="Whether query requires checking or retrieving from PostgreSQL.",
    )
    needs_scraping: bool = Field(
        default=False,
        description="Whether query requires initiating or selecting an external scraping job.",
    )
    category: Optional[str] = Field(
        default=None,
        description="Industry, trade, or subject matter category (e.g., 'Commercial Contractor', 'Plumber').",
    )
    location: Optional[str] = Field(
        default=None,
        description="Geographic region or city (e.g., 'Dallas', 'New York').",
    )
    quantity: Optional[int] = Field(
        default=None,
        description="Number of target records requested (1 to 50000).",
    )
    fields: List[str] = Field(
        default_factory=list,
        description="Specific fields requested by user (e.g., ['email', 'phone', 'website']).",
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value search filters.",
    )
    freshness: bool = Field(
        default=False,
        description="Whether real-time/latest/live data was requested.",
    )
    scraper_id: Optional[str] = Field(
        default=None,
        description="Identified scraper ID (must match execution/registry.py SCRIPTS_REGISTRY).",
    )
    dataset_id: Optional[str] = Field(
        default=None,
        description="Target dataset ID if inquiring about an existing dataset.",
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Target job ID if inquiring about job status or logs.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Model confidence score between 0.0 and 1.0.",
    )
    user_request: str = Field(
        default="",
        description="Original raw user message.",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief explanation of why this intent and parameters were selected.",
    )
    is_fallback: bool = Field(
        default=False,
        description="Whether this intent was produced by rule-based fallback parser.",
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Reason why fallback parser was utilized.",
    )

    @field_validator("quantity")
    @classmethod
    def validate_quantity_bounds(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if v < 1 or v > 50000:
                raise ValueError(f"Quantity {v} is outside allowed bounds [1, 50000].")
        return v

    @field_validator("fields")
    @classmethod
    def sanitize_field_names(cls, v: List[str]) -> List[str]:
        allowed = {
            "email", "phone", "website", "contact_person", "address",
            "title", "organization_name", "category", "location", "status"
        }
        return [f.strip().lower() for f in v if f.strip().lower() in allowed]

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
