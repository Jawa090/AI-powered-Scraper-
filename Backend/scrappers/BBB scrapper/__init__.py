"""
Backend/scrappers/BBB scrapper/__init__.py
──────────────────────────────────────────
Exports BBBScraper and canonical aliases for controller discovery.
"""

from __future__ import annotations

from .bbb import BBBScraper, BBBScrapper, meta

__all__ = [
    "BBBScraper",
    "BBBScrapper",
    "meta",
]
