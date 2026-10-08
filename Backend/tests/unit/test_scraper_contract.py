"""
tests/unit/test_scraper_contract.py — Scraper contract tests (P17.1)
Verifies every registered scraper has valid metadata.
"""
import sys
from pathlib import Path

_backend = str(Path(__file__).resolve().parent.parent.parent)
if _backend not in sys.path:
    sys.path.insert(0, _backend)

import _paths
from scrappers.controller import REGISTERED_SCRAPERS, list_scrapers, scraper_ids


class TestScraperContract:
    """Every registered scraper must satisfy the contract."""

    def test_all_scrapers_have_meta(self):
        """Every registered scraper class must have a 'meta' attribute."""
        for cls in REGISTERED_SCRAPERS:
            assert hasattr(cls, "meta"), f"{cls.__name__} missing 'meta' attribute"

    def test_all_scrapers_have_unique_ids(self):
        """Scraper IDs must be unique and lowercase."""
        ids = scraper_ids()
        assert len(ids) == len(set(ids)), f"Duplicate scraper IDs: {ids}"
        for sid in ids:
            assert sid == sid.lower(), f"Scraper ID '{sid}' is not lowercase"

    def test_all_scrapers_have_required_meta_fields(self):
        """Each scraper meta must have id, name, description, record_kind."""
        for meta in list_scrapers():
            assert meta.id, f"Scraper meta missing 'id'"
            assert meta.name, f"Scraper {meta.id} missing 'name'"
            assert meta.description, f"Scraper {meta.id} missing 'description'"
            assert meta.record_kind in ("opportunity", "company"), (
                f"Scraper {meta.id} has invalid record_kind: {meta.record_kind}"
            )

    def test_scraper_count(self):
        """There should be exactly 4 registered scrapers."""
        assert len(scraper_ids()) == 4

    def test_known_scraper_ids(self):
        """Known scraper IDs should be present."""
        ids = set(scraper_ids())
        expected = {"bonfire", "dasny", "jwiz", "nyscr"}
        assert expected == ids, f"Expected {expected}, got {ids}"
