"""
Backend/scrappers/Blue Book scrapper/__init__.py
Package root for The Blue Book Building and Construction Network scraper.
Exposes BlueBookScraper conforming to BaseScraper.
"""

try:
    from . import crawler, geo, keywords, names, parsers, phones, urls
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
    crawler = _scraper_mod.crawler
    BlueBookScraper = _scraper_mod.BlueBookScraper
    BlueBookScrapper = _scraper_mod.BlueBookScrapper
    BluebookScraper = _scraper_mod.BluebookScraper
    SCRAPPER_CODE = _scraper_mod.SCRAPPER_CODE
    SOURCE_CODE = _scraper_mod.SOURCE_CODE
    RECORD_KIND = _scraper_mod.RECORD_KIND
    parsers = getattr(_scraper_mod, "parsers", None)
    geo = getattr(_scraper_mod, "geo", None)
    keywords = getattr(_scraper_mod, "keywords", None)
    names = getattr(_scraper_mod, "names", None)
    urls = getattr(_scraper_mod, "urls", None)
    phones = getattr(_scraper_mod, "phones", None)

__all__ = [
    "crawler",
    "BlueBookScraper",
    "BlueBookScrapper",
    "BluebookScraper",
    "SCRAPPER_CODE",
    "SOURCE_CODE",
    "RECORD_KIND",
    "parsers",
    "geo",
    "keywords",
    "names",
    "urls",
    "phones",
]

import sys
_pkg = sys.modules[__name__]
for _alias in [
    "bluebook",
    "scrappers.bluebook",
    "Backend.scrappers.bluebook",
    "scrappers.BlueBook",
    "Backend.scrappers.BlueBook",
]:
    sys.modules[_alias] = _pkg
    sys.modules[f"{_alias}.crawler"] = crawler
    sys.modules[f"{_alias}.scraper"] = sys.modules.get("scrappers.Blue Book scrapper.scraper")
    if parsers:
        sys.modules[f"{_alias}.parsers"] = parsers
    if geo:
        sys.modules[f"{_alias}.geo"] = geo
    if keywords:
        sys.modules[f"{_alias}.keywords"] = keywords
    if names:
        sys.modules[f"{_alias}.names"] = names
    if urls:
        sys.modules[f"{_alias}.urls"] = urls
    if phones:
        sys.modules[f"{_alias}.phones"] = phones

