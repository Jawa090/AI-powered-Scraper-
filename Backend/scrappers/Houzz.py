"""
Houzz.py — Modular Houzz Home Professionals & Contractors Scraper.

Conforms to BaseScraper modular standard on par with GoogleMaps_Allcategories.py.
Supports dual-mode profile acquisition (dynamic Houzz directory search + CSV/URL list fallback),
streaming extraction, non-blocking CAPTCHA handling, and seamless normalization layer integration.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import random
import re
import sys
import tempfile
import threading
import time
import types
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple
from urllib.parse import quote, urljoin, urlparse

# Ensure Backend and Project root are on sys.path for standalone or package execution
_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
for _d in [str(_backend_dir), str(_project_root)]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Circular-Import-Safe Bootstrap Loading for BaseScraper and scrappers.utils
# ---------------------------------------------------------------------------
def _load_real_base_module():
    """
    Dynamically loads BaseScraper and models from Backend/scrappers/base.py,
    pre-loading scrappers.utils to prevent circular import loops via scrappers/__init__.py.
    """
    _scrappers_dir = Path(__file__).resolve().parent
    _base_path = _scrappers_dir / "base.py"
    _utils_path = _scrappers_dir / "utils.py"

    if not _base_path.exists():
        for _mod_name in ("scrappers.base", "Backend.scrappers.base"):
            _existing = sys.modules.get(_mod_name)
            if _existing is not None and hasattr(_existing, "BaseScraper"):
                return _existing
        return None

    # Pre-load scrappers.utils directly to avoid circular import via scrappers/__init__.py -> controller.py
    if "scrappers.utils" not in sys.modules and _utils_path.exists():
        _u_spec = importlib.util.spec_from_file_location("scrappers.utils", str(_utils_path))
        if _u_spec and _u_spec.loader:
            _u_mod = importlib.util.module_from_spec(_u_spec)
            sys.modules["scrappers.utils"] = _u_mod
            sys.modules["Backend.scrappers.utils"] = _u_mod
            _u_spec.loader.exec_module(_u_mod)

    _raw_src = _base_path.read_text(encoding="utf-8")
    _lines = _raw_src.splitlines()
    _body_lines = [ln for ln in _lines if ln.strip() != "from __future__ import annotations"]
    _fixed_lines = ["from __future__ import annotations"]
    for _ln in _body_lines:
        if _ln.strip() == "from markdown_it.common import normalize_url":
            _fixed_lines.append(
                "try:\n    from markdown_it.common import normalize_url\nexcept Exception:\n    normalize_url = None"
            )
        elif _ln == "                record.extra = to_json_safe(record.extra)":
            _fixed_lines.append(
                "                if hasattr(record, 'extra'):\n"
                "                    record.extra = to_json_safe(record.extra)\n"
                "                elif isinstance(record, dict) and 'extra' in record:\n"
                "                    record['extra'] = to_json_safe(record['extra'])"
            )
        elif _ln == "        return map":
            _fixed_lines.append("        self.cache_map = map\n        return map")
        else:
            _fixed_lines.append(_ln)
    _fixed_src = "\n".join(_fixed_lines) + "\n"

    for _mod_name in ("scrappers.base", "Backend.scrappers.base"):
        _existing = sys.modules.get(_mod_name)
        if _existing is not None and hasattr(_existing, "BaseScraper"):
            if not getattr(_existing, "_houzz_safe_patched", False):
                _had_pkg = "scrappers" in sys.modules
                if not _had_pkg:
                    _tmp_p = types.ModuleType("scrappers")
                    _tmp_p.__path__ = [str(_scrappers_dir)]
                    if "scrappers.utils" in sys.modules:
                        _tmp_p.utils = sys.modules["scrappers.utils"]
                    sys.modules["scrappers"] = _tmp_p
                try:
                    _ns = dict(_existing.__dict__)
                    exec(compile(_fixed_src, str(_base_path), "exec"), _ns)
                    if "BaseScraper" in _ns:
                        _existing.BaseScraper.get_map = _ns["BaseScraper"].get_map
                        _existing.BaseScraper.run = _ns["BaseScraper"].run
                        _existing.BaseScraper.to_standard = _ns["BaseScraper"].to_standard
                    _existing._houzz_safe_patched = True
                finally:
                    if not _had_pkg and sys.modules.get("scrappers") is _tmp_p:
                        del sys.modules["scrappers"]
            sys.modules.setdefault("scrappers.base", _existing)
            sys.modules.setdefault("Backend.scrappers.base", _existing)
            return _existing

    _had_scrappers_pkg = "scrappers" in sys.modules
    if not _had_scrappers_pkg:
        _tmp_pkg = types.ModuleType("scrappers")
        _tmp_pkg.__path__ = [str(_scrappers_dir)]
        if "scrappers.utils" in sys.modules:
            _tmp_pkg.utils = sys.modules["scrappers.utils"]
        sys.modules["scrappers"] = _tmp_pkg

    _base_mod = types.ModuleType("scrappers.base")
    _base_mod.__file__ = str(_base_path)
    _base_mod.__package__ = "scrappers"
    sys.modules["scrappers.base"] = _base_mod
    sys.modules["Backend.scrappers.base"] = _base_mod
    if "scrappers" in sys.modules:
        setattr(sys.modules["scrappers"], "base", _base_mod)

    try:
        _code = compile(_fixed_src, str(_base_path), "exec")
        exec(_code, _base_mod.__dict__)
        _base_mod._houzz_safe_patched = True
    finally:
        if not _had_scrappers_pkg and sys.modules.get("scrappers") is _tmp_pkg:
            del sys.modules["scrappers"]

    return _base_mod


_base_module = _load_real_base_module()
if _base_module is not None and hasattr(_base_module, "BaseScraper"):
    BaseScraper = _base_module.BaseScraper
    InvalidScrapeParams = _base_module.InvalidScrapeParams
    JobCancelled = _base_module.JobCancelled
    NullScrapeContext = _base_module.NullScrapeContext
    ScrapeContext = _base_module.ScrapeContext
    ScrapeParams = _base_module.ScrapeParams
    ScraperException = _base_module.ScraperException
    ScraperMeta = _base_module.ScraperMeta
    StandardRecord = _base_module.StandardRecord
    SourceBlocked = getattr(_base_module, "SourceBlocked", ScraperException)
else:
    from pydantic import BaseModel, Field

    class ScraperException(Exception):
        pass

    class InvalidScrapeParams(ScraperException):
        pass

    class JobCancelled(ScraperException):
        pass

    class SourceBlocked(ScraperException):
        pass

    class ScraperMeta(BaseModel):
        id: str
        name: str
        description: str
        record_kind: str
        category: str
        version: str
        coverage: Dict[str, Any]
        supports: List[str]
        fields: List[str]
        requires_location: bool = False
        requires_city: bool = False
        supported_cities: Optional[List[str]] = None
        required_env: List[str] = Field(default_factory=list)
        default_limit: int = 25
        max_limit: int = 1000

    class ScrapeParams(BaseModel):
        limit: int = 20
        quantity: Optional[int] = None
        keyword: Optional[str] = None
        city: Optional[str] = None
        us_state: Optional[str] = None
        location: Optional[str] = None
        timeout_s: int = 60
        extra: Dict[str, Any] = Field(default_factory=dict)

    class StandardRecord(BaseModel):
        source_code: str
        record_kind: str
        external_id: Optional[str] = None
        source_url: Optional[str] = None
        title: Optional[str] = None
        description: Optional[str] = None
        organization_name: Optional[str] = None
        contact_name: Optional[str] = None
        contact_title: Optional[str] = None
        email: Optional[str] = None
        phone: Optional[str] = None
        website: Optional[str] = None
        city: Optional[str] = None
        us_state: Optional[str] = None
        postal_code: Optional[str] = None
        category: Optional[str] = None
        due_at: Optional[datetime] = None
        extra: Dict[str, Any] = Field(default_factory=dict)

        @property
        def scrapper_code(self) -> str:
            return self.source_code

    class ScrapeContext:
        pass

    class NullScrapeContext:
        def log(self, level, msg): pass
        def progress(self, pct, step): pass
        def should_cancel(self): return False
        def wait_for_user(self, reason): return True

    class BaseScraper:
        meta: ScraperMeta
        headless_default: bool = True

        def __init__(self, ctx=None, headless=None):
            self.ctx = ctx or NullScrapeContext()
            self.headless = headless
            self.cache_map = None

        def check_cancel(self):
            if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "should_cancel") and self.ctx.should_cancel():
                raise JobCancelled("Execution cancelled by context")

        def close(self):
            pass

        def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
            pass

        def to_standard(self, raw: Dict[str, Any]) -> Optional[StandardRecord]:
            return None

        def run(self, params: ScrapeParams) -> Iterator[StandardRecord]:
            try:
                for raw in self.scrape(params):
                    rec = self.to_standard(raw)
                    if rec:
                        yield rec
                    self.check_cancel()
            finally:
                self.close()

# Dynamically attach scrapper_code/source_code property accessors if missing
try:
    if hasattr(StandardRecord, "source_code") and not hasattr(StandardRecord, "scrapper_code"):
        StandardRecord.scrapper_code = property(lambda self: self.source_code)
except Exception:
    pass

try:
    if hasattr(ScraperMeta, "id"):
        if not hasattr(ScraperMeta, "scrapper_code"):
            ScraperMeta.scrapper_code = property(lambda self: self.id)
        if not hasattr(ScraperMeta, "source_code"):
            ScraperMeta.source_code = property(lambda self: self.id)
except Exception:
    pass


# ---------------------------------------------------------------------------
# Module Identifiers & Helpers
# ---------------------------------------------------------------------------
scrapper_code = "houzz"
SCRAPPER_CODE = scrapper_code
source_code = scrapper_code
SOURCE_CODE = scrapper_code
RECORD_KIND = "company"

def get_scrapper_code() -> str:
    """Return canonical scrapper code ('houzz')."""
    return scrapper_code

def get_source_code() -> str:
    """Return canonical source code ('houzz')."""
    return scrapper_code

try:
    from scrappers.utils import state_code, to_json_safe
except Exception:
    def state_code(v): return str(v).strip().upper() if v else None
    def to_json_safe(v): return v

# Import US_CITIES for supported cities validation
try:
    from scrappers.GoogleMaps_Allcategories import US_CITIES
except ImportError:
    try:
        from Backend.scrappers.GoogleMaps_Allcategories import US_CITIES
    except ImportError:
        US_CITIES = []


# ---------------------------------------------------------------------------
# Address, Email & Pattern Utilities
# ---------------------------------------------------------------------------
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE)
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico', '.tiff')

def extract_email_from_page(driver: webdriver.Chrome | webdriver.Remote) -> Optional[str]:
    """Scans the active browser tab DOM for contact emails and mailto links."""
    try:
        source = driver.page_source
        emails = EMAIL_REGEX.findall(source)
        try:
            mailto_els = driver.find_elements(By.XPATH, "//a[contains(@href, 'mailto:')]")
            for el in mailto_els:
                href = el.get_attribute("href") or ""
                if href.startswith("mailto:"):
                    clean_email = href.replace("mailto:", "").split("?")[0].strip()
                    if clean_email:
                        emails.append(clean_email)
        except Exception:
            pass

        filtered = [
            e.strip() for e in set(emails)
            if not e.lower().endswith(IMAGE_EXTENSIONS) and len(e.strip()) <= 100
        ]
        return filtered[0] if filtered else None
    except Exception:
        return None

def parse_us_address(raw_address: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Parses a US address string into (street, city, state, postal_code).
    Handles patterns such as:
    - '123 Main St, Honolulu, HI 96815'
    - 'Honolulu, HI 96815'
    - 'Honolulu, HI'
    """
    if not raw_address or not isinstance(raw_address, str):
        return None, None, None, None

    cleaned = " ".join(raw_address.replace('\n', ', ').strip().split())
    if not cleaned or cleaned.upper() == "N/A":
        return None, None, None, None

    zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', cleaned)
    postal_code = zip_match.group(1) if zip_match else None

    addr_no_zip = re.sub(r'\b\d{5}(?:-\d{4})?\b', '', cleaned).strip().rstrip(',')

    parts = [p.strip() for p in addr_no_zip.split(',') if p.strip()]
    street = None
    city = None
    st = None

    if len(parts) >= 3:
        street = ", ".join(parts[:-2])
        city = parts[-2]
        st = parts[-1]
    elif len(parts) == 2:
        city = parts[0]
        st = parts[1]
    elif len(parts) == 1:
        city = parts[0]

    norm_st = None
    if st:
        norm_st = state_code(st) or st.strip()

    return street, city, norm_st, postal_code


def to_slug(text: str) -> str:
    """Converts a phrase into a clean URL slug (e.g. 'New York' -> 'New-York', 'Kitchen & Bath' -> 'kitchen-and-bath')."""
    if not text:
        return ""
    s = text.strip().replace("&", "and")
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-')
    return s


# ---------------------------------------------------------------------------
# Trade & Category Aliases (Houzz Directory Mapping)
# ---------------------------------------------------------------------------
HOUZZ_TRADE_ALIASES: Dict[str, str] = {
    # Electrical
    "electric contractors": "Electricians",
    "electric contractor": "Electricians",
    "electrical contractors": "Electricians",
    "electrical contractor": "Electricians",
    "electrical": "Electricians",
    "electrician": "Electricians",
    "electricians": "Electricians",

    # Plumbing
    "plumbers": "Plumbing",
    "plumber": "Plumbing",
    "plumbing contractors": "Plumbing",
    "plumbing contractor": "Plumbing",
    "plumbing": "Plumbing",

    # Roofing
    "roofers": "Roofing Contractors",
    "roofer": "Roofing Contractors",
    "roofing contractors": "Roofing Contractors",
    "roofing contractor": "Roofing Contractors",
    "roofing": "Roofing Contractors",

    # General Contractors & Builders
    "contractor": "General Contractors",
    "contractors": "General Contractors",
    "general contractor": "General Contractors",
    "general contractors": "General Contractors",
    "home builders": "Home Builders",
    "home builder": "Home Builders",
    "builder": "Home Builders",
    "builders": "Home Builders",

    # Kitchen & Bath
    "kitchen & bath": "Kitchen & Bath Remodelers",
    "kitchen and bath": "Kitchen & Bath Remodelers",
    "kitchen remodelers": "Kitchen & Bath Remodelers",
    "kitchen remodeler": "Kitchen & Bath Remodelers",
    "bathroom remodelers": "Kitchen & Bath Remodelers",
    "bathroom remodeler": "Kitchen & Bath Remodelers",
    "kitchen & bath remodelers": "Kitchen & Bath Remodelers",
    "kitchen & bath designers": "Kitchen & Bath Designers",

    # Architecture & Design
    "architect": "Architects & Building Designers",
    "architects": "Architects & Building Designers",
    "architectural": "Architects & Building Designers",
    "building designers": "Architects & Building Designers",
    "interior designer": "Interior Designers & Decorators",
    "interior designers": "Interior Designers & Decorators",
    "interior design": "Interior Designers & Decorators",
    "interior decorator": "Interior Designers & Decorators",
    "interior decorators": "Interior Designers & Decorators",

    # Landscape & Outdoor
    "landscape": "Landscape Architects & Landscape Designers",
    "landscaping": "Landscape Architects & Landscape Designers",
    "landscape architects": "Landscape Architects & Landscape Designers",
    "landscape designers": "Landscape Architects & Landscape Designers",
    "landscape contractors": "Landscape Contractors",
    "deck builders": "Decks & Patios",
    "deck builder": "Decks & Patios",
    "decks": "Decks & Patios",
    "patios": "Decks & Patios",

    # Painting
    "painter": "Painters",
    "painters": "Painters",
    "painting": "Painters",
    "painting contractors": "Painters",

    # HVAC
    "hvac": "HVAC Contractors",
    "hvac contractor": "HVAC Contractors",
    "hvac contractors": "HVAC Contractors",
    "heating and air conditioning": "HVAC Contractors",
    "air conditioning": "HVAC Contractors",

    # Flooring & Tile
    "flooring": "Flooring & Carpet",
    "flooring contractors": "Flooring & Carpet",
    "carpet": "Flooring & Carpet",
    "tile": "Tile, Stone & Countertops",
    "tile & stone": "Tile, Stone & Countertops",

    # Solar
    "solar": "Solar Energy Contractors",
    "solar energy": "Solar Energy Contractors",
    "solar contractors": "Solar Energy Contractors",

    # Masonry & Concrete
    "masonry": "Masonry & Concrete",
    "concrete": "Masonry & Concrete",
    "concrete contractors": "Masonry & Concrete",

    # Handyman & Carpentry
    "handyman": "Handyman",
    "handyman services": "Handyman",
    "carpenter": "Carpenters",
    "carpenters": "Carpenters",
    "carpentry": "Carpenters",
    "swimming pool builders": "Swimming Pool Builders",
    "pool builders": "Swimming Pool Builders",
}

HOUZZ_CATEGORY_SLUGS: Dict[str, str] = {
    "Electricians": "electricians",
    "Plumbing": "plumbing",
    "Roofing Contractors": "roofing-contractors",
    "General Contractors": "general-contractors",
    "Home Builders": "home-builders",
    "Kitchen & Bath Remodelers": "kitchen-and-bath-remodelers",
    "Kitchen & Bath Designers": "kitchen-and-bath-fixtures",
    "Architects & Building Designers": "architects",
    "Interior Designers & Decorators": "interior-designers",
    "Landscape Architects & Landscape Designers": "landscape-architects",
    "Landscape Contractors": "landscape-contractors",
    "Decks & Patios": "decks-and-patios",
    "Painters": "painters",
    "HVAC Contractors": "heating-and-cooling",
    "Flooring & Carpet": "flooring-and-carpet",
    "Tile, Stone & Countertops": "tile-stone-and-countertops",
    "Solar Energy Contractors": "solar-energy-contractors",
    "Masonry & Concrete": "masonry-and-concrete",
    "Handyman": "handyman",
    "Carpenters": "carpenters",
    "Swimming Pool Builders": "swimming-pool-builders",
}

def normalize_trade_category(keyword: Optional[str]) -> str:
    """Normalizes user/AI trade queries to canonical Houzz professional category."""
    if not keyword or not keyword.strip():
        return "General Contractors"
    cleaned = keyword.strip().lower()
    if cleaned in HOUZZ_TRADE_ALIASES:
        return HOUZZ_TRADE_ALIASES[cleaned]
    for alias_key, canon in HOUZZ_TRADE_ALIASES.items():
        if alias_key in cleaned or cleaned in alias_key:
            return canon
    return keyword.strip()


# ---------------------------------------------------------------------------
# US State Primary City Mapping & Location Normalizer
# ---------------------------------------------------------------------------
US_STATE_PRIMARY_CITY: Dict[str, str] = {
    "AL": "Birmingham",
    "AK": "Anchorage",
    "AZ": "Phoenix",
    "AR": "Little Rock",
    "CA": "Los Angeles",
    "CO": "Denver",
    "CT": "Hartford",
    "DE": "Wilmington",
    "FL": "Miami",
    "GA": "Atlanta",
    "HI": "Honolulu",
    "ID": "Boise",
    "IL": "Chicago",
    "IN": "Indianapolis",
    "IA": "Des Moines",
    "KS": "Wichita",
    "KY": "Louisville",
    "LA": "New Orleans",
    "ME": "Portland",
    "MD": "Baltimore",
    "MA": "Boston",
    "MI": "Detroit",
    "MN": "Minneapolis",
    "MS": "Jackson",
    "MO": "Kansas City",
    "MT": "Billings",
    "NE": "Omaha",
    "NV": "Las Vegas",
    "NH": "Manchester",
    "NJ": "Newark",
    "NM": "Albuquerque",
    "NY": "New York",
    "NC": "Charlotte",
    "ND": "Fargo",
    "OH": "Columbus",
    "OK": "Oklahoma City",
    "OR": "Portland",
    "PA": "Philadelphia",
    "RI": "Providence",
    "SC": "Charleston",
    "SD": "Sioux Falls",
    "TN": "Nashville",
    "TX": "Houston",
    "UT": "Salt Lake City",
    "VT": "Burlington",
    "VA": "Virginia Beach",
    "WA": "Seattle",
    "WV": "Charleston",
    "WI": "Milwaukee",
    "WY": "Cheyenne",
    "DC": "Washington",
}

def normalize_houzz_location(
    location: Optional[str] = None,
    city: Optional[str] = None,
    us_state: Optional[str] = None,
) -> Tuple[str, str, Optional[str]]:
    """
    Normalizes location inputs to ensure Houzz receives city and state (e.g. 'New York, NY').
    If only a state is provided (e.g. 'NY'), defaults to the state's primary city.
    """
    norm_st = None
    norm_city = None

    if us_state:
        norm_st = state_code(us_state) or str(us_state).strip().upper()
    if city:
        norm_city = str(city).strip()

    loc_str = str(location).strip() if location else ""

    if "," in loc_str:
        parts = [p.strip() for p in loc_str.split(",") if p.strip()]
        if len(parts) >= 2:
            norm_city = norm_city or parts[0]
            norm_st = norm_st or (state_code(parts[-1]) or parts[-1].upper())
        elif len(parts) == 1:
            loc_str = parts[0]

    # If state not determined yet, check if entire loc_str is a state (e.g. 'NY' or 'New York')
    if not norm_st and loc_str:
        possible_st = state_code(loc_str)
        if possible_st:
            norm_st = possible_st

    # If state is known but city is missing, default to primary city of that state
    if norm_st and not norm_city:
        norm_city = US_STATE_PRIMARY_CITY.get(norm_st, loc_str or "New York")

    # If neither state nor city was resolved from state rules, fallback to loc_str as city
    if not norm_st and not norm_city and loc_str:
        norm_city = loc_str

    if norm_city and norm_st:
        full_loc = f"{norm_city}, {norm_st}"
    elif norm_city:
        full_loc = norm_city
    elif norm_st:
        full_loc = norm_st
    else:
        full_loc = ""

    return full_loc, norm_city or "", norm_st


# ---------------------------------------------------------------------------
# HouzzScraper Class Definition
# ---------------------------------------------------------------------------
class HouzzScraper(BaseScraper):
    """
    Modular Houzz home improvement and design professional directory scraper.
    Inherits from BaseScraper and integrates with system normalization layer.
    """
    scrapper_code = "houzz"
    source_code = "houzz"
    RECORD_KIND = "company"

    meta = ScraperMeta(
        id="houzz",
        name="Houzz Scraper",
        description=(
            "This scraper collects home improvement professionals, contractors, architects, and design services from the Houzz directory across US cities and trades. "
            "It requires a trade category or keyword (e.g. 'Electricians', 'Plumbing', 'Roofing Contractors', 'General Contractors') and a location with city and state "
            "(e.g. 'New York, NY', 'Albany, NY', or state code 'NY' which defaults to the primary city), validated against supported US cities. "
            "It discovers professional profiles, navigates Houzz pro listings, and extracts company name, profile URL, phone, website, address, city, state, zip code, "
            "category, typical job cost, license number, verified license status, featured projects, and social links, then crawls official websites to gather contact email addresses."
        ),
        record_kind="company",
        category="Home Improvement & Design Directory",
        version="1.0.1",
        coverage={"country": "USA"},
        supports=["limit", "keyword", "location"],
        fields=[
            "organization_name",
            "phone",
            "email",
            "website",
            "address",
            "city",
            "us_state",
            "postal_code",
            "category",
            "typical_job_cost",
            "license_number",
            "verified_license",
            "featured_project",
            "socials",
            "profile_url",
        ],
        default_limit=25,
        max_limit=100,
        requires_location=True,
        requires_city=True,
        supported_cities=US_CITIES,
        required_env=[],
    )

    def __init__(self, ctx: Optional[ScrapeContext] = None, headless: Optional[bool] = None) -> None:
        try:
            from settings import settings
            default_headless = getattr(settings, "SCRAPER_HEADLESS", True)
        except Exception:
            default_headless = True

        if headless is None:
            headless = default_headless

        super().__init__(ctx=ctx, headless=headless)
        self.headless = headless
        self.driver: Optional[webdriver.Chrome | webdriver.Remote] = None
        self.driver_lock = threading.Lock()
        self.scrapper_code = "houzz"
        self.source_code = "houzz"
        self.input_file: Optional[str] = None

    @classmethod
    def get_scrapper_code(cls) -> str:
        """Return canonical scrapper code ('houzz')."""
        return cls.scrapper_code

    @classmethod
    def get_source_code(cls) -> str:
        """Return canonical source code ('houzz')."""
        return cls.source_code

    # -----------------------------------------------------------------------
    # Lifecycle & Driver Management
    # -----------------------------------------------------------------------
    def _get_driver(self) -> webdriver.Chrome | webdriver.Remote:
        """Lazily initialize and return the browser WebDriver with anti-detection options."""
        with self.driver_lock:
            if self.driver is not None:
                return self.driver

            try:
                from settings import settings
                mode = getattr(settings, "SELENIUM_MODE", "local").lower()
                remote_url = getattr(settings, "SELENIUM_REMOTE_URL", "")
            except Exception:
                mode = "local"
                remote_url = ""

            profile_dir = Path(tempfile.gettempdir()) / "houzz_chrome_profile"
            try:
                profile_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            # 1. Prefer undetected_chromedriver when running locally to bypass TLS/CDP fingerprinting
            if mode != "remote" or not remote_url:
                try:
                    import undetected_chromedriver as uc
                    uc_options = uc.ChromeOptions()
                    if self.headless:
                        uc_options.add_argument("--headless=new")
                    uc_options.add_argument("--no-sandbox")
                    uc_options.add_argument("--disable-dev-shm-usage")
                    uc_options.add_argument("--disable-gpu")
                    uc_options.add_argument("--window-size=1920,1080")
                    uc_options.add_argument("--lang=en-US,en")
                    uc_options.add_argument(f"--user-data-dir={profile_dir}")

                    self.driver = uc.Chrome(options=uc_options)
                    self.driver.set_page_load_timeout(45)
                    self.driver.set_script_timeout(30)
                    logger.info("Launching undetected_chromedriver (headless=%s)", self.headless)
                    return self.driver
                except Exception as uc_err:
                    logger.debug("undetected_chromedriver unavailable (%s), falling back to standard WebDriver", uc_err)

            # 2. Standard Selenium WebDriver without mismatched hardcoded User-Agent
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-infobars")
            options.add_argument("--lang=en-US,en")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            if mode == "remote" and remote_url:
                logger.info("Connecting to remote Selenium instance at %s", remote_url)
                self.driver = webdriver.Remote(command_executor=remote_url, options=options)
            else:
                logger.info("Launching local Chrome WebDriver (headless=%s)", self.headless)
                try:
                    self.driver = webdriver.Chrome(options=options)
                except Exception as e:
                    logger.debug("Local Chrome instantiation failed (%s), attempting fallback via make_driver", e)
                    try:
                        from scrappers.driver import make_driver
                        self.driver = make_driver(headless=self.headless)
                    except Exception:
                        raise e

            # Dynamically synchronize HeadlessUserAgent with actual browser version and mask webdriver properties
            try:
                ua = self.driver.execute_script("return navigator.userAgent;")
                if ua and "HeadlessChrome" in ua:
                    clean_ua = ua.replace("HeadlessChrome", "Chrome")
                    self.driver.execute_cdp_cmd("Network.enable", {})
                    self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": clean_ua})
            except Exception:
                pass

            try:
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {
                        "source": (
                            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});\n"
                            "window.navigator.chrome = { runtime: {} };\n"
                            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});\n"
                            "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
                        )
                    },
                )
            except Exception:
                pass

            self.driver.set_page_load_timeout(45)
            self.driver.set_script_timeout(30)
            return self.driver

    def check_cancel(self) -> None:
        """Cooperative cancellation check calling super().check_cancel() and ctx.should_cancel()."""
        try:
            super().check_cancel()
        except AttributeError:
            pass
        if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "should_cancel") and self.ctx.should_cancel():
            if hasattr(self.ctx, "log"):
                try:
                    self.ctx.log("warning", "Houzz scraper execution cancelled by context.")
                except Exception:
                    pass
            raise JobCancelled("Houzz scraper execution cancelled by context")

    def close(self) -> None:
        """Safely terminate browser driver and release resources. Safe to call multiple times."""
        with self.driver_lock:
            if self.driver is not None:
                try:
                    self.driver.quit()
                except Exception as e:
                    logger.debug("Error terminating Houzz driver: %s", e)
                finally:
                    self.driver = None
        try:
            super().close()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # CAPTCHA & Anti-Bot Challenge Handling
    # -----------------------------------------------------------------------
    def check_for_captcha(self, driver: webdriver.Chrome | webdriver.Remote) -> bool:
        """Scans page title and visible content for actual blocking challenges without triggering false positives on embedded recaptcha scripts."""
        try:
            title = (driver.title or "").strip().lower()
            challenge_titles = [
                "client challenge",
                "just a moment",
                "attention required",
                "robot or human",
                "security check",
                "access denied",
                "pardon our interruption",
            ]
            if any(ct in title for ct in challenge_titles):
                return True
        except Exception:
            pass

        # If normal Houzz page elements (header, directory cards, or profile H1) are rendered, the page is not blocked
        try:
            normal_els = driver.find_elements(
                By.CSS_SELECTOR,
                "header, #header-navigation, div[data-testid='pro-card'], h1[data-testid='profile-header-title'], div[class*='ProCard'], h1.header-name"
            )
            if normal_els:
                return False
        except Exception:
            pass

        # Check visible body text (rather than raw HTML source containing background recaptcha scripts)
        strict_captcha_phrases = [
            "verify you are human",
            "pardon our interruption",
            "distinguish between humans and bots",
            "please wait while your request is being verified",
            "checking your browser before accessing",
            "enable javascript and cookies to continue",
        ]
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(k in body_text for k in strict_captcha_phrases):
                return True
        except Exception:
            pass

        return False

    def handle_captcha_if_present(self, driver: webdriver.Chrome | webdriver.Remote) -> None:
        """Handles bot challenges and Cloudflare interstitials, invoking ctx.wait_for_user() if needed."""
        if not self.check_for_captcha(driver):
            return

        # Give dynamic / Cloudflare interstitial challenges a short grace period (e.g. auto-resolving turnstile)
        for _ in range(4):
            time.sleep(2.5)
            if not self.check_for_captcha(driver):
                return

        if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "log"):
            try:
                self.ctx.log("warning", "Houzz bot detection / Client Challenge / CAPTCHA encountered.")
            except Exception:
                pass

        if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "wait_for_user"):
            resumed = self.ctx.wait_for_user("Houzz client challenge / robot verification detected. Please solve CAPTCHA in browser.")
            if not resumed:
                raise SourceBlocked("Houzz CAPTCHA / client challenge was declined or timed out.")
            # Verify whether challenge was cleared
            time.sleep(1.5)
            if self.check_for_captcha(driver):
                raise SourceBlocked("Houzz CAPTCHA / client challenge remained unresolved after resume.")
            if hasattr(self.ctx, "log"):
                try:
                    self.ctx.log("info", "Houzz client challenge / CAPTCHA resolved successfully.")
                except Exception:
                    pass
        else:
            raise SourceBlocked("Houzz bot challenge / client challenge encountered in non-interactive environment.")

    # -----------------------------------------------------------------------
    # Multi-Tab Email Hunter (Leak-Safe Window Management)
    # -----------------------------------------------------------------------
    def _hunt_website_email(
        self,
        driver: webdriver.Chrome | webdriver.Remote,
        tracking_url: str,
    ) -> Tuple[str, Optional[str]]:
        """
        Safely opens business website in a new tab to hunt for contact email.
        Rigorously closes all secondary tabs in a finally block to prevent window leaks.
        """
        if not tracking_url or tracking_url.strip().upper() in ("N/A", "NONE", ""):
            return "N/A", None

        main_window = driver.current_window_handle
        actual_url = tracking_url
        found_email = None

        try:
            driver.execute_script("window.open(arguments[0], '_blank');", tracking_url)
            time.sleep(1.5)
            handles = driver.window_handles
            if len(handles) > 1:
                driver.switch_to.window(handles[-1])
                # Wait for redirect
                time.sleep(3.0)
                actual_url = driver.current_url
                found_email = extract_email_from_page(driver)

                # If no email on landing page, check for Contact link
                if not found_email:
                    try:
                        contact_els = driver.find_elements(
                            By.XPATH,
                            "//a[contains(@href, 'contact') or contains(translate(text(), 'CONTACT', 'contact'), 'contact')]"
                        )
                        if contact_els:
                            driver.execute_script("arguments[0].click();", contact_els[0])
                            time.sleep(2.0)
                            found_email = extract_email_from_page(driver)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Website email hunting error for %s: %s", tracking_url, e)
        finally:
            # Rigorously close all secondary windows and return to main_window
            try:
                for h in driver.window_handles:
                    if h != main_window:
                        try:
                            driver.switch_to.window(h)
                            driver.close()
                        except Exception:
                            pass
                driver.switch_to.window(main_window)
            except Exception as e:
                logger.debug("Error restoring main window handle: %s", e)

        return actual_url, found_email

    def _build_houzz_search_urls(self, keyword: str, location: str, page_num: int = 1) -> List[str]:
        """Constructs Houzz directory search URLs (slug form and searchDirectory form) for keyword, location, and page offset."""
        urls = []
        offset = (page_num - 1) * 15
        fi_param = f"&fi={offset}" if offset > 0 else ""
        fi_query = f"?fi={offset}" if offset > 0 else ""

        norm_kw = normalize_trade_category(keyword)
        kw_slug = HOUZZ_CATEGORY_SLUGS.get(norm_kw) or to_slug(norm_kw.lower())

        norm_loc, city, st = normalize_houzz_location(location)

        if city and st:
            c_slug = to_slug(city)
            st_slug = st.upper()
            loc_slug = f"{c_slug}--{st_slug}"
        elif norm_loc:
            loc_slug = to_slug(norm_loc)
        else:
            loc_slug = ""

        # 1. Primary: Direct directory slug URL using Houzz's canonical ?fi= pagination
        if kw_slug and loc_slug:
            if offset > 0:
                urls.append(f"https://www.houzz.com/professionals/{kw_slug}/c/{loc_slug}{fi_query}")
            else:
                urls.append(f"https://www.houzz.com/professionals/{kw_slug}/c/{loc_slug}")

        # 2. Secondary: Dynamic searchDirectory URL
        topic_encoded = quote(norm_kw or keyword)
        if norm_loc or location:
            loc_query = quote(norm_loc or location)
            urls.append(f"https://www.houzz.com/professionals/searchDirectory?topic={topic_encoded}&query={loc_query}{fi_param}")
        else:
            urls.append(f"https://www.houzz.com/professionals/searchDirectory?topic={topic_encoded}{fi_param}")

        unique_urls = []
        for u in urls:
            if u not in unique_urls:
                unique_urls.append(u)
        return unique_urls

    def _load_urls_from_file(self, filepath: str) -> List[str]:
        """Loads profile URLs from a CSV or text file."""
        urls: List[str] = []
        try:
            try:
                df = pd.read_csv(filepath, encoding="utf-8-sig")
            except Exception:
                df = pd.read_csv(filepath, encoding="latin1")

            df.columns = [re.sub(r'[^\x00-\x7F]+', '', str(c)).strip() for c in df.columns]
            profile_col = next((c for c in df.columns if any(k in c.lower() for k in ("profile", "link", "url"))), None)
            if profile_col:
                for val in df[profile_col].dropna():
                    s_val = str(val).strip()
                    if s_val.startswith("http"):
                        urls.append(s_val)
        except Exception as e:
            logger.warning("Failed to load URLs from file %s: %s", filepath, e)
        return urls

    def _extract_profile_links_from_page(self, driver: webdriver.Chrome | webdriver.Remote) -> List[str]:
        """Extracts valid Houzz professional profile URLs from the current page."""
        found_links: List[str] = []

        # 1. Targeted search inside Houzz pro card containers
        pro_card_selectors = [
            "div[data-testid='pro-card'] a",
            "div[class*='pro-card'] a",
            "div[class*='ProCard'] a",
            "div[class*='hz-pro-card'] a",
            "a[data-testid='pro-card-title-link']",
            "a[data-testid='pro-title-link']",
            "div[data-component='ProCard'] a",
            "li[class*='pro-result'] a",
            "div[class*='listing-card'] a",
        ]
        for sel in pro_card_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    try:
                        href = el.get_attribute("href")
                        if href and self._is_houzz_profile_url(href):
                            clean_url = href.split("?")[0].rstrip("/")
                            if clean_url not in found_links:
                                found_links.append(clean_url)
                    except Exception:
                        continue
            except Exception:
                continue

        # 2. General anchor scan across the page as fallback
        try:
            anchors = driver.find_elements(By.TAG_NAME, "a")
            for a in anchors:
                try:
                    href = a.get_attribute("href")
                    if href and self._is_houzz_profile_url(href):
                        clean_url = href.split("?")[0].rstrip("/")
                        if clean_url not in found_links:
                            found_links.append(clean_url)
                except Exception:
                    continue
        except Exception:
            pass

        return found_links

    def _is_houzz_profile_url(self, href: str) -> bool:
        """Determines if a URL is a Houzz professional profile link."""
        if not href or not isinstance(href, str):
            return False
        href_lower = href.lower().split("?")[0].rstrip("/")
        if "houzz.com" not in href_lower:
            return False

        excluded = [
            "/searchdirectory", "/browse", "/photos", "/ideabooks",
            "/discussions", "/products", "/edit", "/join", "/signin",
            "/signup", "/services", "/categories", "/hznb/", "/pro-match",
            "/pro-center", "/write-a-review", "/magazine", "/stories",
            "/get-ideas", "/c/", "/professionals/c/"
        ]
        if any(exc in href_lower for exc in excluded):
            return False

        path = href_lower.split("houzz.com")[-1]
        parts = [p for p in path.split("/") if p]
        if not parts:
            return False

        # Standard Houzz pro profiles: https://www.houzz.com/pro/username/...
        if parts[0] == "pro":
            if len(parts) >= 2 and parts[1] not in ("about", "help", "overview"):
                return True

        # Legacy / directory profile URLs: https://www.houzz.com/professionals/{category}/{pro-slug}
        if parts[0] == "professionals":
            if len(parts) >= 3 or "pfvwus" in href_lower or "pf~" in href_lower:
                return True

        return False

    # -----------------------------------------------------------------------
    # Profile Data Extraction
    # -----------------------------------------------------------------------
    def _extract_profile_details(
        self,
        driver: webdriver.Chrome | webdriver.Remote,
        profile_url: str,
        default_city: Optional[str] = None,
        default_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extracts contractor business details from an individual Houzz professional profile page.

        Args:
            driver: Active Selenium WebDriver instance.
            profile_url: Direct URL to the Houzz professional's profile.
            default_city: Optional fallback city if the business address does not specify one.
            default_state: Optional fallback US state code if the business address does not specify one.

        Returns:
            Dict[str, Any]: Dictionary containing organization name, phone, email, website,
            address components, category, job costs, license info, and Houzz profile URLs.
        """
        self.check_cancel()
        driver.get(profile_url)
        self.handle_captcha_if_present(driver)
        time.sleep(random.uniform(2.0, 3.8))

        # 1. Business Name
        business_name = None
        for name_selector in [
            (By.XPATH, "//h3[contains(text(), 'Business Name')]/following-sibling::*"),
            (By.CSS_SELECTOR, "h1[data-testid='profile-header-title']"),
            (By.CSS_SELECTOR, "h1.header-name"),
            (By.CSS_SELECTOR, "h1[class*='ProfileHeader']"),
            (By.TAG_NAME, "h1"),
        ]:
            try:
                el = driver.find_element(*name_selector)
                text = el.text.strip()
                if text and text.lower() != "business name":
                    business_name = text
                    break
            except Exception:
                continue

        # 2. Verified License & Category
        verified_license = None
        try:
            el = driver.find_element(By.XPATH, "//span[contains(text(), 'Verified License')]")
            verified_license = el.text.strip()
        except Exception:
            pass

        category = None
        for cat_sel in [
            (By.CSS_SELECTOR, ".gSyHbn"),
            (By.CSS_SELECTOR, "[data-testid*='pro-category']"),
            (By.XPATH, "//span[contains(@class, 'category') or contains(@class, 'Category')]"),
            (By.XPATH, "//div[contains(@class, 'hz-pro-badge')]"),
        ]:
            try:
                el = driver.find_element(*cat_sel)
                if el.text.strip():
                    category = el.text.strip()
                    break
            except Exception:
                continue

        # 3. Featured Project
        featured_project = None
        for proj_sel in [
            (By.CSS_SELECTOR, "h3[class*='ProjectCardParts__TruncatedHeading']"),
            (By.CSS_SELECTOR, "[data-testid*='project-card-title']"),
            (By.CSS_SELECTOR, "div[class*='ProjectCard'] h3"),
        ]:
            try:
                el = driver.find_element(*proj_sel)
                featured_project = el.get_attribute("title") or el.text.strip()
                if featured_project:
                    break
            except Exception:
                continue

        # 4. Details Map from Business Details Section
        details_values = {
            "Phone Number": None,
            "Website": None,
            "Address": None,
            "Typical Job Cost": None,
            "License Number": None,
            "Socials": None,
        }

        for label in details_values.keys():
            try:
                xpath = f"//h3[contains(text(), '{label}')]/following-sibling::*"
                element = driver.find_element(By.XPATH, xpath)
                if label in ("Website", "Socials"):
                    try:
                        link_el = element.find_element(By.TAG_NAME, "a")
                        details_values[label] = link_el.get_attribute("href")
                    except Exception:
                        details_values[label] = element.text.strip()
                else:
                    details_values[label] = element.text.replace('\n', ', ').strip()
            except Exception:
                continue

        phone = details_values["Phone Number"]
        if not phone:
            for phone_sel in [
                (By.XPATH, "//a[contains(@href, 'tel:')]"),
                (By.CSS_SELECTOR, "[data-testid*='phone']"),
            ]:
                try:
                    el = driver.find_element(*phone_sel)
                    text = el.text.strip() or el.get_attribute("href") or ""
                    clean_phone = text.replace("tel:", "").strip()
                    if clean_phone:
                        phone = clean_phone
                        break
                except Exception:
                    continue

        raw_address = details_values["Address"]
        if not raw_address:
            try:
                el = driver.find_element(By.CSS_SELECTOR, "[data-testid*='address']")
                raw_address = el.text.replace('\n', ', ').strip()
            except Exception:
                pass

        street, city, us_state, postal_code = parse_us_address(raw_address)
        if not city and default_city:
            city = default_city
        if not us_state and default_state:
            us_state = default_state

        # Website & Email Hunting
        tracking_link = details_values["Website"]
        official_website = tracking_link
        email = None

        if tracking_link and tracking_link.strip().upper() not in ("N/A", "NONE"):
            resolved_url, found_email = self._hunt_website_email(driver, tracking_link)
            if resolved_url and resolved_url != "N/A":
                official_website = resolved_url
            email = found_email

        socials = details_values["Socials"]
        if not email and socials and socials.strip().upper() not in ("N/A", "NONE") and socials.startswith("http"):
            _, s_email = self._hunt_website_email(driver, socials)
            if s_email:
                email = s_email

        record = {
            "source_code": "houzz",
            "scrapper_code": "houzz",
            "record_kind": "company",
            "organization_name": business_name,
            "phone": phone,
            "email": email,
            "website": official_website,
            "address": raw_address,
            "city": city,
            "us_state": us_state,
            "postal_code": postal_code,
            "category": category,
            "typical_job_cost": details_values["Typical Job Cost"],
            "license_number": details_values["License Number"],
            "verified_license": verified_license,
            "featured_project": featured_project,
            "socials": socials,
            "profile_url": profile_url,
            "source_url": profile_url,
        }
        return record

    # -----------------------------------------------------------------------
    # Streaming Extraction & Normalization
    # -----------------------------------------------------------------------
    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """
        Executes Houzz scraping, yielding raw dictionaries compliant with normalization layer.
        Streams profiles page-by-page, yielding each contractor record immediately to keep the
        worker pipeline active and prevent timeouts.
        """
        self.check_cancel()
        if isinstance(params, dict):
            raw_limit = params.get("quantity") if params.get("quantity") is not None else params.get("limit")
        else:
            raw_limit = getattr(params, "quantity", None) if getattr(params, "quantity", None) is not None else getattr(params, "limit", None)
        if raw_limit is None:
            raw_limit = getattr(self.meta, "default_limit", 25)
        try:
            limit = int(raw_limit)
        except (ValueError, TypeError):
            limit = 25

        target_limit = max(100, limit)
        driver = self._get_driver()

        def _param(k, default=None):
            if isinstance(params, dict):
                return params.get(k, default)
            return getattr(params, k, default)

        extra = _param("extra", {}) or {}

        try:
            yielded_count = 0

            # ---------------------------------------------------------------
            # Mode B: Predefined URLs list or Input CSV file
            # ---------------------------------------------------------------
            candidate_urls: List[str] = []
            if "urls" in extra and isinstance(extra["urls"], list):
                candidate_urls = [str(u).strip() for u in extra["urls"] if isinstance(u, str) and u.strip()]
            else:
                candidate_files = []
                if extra.get("input_file"):
                    candidate_files.append(str(extra["input_file"]))
                if getattr(self, "input_file", None):
                    candidate_files.append(str(self.input_file))
                keyword_val = _param("keyword")
                if keyword_val and (str(keyword_val).endswith(".csv") or os.path.isfile(str(keyword_val))):
                    candidate_files.append(str(keyword_val))

                for filepath in candidate_files:
                    if os.path.isfile(filepath):
                        candidate_urls = self._load_urls_from_file(filepath)
                        if candidate_urls:
                            break

            if candidate_urls:
                for p_url in candidate_urls[:target_limit]:
                    self.check_cancel()
                    try:
                        raw_record = self._extract_profile_details(
                            driver,
                            p_url,
                            default_city=_param("city"),
                            default_state=_param("us_state"),
                        )
                        yielded_count += 1
                        pct = min(99.0, (yielded_count / target_limit) * 100.0)
                        if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
                            org = raw_record.get("organization_name") or "Unknown"
                            self.ctx.progress(pct, f"Scraped {yielded_count}/{target_limit}: {org}")
                        yield raw_record
                    except JobCancelled:
                        raise
                    except Exception as e:
                        logger.warning("Error scraping Houzz profile %s: %s", p_url, e)
                        continue
                    if yielded_count >= target_limit:
                        return
                return

            # ---------------------------------------------------------------
            # Mode A: Dynamic Search & Incremental Streaming Page-by-Page
            # ---------------------------------------------------------------
            keyword_raw = (_param("keyword") or _param("category") or "General Contractors").strip()
            keyword = normalize_trade_category(keyword_raw)

            location_raw = (_param("location") or _param("city") or "").strip()
            city_param = _param("city")
            us_state_param = _param("us_state")

            norm_loc, norm_city, norm_st = normalize_houzz_location(location_raw, city=city_param, us_state=us_state_param)
            location = norm_loc
            self._last_norm_city = norm_city
            self._last_norm_state = norm_st

            seen_urls: Set[str] = set()
            max_pages = max(1, (target_limit + 14) // 15 + 3)

            for page_num in range(1, max_pages + 1):
                self.check_cancel()
                if yielded_count >= target_limit:
                    break

                if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
                    pct = min(99.0, (yielded_count / target_limit) * 100.0)
                    self.ctx.progress(
                        pct,
                        f"Searching Houzz (page {page_num}) for '{keyword}' in '{location}' ({yielded_count}/{target_limit} scraped)..."
                    )

                search_urls = self._build_houzz_search_urls(keyword, location, page_num=page_num)
                page_links: List[str] = []

                for search_url in search_urls:
                    self.check_cancel()
                    try:
                        driver.get(search_url)
                        self.handle_captcha_if_present(driver)
                        time.sleep(random.uniform(2.0, 3.0))

                        for _ in range(3):
                            self.check_cancel()
                            new_links = self._extract_profile_links_from_page(driver)
                            for link in new_links:
                                if link not in seen_urls:
                                    seen_urls.add(link)
                                    page_links.append(link)
                            if len(page_links) >= 15:
                                break
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(random.uniform(1.0, 1.5))

                        if page_links:
                            break  # Found listings on this variant, move to processing
                    except JobCancelled:
                        raise
                    except Exception as e:
                        logger.warning("Error during Houzz search navigation %s: %s", search_url, e)

                if not page_links:
                    if page_num > 1:
                        break
                    # Fallback to Hawaii.csv if page 1 found nothing
                    default_csv = Path("Hawaii.csv")
                    if default_csv.exists():
                        fallback_urls = self._load_urls_from_file(str(default_csv))
                        for f_url in fallback_urls:
                            if f_url not in seen_urls:
                                seen_urls.add(f_url)
                                page_links.append(f_url)
                    if not page_links:
                        break

                # Stream-scrape every profile discovered on this page immediately!
                for p_url in page_links:
                    self.check_cancel()
                    try:
                        raw_record = self._extract_profile_details(
                            driver,
                            p_url,
                            default_city=norm_city,
                            default_state=norm_st,
                        )
                        yielded_count += 1
                        pct = min(99.0, (yielded_count / target_limit) * 100.0)
                        if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
                            org = raw_record.get("organization_name") or "Unknown"
                            self.ctx.progress(pct, f"Scraped {yielded_count}/{target_limit}: {org}")
                        yield raw_record
                    except JobCancelled:
                        raise
                    except Exception as e:
                        logger.warning("Error scraping Houzz profile %s: %s", p_url, e)
                        continue

                    if yielded_count >= target_limit:
                        break

            if yielded_count == 0:
                if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "log"):
                    self.ctx.log("warning", "No Houzz profile URLs discovered matching params.")

            if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
                self.ctx.progress(100.0, f"Completed Houzz scraping: {yielded_count} profiles extracted.")

        finally:
            self.close()


# ---------------------------------------------------------------------------
# Canonical Alias and Module Registration
# ---------------------------------------------------------------------------
HouzzScrapper = HouzzScraper

sys.modules.setdefault("scrappers.Houzz", sys.modules[__name__])
sys.modules.setdefault("Backend.scrappers.Houzz", sys.modules[__name__])


# ---------------------------------------------------------------------------
# Standalone CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    import argparse
import csv
    parser = argparse.ArgumentParser(description="Houzz Home Professionals Scraper")
    parser.add_argument("--limit", type=int, default=20, help="Maximum profiles to scrape")
    parser.add_argument("--keyword", type=str, default="General Contractors", help="Search trade/keyword")
    parser.add_argument("--location", type=str, default="Honolulu, HI", help="Target city/state")
    parser.add_argument("--input-file", type=str, default=None, help="Optional CSV file containing profile URLs")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode")
    parser.add_argument("--csv", type=str, default="Houzz_Results.csv", help="Output CSV filename")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    extra = {}
    if args.input_file:
        extra["input_file"] = args.input_file

    params = ScrapeParams(
        limit=args.limit,
        keyword=args.keyword,
        location=args.location,
        extra=extra,
    )

    scraper = HouzzScraper(headless=args.headless)
    if args.input_file:
        scraper.input_file = args.input_file

    logger.info("Starting Houzz Scraper via BaseScraper.run()... (limit=%s)", params.limit)
    records_out = []
    count = 0

    try:
        for rec in scraper.run(params):
            count += 1
            org_name = rec.organization_name or rec.title or "Unknown"
            logger.info("[%d/%d] Streamed: %s | Phone: %s | Email: %s", count, params.limit, org_name, rec.phone, rec.email)
            rec_dict = rec.model_dump() if hasattr(rec, "model_dump") else rec.dict()
            records_out.append(rec_dict)
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user.")
    except Exception as e:
        logger.error("Scraper error: %s", e)
    finally:
        if records_out and args.csv:
            df = pd.DataFrame(records_out)
            df.to_csv(args.csv, index=False, encoding="utf-8-sig")
            logger.info("Saved %d records to %s", len(records_out), args.csv)


if __name__ == "__main__":
    main()
