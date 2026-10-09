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

    records = list(run(scraper_id, {"limit": 100, **({"us_state": "NY"} if scraper_id == "jwiz" else {})}))
    assert len(records) >= 2
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


@pytest.mark.unit
def test_validate_params_location_handling():
    """Verify validate_params across all scrapers with various location inputs and edge cases."""
    from scrappers.base import InvalidScrapeParams
    from scrappers.controller import validate_params

    # Bonfire: covers Dallas, TX
    p_bonfire = validate_params("bonfire", {"location": "Dallas, TX"})
    assert p_bonfire.limit == 20
    p_bonfire_state = validate_params("bonfire", {"us_state": "Texas"})
    assert p_bonfire_state.limit == 20

    with pytest.raises(InvalidScrapeParams, match="Dallas, not Austin"):
        validate_params("bonfire", {"city": "Austin"})
    with pytest.raises(InvalidScrapeParams, match="TX, not CA"):
        validate_params("bonfire", {"us_state": "CA"})
    with pytest.raises(InvalidScrapeParams, match="Dallas, not Houston"):
        validate_params("bonfire", {"location": "Houston, TX"})

    # DASNY: covers NY
    p_dasny = validate_params("dasny", {"us_state": "NY"})
    assert p_dasny.limit == 20
    p_dasny_loc = validate_params("dasny", {"location": "Albany, NY"})
    assert p_dasny_loc.city == "Albany"
    assert p_dasny_loc.us_state == "NY"

    with pytest.raises(InvalidScrapeParams, match="NY, not FL"):
        validate_params("dasny", {"us_state": "FL"})
    with pytest.raises(InvalidScrapeParams, match="NY, not FL"):
        validate_params("dasny", {"location": "Miami, FL"})

    # JWiz: requires location
    with pytest.raises(InvalidScrapeParams, match="requires a city or state"):
        validate_params("jwiz", {"limit": 25})

    p_jwiz = validate_params("jwiz", {"location": "Brooklyn, NY"})
    assert p_jwiz.city == "Brooklyn"
    assert p_jwiz.us_state == "NY"
    p_jwiz_state = validate_params("jwiz", {"us_state": "New York"})
    assert p_jwiz_state.us_state == "NY"

    # NYSCR: covers NY
    p_nyscr = validate_params("nyscr", {"location": "Yonkers, NY"})
    assert p_nyscr.city == "Yonkers"
    assert p_nyscr.us_state == "NY"

    with pytest.raises(InvalidScrapeParams, match="NY, not TX"):
        validate_params("nyscr", {"us_state": "TX"})


@pytest.mark.unit
def test_fixtures_populate_standard_record_fields():
    """Verify that every scraper extracts full fields, valid timezones, and JSON-safe metadata."""
    from scrappers.controller import get_scraper_class
    import json

    for scraper_id in ["bonfire", "dasny", "jwiz", "nyscr"]:
        fixtures_file = (
            Path(__file__).resolve().parent.parent / "fixtures" / scraper_id / "records.json"
        )
        with open(fixtures_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        scraper = get_scraper_class(scraper_id)()
        for raw in data:
            rec = scraper.to_standard(raw)
            # Check JSON-safety of extra
            json.dumps(rec.extra)

            assert rec.organization_name is not None and len(rec.organization_name) > 0
            assert rec.external_id is not None and len(str(rec.external_id)) > 0
            assert rec.source_code == scraper_id

            if scraper_id in ("bonfire", "dasny", "nyscr"):
                assert rec.record_kind == "opportunity"
                assert rec.due_at is not None
                assert rec.due_at.tzinfo is not None
                assert rec.us_state in ("TX", "NY")
            else:
                assert rec.record_kind == "company"
                assert rec.us_state is not None
                assert "lead_priority" in rec.extra


@pytest.mark.unit
def test_ingest_identity_for_all_scraper_fixtures():
    """Verify that every fixture record across all 4 scrapers produces a valid identity key for ingestion."""
    from scrappers.controller import get_scraper_class
    from Database.normalize import lead_identity, fingerprint, normalize_email, normalize_phone, normalize_domain

    for scraper_id in ["bonfire", "dasny", "jwiz", "nyscr"]:
        fixtures_file = (
            Path(__file__).resolve().parent.parent / "fixtures" / scraper_id / "records.json"
        )
        with open(fixtures_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        scraper = get_scraper_class(scraper_id)()
        for raw in data:
            rec = scraper.to_standard(raw)
            fp = fingerprint(
                name=rec.organization_name,
                domain=normalize_domain(rec.website),
                phone=normalize_phone(rec.phone),
                email=normalize_email(rec.email),
            )
            id_key = lead_identity(
                kind=rec.record_kind,
                source_code=rec.source_code,
                external_id=rec.external_id,
                fingerprint=fp,
            )
            assert id_key is not None, f"Failed to compute lead identity for {scraper_id} record: {rec}"
            if rec.record_kind == "opportunity":
                assert id_key.startswith(f"src:{scraper_id}:")
            else:
                assert id_key.startswith("fp:")
