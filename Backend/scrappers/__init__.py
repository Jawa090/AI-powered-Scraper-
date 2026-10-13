"""
scrappers/__init__.py
─────────────────────
Modular Scraper Framework Entrypoint.
Delegates all discovery, introspection, and execution to scrappers.controller.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scrappers.controller import (
    REGISTERED_SCRAPERS,
    check_ready,
    describe_for_llm,
    get_meta,
    get_scraper_class,
    list_scrapers,
    run,
    scraper_ids,
    to_api_dict,
    validate_params,
)


def run_scraper(scraper_id: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Legacy compatibility bridge to execute scraper and return serialized records."""
    return [record.model_dump() for record in run(scraper_id, params)]


def get_scraper_info(scraper_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve API dictionary representation for a scraper ID."""
    try:
        meta = get_meta(scraper_id)
        return to_api_dict(meta)
    except Exception:
        return None


__all__ = [
    "REGISTERED_SCRAPERS",
    "check_ready",
    "describe_for_llm",
    "get_meta",
    "get_scraper_class",
    "get_scraper_info",
    "list_scrapers",
    "run",
    "run_scraper",
    "scraper_ids",
    "to_api_dict",
    "validate_params",
]
