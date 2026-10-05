from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, Union

from scrappers.base import (
    BaseScraper,
    InvalidScrapeParams,
    JobCancelled,
    ScrapeContext,
    ScrapeParams,
    ScraperException,
    ScraperMeta,
    ScraperNotReady,
    StandardRecord,
    UnknownScraper,
)
from scrappers.bonfire import BonfireScraper
from scrappers.dasny import DasnyScraper
from scrappers.jwiz import JWizScraper
from scrappers.nyscr import NyscrScraper
from settings import settings

logger = logging.getLogger(__name__)

# To add a scraper: copy _template.py to scrappers/<name>.py, implement it,
# import it above and add its class below. Nothing else changes.
REGISTERED_SCRAPERS: Tuple[Type[BaseScraper], ...] = (
    BonfireScraper,
    DasnyScraper,
    JWizScraper,
    NyscrScraper,
)

# ---------------------------------------------------------------------------
# Import-time validation of registered scrapers
# ---------------------------------------------------------------------------
_SEEN_IDS = set()
for scraper_cls in REGISTERED_SCRAPERS:
    if not issubclass(scraper_cls, BaseScraper):
        raise TypeError(f"Registered scraper {scraper_cls} must subclass BaseScraper")
    if not hasattr(scraper_cls, "meta") or not isinstance(scraper_cls.meta, ScraperMeta):
        raise AttributeError(f"Registered scraper {scraper_cls} must define 'meta' of type ScraperMeta")
    sid = scraper_cls.meta.id
    if not sid or not sid.islower() or not sid.isalnum():
        raise ValueError(f"Scraper id '{sid}' must be non-empty lowercase alphanumeric")
    if sid in _SEEN_IDS:
        raise ValueError(f"Duplicate scraper id '{sid}' found in REGISTERED_SCRAPERS")
    _SEEN_IDS.add(sid)


# ---------------------------------------------------------------------------
# Public Discovery and Introspection API
# ---------------------------------------------------------------------------

def list_scrapers() -> List[ScraperMeta]:
    """Return ScraperMeta for all registered scrapers."""
    return [cls.meta for cls in REGISTERED_SCRAPERS]


def scraper_ids() -> List[str]:
    """Return list of registered lowercase scraper IDs."""
    return [cls.meta.id for cls in REGISTERED_SCRAPERS]


def get_scraper_class(scraper_id: str) -> Type[BaseScraper]:
    """Return scraper class for the given ID or raise UnknownScraper."""
    clean_id = (scraper_id or "").strip().lower()
    for cls in REGISTERED_SCRAPERS:
        if cls.meta.id == clean_id:
            return cls
    raise UnknownScraper(f"Unknown scraper '{scraper_id}'. Registered: {scraper_ids()}")


def get_meta(scraper_id: str) -> ScraperMeta:
    """Retrieve metadata for a scraper ID; raises UnknownScraper if not found."""
    return get_scraper_class(scraper_id).meta


def check_ready(scraper_id: str) -> Tuple[bool, Optional[str]]:
    """
    Check if required environment variables and credentials are configured for scraper.
    Returns (True, None) if ready, or (False, reason) if blocked.
    """
    meta = get_meta(scraper_id)
    for env_var in meta.required_env:
        val = getattr(settings, env_var, None) or os.getenv(env_var)
        if not val:
            return False, f"Missing required environment variable: {env_var}"
    return True, None


def validate_params(scraper_id: str, raw: Union[Dict[str, Any], ScrapeParams]) -> ScrapeParams:
    """
    Strict validation of scrape parameters against scraper metadata.
    Raises InvalidScrapeParams with explicit reason; no silent clamping or dropping.
    """
    meta = get_meta(scraper_id)
    if isinstance(raw, ScrapeParams):
        raw_dict = raw.model_dump()
    else:
        raw_dict = dict(raw or {})

    limit_val = raw_dict.get("limit")
    if limit_val is None:
        limit = meta.default_limit
    else:
        try:
            limit = int(limit_val)
        except (ValueError, TypeError):
            raise InvalidScrapeParams(f"Invalid limit '{limit_val}': must be an integer")
        if limit < 1 or limit > meta.max_limit:
            raise InvalidScrapeParams(
                f"Limit {limit} is outside allowed range [1, {meta.max_limit}] for scraper '{scraper_id}'"
            )

    kw = raw_dict.get("keyword")
    if kw is not None and str(kw).strip():
        if "keyword" not in meta.supports:
            raise InvalidScrapeParams(f"Scraper '{scraper_id}' does not support keyword filtering")

    city = raw_dict.get("city")
    us_state = raw_dict.get("us_state")
    loc = raw_dict.get("location")
    if (city or us_state or loc) and "location" not in meta.supports:
        raise InvalidScrapeParams(f"Scraper '{scraper_id}' does not support location filtering")

    timeout_s = raw_dict.get("timeout_s", 60)
    try:
        timeout_s = int(timeout_s)
    except (ValueError, TypeError):
        raise InvalidScrapeParams(f"Invalid timeout_s '{timeout_s}': must be an integer")

    return ScrapeParams(
        limit=limit,
        keyword=str(kw).strip() if kw else None,
        city=str(city).strip() if city else None,
        us_state=str(us_state).strip() if us_state else None,
        location=str(loc).strip() if loc else None,
        timeout_s=timeout_s,
    )


def describe_for_llm() -> List[Dict[str, Any]]:
    """Format scraper catalog for LLM system prompt and tool descriptions."""
    out = []
    for cls in REGISTERED_SCRAPERS:
        meta = cls.meta
        ready, reason = check_ready(meta.id)
        out.append({
            "id": meta.id,
            "name": meta.name,
            "description": meta.description,
            "record_kind": meta.record_kind,
            "coverage": meta.coverage,
            "supports": meta.supports,
            "fields": meta.fields,
            "ready": ready,
            "unready_reason": reason if not ready else None,
        })
    return out


def to_api_dict(meta: ScraperMeta) -> Dict[str, Any]:
    """Convert ScraperMeta to the frontend Script representation."""
    ready, reason = check_ready(meta.id)
    return {
        "id": meta.id,
        "name": meta.name,
        "description": meta.description,
        "category": meta.category,
        "recordKind": meta.record_kind,
        "coverage": meta.coverage,
        "supports": meta.supports,
        "fields": meta.fields,
        "defaultLimit": meta.default_limit,
        "maxLimit": meta.max_limit,
        "version": meta.version,
        "ready": ready,
        "unreadyReason": reason if not ready else None,
    }


# ---------------------------------------------------------------------------
# Execution Dispatcher
# ---------------------------------------------------------------------------

def run(
    scraper_id: str,
    params: Union[Dict[str, Any], ScrapeParams],
    ctx: Optional[ScrapeContext] = None,
) -> Iterator[StandardRecord]:
    """
    Primary execution dispatch for running any registered scraper.
    Yields StandardRecord items.
    Checks ctx.should_cancel(); JobCancelled propagates.
    Calls scraper.close() in finally block.
    """
    clean_id = (scraper_id or "").strip().lower()
    scraper_cls = get_scraper_class(clean_id)
    validated_params = validate_params(clean_id, params)

    # Fixture mode (testing only)
    if settings.SCRAPER_MODE == "fixture":
        if settings.ENVIRONMENT != "test":
            raise RuntimeError("SCRAPER_MODE='fixture' is only permitted when ENVIRONMENT='test'")
        logger.info("Running scraper '%s' in fixture mode", clean_id)
        fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / clean_id
        fixture_file = fixtures_dir / "records.json"
        if not fixture_file.exists():
            raise FileNotFoundError(f"Fixture file not found: {fixture_file}")
        
        with open(fixture_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        scraper = scraper_cls(ctx=ctx)
        count = 0
        try:
            for item in data:
                if ctx and ctx.should_cancel():
                    raise JobCancelled(f"Scraper '{clean_id}' cancelled during fixture execution")
                if count >= validated_params.limit:
                    break
                # If fixture is already in StandardRecord shape, validate it, otherwise use to_standard
                if "source_code" in item and "record_kind" in item:
                    yield StandardRecord(**item)
                else:
                    yield scraper.to_standard(item)
                count += 1
        finally:
            scraper.close()
        return

    # Live execution mode
    ready, reason = check_ready(clean_id)
    if not ready:
        raise ScraperNotReady(f"Scraper '{clean_id}' is not ready: {reason}")

    scraper = scraper_cls(ctx=ctx)
    try:
        for record in scraper.run(validated_params):
            if ctx and ctx.should_cancel():
                raise JobCancelled(f"Scraper '{clean_id}' cancelled by context")
            yield record
    finally:
        scraper.close()
