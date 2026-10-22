"""
Backend/scrappers/Blue Book scrapper/tests/conftest.py
─────────────────────────────────────────────────────
Pytest configuration for Blue Book scraper tests.
Aliases the package as 'bluebook' in sys.modules so all existing offline tests
and parser tests load smoothly without modification.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Locate root paths
_tests_dir = Path(__file__).resolve().parent
_scrapper_dir = _tests_dir.parent
_scrappers_dir = _scrapper_dir.parent
_backend_dir = _scrappers_dir.parent

for _p in [str(_backend_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Import the actual package and register it under canonical 'bluebook' name
try:
    pkg = importlib.import_module("scrappers.Blue Book scrapper")
    sys.modules["bluebook"] = pkg
    for sub in ["geo", "keywords", "names", "parsers", "phones", "urls", "scraper"]:
        try:
            submod = importlib.import_module(f"scrappers.Blue Book scrapper.{sub}")
            sys.modules[f"bluebook.{sub}"] = submod
        except Exception:
            pass
except Exception as e:
    pass
