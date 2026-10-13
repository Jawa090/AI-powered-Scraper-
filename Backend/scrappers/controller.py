from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, Union
import importlib

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
from settings import settings
from scrappers.utils import state_code, to_json_safe

logger = logging.getLogger(__name__)

SCRAPER_PATHS = [
    "scrappers.bonfire:BonfireScraper",
    "scrappers.dasny:DasnyScraper",
    "scrappers.jwiz:JWizScraper",
    "scrappers.nyscr:NyscrScraper",
]

REGISTERED_SCRAPERS: List[Type[BaseScraper]] = []
_IMPORT_ERRORS = {}

for path in SCRAPER_PATHS:
    mod_path, cls_name = path.split(":")
    scraper_id = mod_path.split(".")[-1]
    try:
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        REGISTERED_SCRAPERS.append(cls)
    except Exception as e:
        logger.error(f"Failed to load scraper {scraper_id}: {e}")
        _IMPORT_ERRORS[scraper_id] = f"Import error: {e}"
        # Create a placeholder to ensure it shows up in API with ready=False
        meta = ScraperMeta(
            id=scraper_id,
            name=cls_name.replace("Scraper", ""),
            description="Failed to load module.",
            record_kind="opportunity",
            category="Unknown",
            version="0.0.0",
            coverage={},
            supports=[],
            fields=[],
            required_env=[]
        )
        class BrokenScraper(BaseScraper):
            def scrape(self, params):
                pass
            def to_standard(self, raw):
                pass
        BrokenScraper.meta = meta
        REGISTERED_SCRAPERS.append(BrokenScraper)

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
    if scraper_id in _IMPORT_ERRORS:
        return False, _IMPORT_ERRORS[scraper_id]

    if getattr(settings, "SCRAPER_MODE", "") == "fixture":
        return True, None

    meta = get_meta(scraper_id)
    for env_var in meta.required_env:
        val = getattr(settings, env_var, None)
        if not val:
            return False, f"Missing required environment variable: {env_var}"
    return True, None


def validate_params(scraper_id: str, raw: Union[Dict[str, Any], ScrapeParams]) -> ScrapeParams:
    """
    Adjust scrape parameters to match scraper capabilities, or raise if unsupported.
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

        if limit < 1:
            raise InvalidScrapeParams(f"Limit {limit} must be >= 1")
        # We don't cap to max_limit, per test expectations.

    kw = raw_dict.get("keyword")
    if kw is not None and str(kw).strip():
        if "keyword" not in meta.supports:
            raise InvalidScrapeParams(f"Scraper '{scraper_id}' does not support keyword filtering")

    city = raw_dict.get("city")
    city = str(city).strip() if city else None

    us_state = raw_dict.get("us_state")
    if us_state:
        us_state = state_code(us_state)

    loc = raw_dict.get("location")
    if loc:
        loc = str(loc).strip()
        if not city or not us_state:
            from Database.normalize import parse_location, normalize_state
            parsed_city, parsed_state, _ = parse_location(loc)
            if not city and parsed_city:
                city = parsed_city
            if not us_state and parsed_state:
                us_state = parsed_state
            if not us_state:
                us_state = normalize_state(loc)
            if not city and not us_state:
                city = loc

    # Drop location when city or us_state is present
    if city or us_state:
        loc = None

    # Check if a location filter is entirely inside the scraper's coverage
    has_location_filter = city or us_state or loc

    if meta.requires_location and not has_location_filter:
        raise InvalidScrapeParams(f"{meta.name} requires a city or state before it can run. "
            "Ask the user for a search location; an unrestricted database search is still allowed.")

    if has_location_filter:
        cov_city = meta.coverage.get("city")
        cov_state = meta.coverage.get("state")

        if cov_city and city and city.casefold() != cov_city.casefold():
            raise InvalidScrapeParams(f"Source covers {cov_city}, not {city}")
        if cov_state and us_state and us_state != cov_state:
            raise InvalidScrapeParams(f"Source covers {cov_state}, not {us_state}")
        covered = bool(cov_city or cov_state) and (not city or (cov_city and city.casefold() == cov_city.casefold())) and (not us_state or us_state == cov_state)
        if covered:
            city = us_state = loc = None
        elif 'location' not in meta.supports:
            raise InvalidScrapeParams(f"Scraper '{scraper_id}' does not support the requested location")

    timeout_s = raw_dict.get("timeout_s", 60)
    try:
        timeout_s = int(timeout_s)
    except (ValueError, TypeError):
        raise InvalidScrapeParams(f"Invalid timeout_s '{timeout_s}': must be an integer")

    return ScrapeParams(
        limit=limit,
        keyword=str(kw).strip() if kw else None,
        city=city,
        us_state=us_state,
        location=loc,
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
            "requires_location": meta.requires_location,
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
        "requiresLocation": meta.requires_location,
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
                    rec = StandardRecord(**item)
                else:
                    rec = scraper.to_standard(item)
                rec.extra = to_json_safe(rec.extra)
                yield rec
                count += 1
        finally:
            scraper.close()
        return

    # Live execution mode
    ready, reason = check_ready(clean_id)
    if not ready:
        raise ScraperNotReady(f"Scraper '{clean_id}' is not ready: {reason}")

    # Set headless default from settings. NYSCR overrides this in its own class if needed.
    if clean_id == "nyscr":
        headless = getattr(settings, "NYSCR_HEADLESS", None)
    else:
        headless = settings.SCRAPER_HEADLESS
    scraper = scraper_cls(ctx=ctx, headless=headless)

    try:
        for record in scraper.run(validated_params):
            yield record
    finally:
        scraper.close()
