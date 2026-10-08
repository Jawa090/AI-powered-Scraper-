"""
test_scraper_fixtures.py
─────────────────────────
Tests offline fixture parsing and controller fixture dispatch for all 4 modular scrapers:
bonfire, dasny, jwiz, nyscr.
"""

import json
from pathlib import Path
import pytest

from scrappers.base import StandardRecord
from scrappers.controller import (
    check_ready,
    describe_for_llm,
    get_meta,
    list_scrapers,
    run,
    scraper_ids,
    to_api_dict,
)
from settings import settings


@pytest.mark.unit
@pytest.mark.parametrize("scraper_id", ["bonfire", "dasny", "jwiz", "nyscr"])
def test_offline_fixture_parsing_all_scrapers(scraper_id):
    """Verify offline fixture files parse cleanly into StandardRecords for each scraper."""
    fixtures_file = (
        Path(__file__).resolve().parent.parent / "fixtures" / scraper_id / "records.json"
    )
    assert fixtures_file.exists(), f"Fixture file not found: {fixtures_file}"

    with open(fixtures_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) >= 2, f"Fixture for '{scraper_id}' must contain at least 2 sample records"

    from scrappers.controller import get_scraper_class
    cls = get_scraper_class(scraper_id)
    scraper = cls()

    for raw in data:
        record = scraper.to_standard(raw)
        assert isinstance(record, StandardRecord)
        assert record.source_code == scraper_id
        if record.record_kind == "opportunity":
            assert record.external_id is not None
            assert record.title
        else:
            assert record.organization_name


@pytest.mark.unit
@pytest.mark.parametrize("scraper_id", ["bonfire", "dasny", "jwiz", "nyscr"])
def test_controller_fixture_mode_execution(scraper_id, monkeypatch):
    """Verify controller.run in SCRAPER_MODE='fixture' yields correct StandardRecords."""
    monkeypatch.setattr(settings, "SCRAPER_MODE", "fixture")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")

    records = list(run(scraper_id, {"limit": 1, **({"us_state": "NY"} if scraper_id == "jwiz" else {})}))
    assert len(records) == 1
    rec = records[0]
    assert isinstance(rec, StandardRecord)
    assert rec.source_code == scraper_id


@pytest.mark.unit
def test_controller_describe_and_to_api_dict():
    """Verify describe_for_llm and to_api_dict output structure and completeness."""
    ids = scraper_ids()
    assert set(ids) == {"bonfire", "dasny", "jwiz", "nyscr"}

    all_meta = list_scrapers()
    assert len(all_meta) == 4

    for meta in all_meta:
        api_dict = to_api_dict(meta)
        assert api_dict["id"] == meta.id
        assert api_dict["name"] == meta.name
        assert api_dict["recordKind"] == meta.record_kind
        assert "ready" in api_dict
        assert api_dict["defaultLimit"] == meta.default_limit
        assert api_dict["maxLimit"] == meta.max_limit


@pytest.mark.unit
def test_sync_sources_creates_rows():
    """Verify sync_sources in services/sources.py creates/updates Source models."""
    from unittest.mock import MagicMock
    from services.sources import sync_sources

    session = MagicMock()
    # Mock query to simulate empty table first
    session.query.return_value.filter.return_value.first.return_value = None

    synced = sync_sources(session)
    assert len(synced) == 4
    synced_codes = {s.code for s in synced}
    assert synced_codes == {"bonfire", "dasny", "jwiz", "nyscr"}
    assert session.add.call_count == 4
    session.flush.assert_called_once()
