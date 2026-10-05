"""
test_scraper_contract.py
─────────────────────────
Contract tests verifying all registered scrapers adhere to the modular scraper specification.
Parametrized over scrappers.controller.REGISTERED_SCRAPERS.
"""

import json
from pathlib import Path
import pytest

from scrappers.base import (
    BaseScraper,
    InvalidScrapeParams,
    ScrapeParams,
    StandardRecord,
)
from scrappers.controller import (
    REGISTERED_SCRAPERS,
    describe_for_llm,
    get_meta,
    list_scrapers,
    scraper_ids,
    validate_params,
)


@pytest.mark.unit
@pytest.mark.parametrize("scraper_cls", REGISTERED_SCRAPERS)
def test_scraper_meta_valid(scraper_cls):
    """Verify that ScraperMeta is properly and completely defined."""
    assert issubclass(scraper_cls, BaseScraper)
    meta = scraper_cls.meta

    assert meta.id, "Scraper ID must be non-empty"
    assert meta.id.islower(), f"Scraper ID '{meta.id}' must be lowercase"
    assert meta.id.isalnum(), f"Scraper ID '{meta.id}' must be alphanumeric"
    assert meta.name, "Name must be non-empty"
    assert meta.description, "Description must be non-empty"
    assert meta.record_kind in ("opportunity", "company"), f"Invalid record_kind: {meta.record_kind}"
    assert meta.category, "Category must be non-empty"
    assert meta.version, "Version must be non-empty"
    assert isinstance(meta.coverage, dict) and meta.coverage, "Coverage dict must not be empty"

    allowed_supports = {"limit", "keyword", "location"}
    assert set(meta.supports).issubset(allowed_supports), f"Invalid supports in {meta.id}: {meta.supports}"

    assert isinstance(meta.fields, list) and len(meta.fields) > 0, "Fields list must not be empty"
    assert meta.default_limit > 0
    assert meta.max_limit >= meta.default_limit


@pytest.mark.unit
@pytest.mark.parametrize("scraper_cls", REGISTERED_SCRAPERS)
def test_scraper_to_standard_with_fixtures(scraper_cls):
    """Verify to_standard() creates valid StandardRecord from offline fixture data."""
    meta = scraper_cls.meta
    fixtures_file = (
        Path(__file__).resolve().parent.parent / "fixtures" / meta.id / "records.json"
    )
    assert fixtures_file.exists(), f"Missing fixture file for scraper '{meta.id}' at {fixtures_file}"

    with open(fixtures_file, "r", encoding="utf-8") as f:
        records_raw = json.load(f)

    assert len(records_raw) >= 1, f"Fixture for '{meta.id}' must contain at least one record"

    scraper = scraper_cls()
    for item in records_raw:
        record = scraper.to_standard(item)
        assert isinstance(record, StandardRecord), f"{meta.id}.to_standard did not return StandardRecord"
        assert record.source_code == meta.id
        assert record.record_kind == meta.record_kind

        if meta.record_kind == "opportunity":
            assert record.external_id is not None, f"Opportunity record from {meta.id} missing external_id"
            assert record.title, f"Opportunity record from {meta.id} missing title"
        else:
            assert record.organization_name, f"Company record from {meta.id} missing organization_name"


@pytest.mark.unit
@pytest.mark.parametrize("scraper_cls", REGISTERED_SCRAPERS)
def test_describe_for_llm_includes_scraper(scraper_cls):
    """Verify describe_for_llm catalog includes every registered scraper."""
    meta = scraper_cls.meta
    catalog = describe_for_llm()
    matching = [entry for entry in catalog if entry["id"] == meta.id]
    assert len(matching) == 1, f"Scraper '{meta.id}' missing or duplicated in describe_for_llm"
    entry = matching[0]
    assert entry["record_kind"] == meta.record_kind
    assert "ready" in entry


@pytest.mark.unit
@pytest.mark.parametrize("scraper_cls", REGISTERED_SCRAPERS)
def test_validate_params_bounds(scraper_cls):
    """Verify validate_params correctly enforces limits and feature support."""
    meta = scraper_cls.meta

    # Valid default params
    valid_res = validate_params(meta.id, {"limit": meta.default_limit})
    assert isinstance(valid_res, ScrapeParams)
    assert valid_res.limit == meta.default_limit

    # Exceeding max limit raises InvalidScrapeParams
    with pytest.raises(InvalidScrapeParams):
        validate_params(meta.id, {"limit": meta.max_limit + 100})

    # Zero or negative limit raises InvalidScrapeParams
    with pytest.raises(InvalidScrapeParams):
        validate_params(meta.id, {"limit": 0})


@pytest.mark.unit
@pytest.mark.parametrize("scraper_cls", REGISTERED_SCRAPERS)
def test_close_safe_to_call_twice(scraper_cls):
    """Verify close() is idempotent and safe to call multiple times."""
    scraper = scraper_cls()
    scraper.close()
    scraper.close()  # Must not raise
