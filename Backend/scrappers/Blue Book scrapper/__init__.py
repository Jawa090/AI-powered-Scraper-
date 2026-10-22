"""
Backend/scrappers/Blue Book scrapper/__init__.py
─────────────────────────────────────────────────
Package root for The Blue Book Building & Construction Network scraper.
Exposes BlueBookScraper conforming to BaseScraper.
"""

try:
    from .scraper import (
        BlueBookScraper,
        BlueBookScrapper,
        BluebookScraper,
        SCRAPPER_CODE,
        SOURCE_CODE,
        RECORD_KIND,
    )
except (ImportError, ValueError):
    import importlib
    _scraper_mod = importlib.import_module("scrappers.Blue Book scrapper.scraper")
    BlueBookScraper = _scraper_mod.BlueBookScraper
    BlueBookScrapper = _scraper_mod.BlueBookScrapper
    BluebookScraper = _scraper_mod.BluebookScraper
    SCRAPPER_CODE = _scraper_mod.SCRAPPER_CODE
    SOURCE_CODE = _scraper_mod.SOURCE_CODE
    RECORD_KIND = _scraper_mod.RECORD_KIND

__all__ = [
    "BlueBookScraper",
    "BlueBookScrapper",
    "BluebookScraper",
    "SCRAPPER_CODE",
    "SOURCE_CODE",
    "RECORD_KIND",
]


# Register package aliases so that 'bluebook' and variants resolve to this package
import sys
_pkg = sys.modules[__name__]
for _alias in [
    "bluebook",
    "scrappers.bluebook",
    "Backend.scrappers.bluebook",
    "scrappers.BlueBook",
    "Backend.scrappers.BlueBook",
]:
    sys.modules.setdefault(_alias, _pkg)

