from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ScraperException(Exception):
    """Base exception for all scraper errors."""
    pass


class UnknownScraper(ScraperException):
    """Raised when an unregistered scraper ID is requested."""
    pass


class InvalidScrapeParams(ScraperException):
    """Raised when scrape parameters fail validation."""
    pass


class ScraperNotReady(ScraperException):
    """Raised when required environment configuration or credentials are missing."""
    pass


class JobCancelled(ScraperException):
    """Raised when a scrape job is cancelled during execution."""
    pass


# ---------------------------------------------------------------------------
# Metadata and Parameters Models
# ---------------------------------------------------------------------------

class ScraperMeta(BaseModel):
    """Metadata describing a scraper's capabilities, coverage, and requirements."""
    id: str = Field(..., description="Unique lowercase identifier, e.g. 'bonfire'")
    name: str = Field(..., description="Human-readable name of the scraper")
    description: str = Field(..., description="Detailed description of what the scraper extracts")
    record_kind: str = Field(..., description="Kind of records: 'opportunity' or 'company'")
    category: str = Field(..., description="High-level category, e.g. 'Government & Municipal Bids'")
    version: str = Field(..., description="Semantic version string, e.g. '1.0.0'")
    coverage: Dict[str, Any] = Field(..., description="Geographical coverage, e.g. {'city': 'Dallas', 'state': 'TX'}")
    supports: List[str] = Field(..., description="Supported filtering features: subset of ['limit', 'keyword', 'location']")
    fields: List[str] = Field(..., description="List of standard fields populated by this scraper")
    required_env: List[str] = Field(default_factory=list, description="Environment variable names required for operation")
    default_limit: int = Field(default=20, ge=1, description="Default record extraction limit")
    max_limit: int = Field(default=100, ge=1, description="Maximum record extraction limit")


class ScrapeParams(BaseModel):
    """Parameters passed to a scraper run."""
    limit: int = Field(default=20, ge=1)
    keyword: Optional[str] = None
    city: Optional[str] = None
    us_state: Optional[str] = None
    location: Optional[str] = None
    timeout_s: int = Field(default=60, ge=1)


# ---------------------------------------------------------------------------
# Scrape Context Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ScrapeContext(Protocol):
    """Execution context provided by worker/job runners for telemetry, logging, and cancellation."""
    def log(self, level: str, msg: str) -> None:
        ...

    def progress(self, pct: float, step: str) -> None:
        ...

    def should_cancel(self) -> bool:
        ...

    def wait_for_user(self, reason: str) -> bool:
        ...


class NullScrapeContext:
    """Default no-op context implementation used when no external context is provided."""
    def log(self, level: str, msg: str) -> None:
        lvl = getattr(logging, level.upper(), logging.INFO)
        logger.log(lvl, msg)

    def progress(self, pct: float, step: str) -> None:
        logger.debug("Progress %.1f%%: %s", pct, step)

    def should_cancel(self) -> bool:
        return False

    def wait_for_user(self, reason: str) -> bool:
        logger.info("Scraper requested user intervention: %s", reason)
        return True


# ---------------------------------------------------------------------------
# Standard Record Model
# ---------------------------------------------------------------------------

class StandardRecord(BaseModel):
    """Canonical lead/opportunity record produced by all scrapers."""
    source_code: str = Field(..., description="Lowercase source code, e.g. 'bonfire'")
    record_kind: str = Field(..., description="'opportunity' or 'company'")
    external_id: Optional[str] = Field(default=None, description="Per-source unique identifier")
    source_url: Optional[str] = Field(default=None, description="URL of the specific opportunity or company")
    title: Optional[str] = Field(default=None, description="Title of the bid or business headline")
    description: Optional[str] = Field(default=None, description="Detailed text or scope description")
    organization_name: Optional[str] = Field(default=None, description="Issuing agency or company name")
    contact_name: Optional[str] = Field(default=None, description="Point of contact name")
    contact_title: Optional[str] = Field(default=None, description="Point of contact job title")
    email: Optional[str] = Field(default=None, description="Contact email address")
    phone: Optional[str] = Field(default=None, description="Contact phone number")
    website: Optional[str] = Field(default=None, description="Website URL")
    city: Optional[str] = Field(default=None, description="City name")
    us_state: Optional[str] = Field(default=None, description="2-letter US state code or full state")
    postal_code: Optional[str] = Field(default=None, description="ZIP or postal code")
    category: Optional[str] = Field(default=None, description="Industry or category classification")
    due_at: Optional[datetime] = Field(default=None, description="Bid submission deadline or closing timestamp")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Raw metadata or additional attributes")


# Backwards compatibility alias
RawRecord = StandardRecord


# ---------------------------------------------------------------------------
# Base Scraper Abstract Class
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    """Abstract base class for all modular scrapers."""
    meta: ScraperMeta

    def __init__(self, ctx: Optional[ScrapeContext] = None) -> None:
        self.ctx: ScrapeContext = ctx or NullScrapeContext()
        self._is_closed: bool = False

    @abstractmethod
    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """Execute extraction yielding raw dictionary records."""
        pass

    @abstractmethod
    def to_standard(self, raw: Dict[str, Any]) -> StandardRecord:
        """Transform a raw source dictionary into a canonical StandardRecord."""
        pass

    def run(self, params: ScrapeParams) -> Iterator[StandardRecord]:
        """High-level runner iterating over scrape() and converting via to_standard()."""
        try:
            for raw in self.scrape(params):
                if self.ctx.should_cancel():
                    self.ctx.log("warning", "Scraper execution cancelled by context.")
                    raise JobCancelled(f"Scraper '{self.meta.id}' cancelled by context")
                yield self.to_standard(raw)
        finally:
            self.close()

    def check_credentials(self) -> tuple[bool, Optional[str]]:
        """Pre-flight credential check based on required_env."""
        from settings import settings
        for env_var in self.meta.required_env:
            val = getattr(settings, env_var, None)
            if not val:
                return False, f"Missing required environment variable: {env_var}"
        return True, None

    def close(self) -> None:
        """Clean up browser drivers and network sessions. Safe to call multiple times."""
        self._is_closed = True


# Canonical alias
ScraperBase = BaseScraper
