"""
_template.py
────────────
Template for adding a new modular scraper to the framework.

Steps to add a new scraper:
1. Copy this file to Backend/scrappers/<name>.py (e.g. Backend/scrappers/mysource.py).
2. Define class <Name>Scraper(BaseScraper) with ScraperMeta.
3. Implement scrape(self, params: ScrapeParams) yielding raw dictionaries.
4. Implement to_standard(self, raw: Dict[str, Any]) -> StandardRecord mapping raw fields.
5. Create offline fixture test data in Backend/tests/fixtures/<name>/records.json.
6. Register the scraper class in Backend/scrappers/controller.py in REGISTERED_SCRAPERS.
7. Run `pytest -k scraper` to verify contracts and integration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, Optional

from scrappers.base import (
    BaseScraper,
    ScrapeContext,
    ScrapeParams,
    ScraperMeta,
    StandardRecord,
)

logger = logging.getLogger(__name__)


class TemplateScraper(BaseScraper):
    """Template scraper implementation."""

    meta = ScraperMeta(
        id="template",
        name="Template Portal Scraper",
        description="Extracts opportunities or business leads from Template Portal.",
        record_kind="opportunity",  # 'opportunity' or 'company'
        category="Public Procurement",
        version="1.0.0",
        coverage={"state": "US"},
        supports=["limit", "keyword", "location"],  # subset of ['limit', 'keyword', 'location']
        fields=[
            "source_code",
            "record_kind",
            "external_id",
            "source_url",
            "title",
            "description",
            "organization_name",
            "contact_name",
            "contact_title",
            "email",
            "phone",
            "website",
            "city",
            "us_state",
            "postal_code",
            "category",
            "due_at",
        ],
        required_env=[],  # e.g. ["TEMPLATE_API_KEY"] if credentials required
        default_limit=20,
        max_limit=100,
    )

    def __init__(self, ctx: Optional[ScrapeContext] = None) -> None:
        super().__init__(ctx)
        # Initialize client/browser resources here without raising on missing credentials

    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """
        Execute raw data extraction.
        Yields raw dictionary items.
        Respects params.limit, params.keyword, params.city/us_state/location.
        Checks self.ctx.should_cancel() periodically.
        """
        logger.info("Starting scrape with params: %s", params)
        # Example extraction loop:
        # for raw_item in fetch_items():
        #     if self.ctx.should_cancel():
        #         break
        #     yield raw_item
        yield {}

    def to_standard(self, raw: Dict[str, Any]) -> StandardRecord:
        """
        Transform a raw extracted dictionary into the canonical StandardRecord.
        Must never fabricate data; missing fields should be set to None.
        """
        return StandardRecord(
            source_code=self.meta.id,
            record_kind=self.meta.record_kind,
            external_id=raw.get("id"),
            source_url=raw.get("url"),
            title=raw.get("title"),
            description=raw.get("description"),
            organization_name=raw.get("organization_name"),
            contact_name=raw.get("contact_name"),
            contact_title=raw.get("contact_title"),
            email=raw.get("email"),
            phone=raw.get("phone"),
            website=raw.get("website"),
            city=raw.get("city"),
            us_state=raw.get("state"),
            postal_code=raw.get("postal_code"),
            category=raw.get("category"),
            due_at=raw.get("due_at"),
            extra=raw.get("extra", {}),
        )

    def close(self) -> None:
        """Clean up connections, browser windows, or temporary resources. Safe to call twice."""
        super().close()
