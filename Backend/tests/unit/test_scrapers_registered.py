"""
test_scrapers_registered.py
───────────────────────────
Verify that every scraper module in Backend/scrappers/ is registered in controller.REGISTERED_SCRAPERS.
Fails with "add it to REGISTERED_SCRAPERS" if an unregistered scraper module exists.
"""

from pathlib import Path
import pytest

from scrappers.controller import REGISTERED_SCRAPERS


IGNORED_FILES = {
    "__init__.py",
    "base.py",
    "driver.py",
    "controller.py",
    "_template.py",
    "utils.py",
    "bonfire_parser.py",
}


@pytest.mark.unit
def test_all_scraper_modules_are_registered():
    """Verify that all scraper implementation files are present in REGISTERED_SCRAPERS."""
    scrappers_dir = Path(__file__).resolve().parent.parent.parent / "scrappers"
    scraper_files = [
        f for f in scrappers_dir.glob("*.py")
        if f.name not in IGNORED_FILES and not f.name.startswith(".")
    ]

    registered_modules = {cls.__module__.split(".")[-1] for cls in REGISTERED_SCRAPERS}

    for sf in scraper_files:
        stem = sf.stem
        assert stem in registered_modules, (
            f"Scraper module '{sf.name}' is not registered! "
            f"Add it to REGISTERED_SCRAPERS in Backend/scrappers/controller.py"
        )
