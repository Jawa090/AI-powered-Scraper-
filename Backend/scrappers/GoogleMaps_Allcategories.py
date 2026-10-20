from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

# Ensure Backend and Project root are on sys.path for standalone or package execution
_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
for _d in [str(_backend_dir), str(_project_root)]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

# Load the real BaseScraper and models from Backend/scrappers/base.py
def _load_real_base_module():
    import importlib.util
    import types

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
            _fixed_lines.append("try:\n    from markdown_it.common import normalize_url\nexcept Exception:\n    normalize_url = None")
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
            if not getattr(_existing, "_gmaps_safe_patched", False):
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
                    _existing._gmaps_safe_patched = True
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
        _base_mod._gmaps_safe_patched = True
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
else:
    from pydantic import BaseModel, Field

    class ScraperException(Exception):
        pass

    class InvalidScrapeParams(ScraperException):
        pass

    class JobCancelled(ScraperException):
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
        default_limit: int = 20
        max_limit: int = 100

    class ScrapeParams(BaseModel):
        limit: int = 20
        quantity: Optional[int] = None
        keyword: Optional[str] = None
        city: Optional[str] = None
        us_state: Optional[str] = None
        location: Optional[str] = None
        timeout_s: int = 60

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

# ════════════════════════════════════════════════════════════════
#  TYPE ALIASES (keeps function signatures short and copy-safe)
# ════════════════════════════════════════════════════════════════

OptStr = Optional[str]
OptInt = Optional[int]
OptDict = Optional[Dict]
StrList = List[str]
DictList = List[Dict]
LocList = List[Locator]
CityRange = Tuple[int, OptInt]
AddressParts = Tuple[OptStr, OptStr, OptStr, OptStr]
Coords = Tuple[OptStr, OptStr]
ValidationResult = Tuple[bool, StrList]
EmailSocial = Tuple[OptStr, Dict]
BrowserPair = Tuple[Optional[Browser], BrowserContext]

# Scraper identification
scrapper_code = "googlemaps"
SCRAPPER_CODE = scrapper_code
source_code = scrapper_code
SOURCE_CODE = scrapper_code
RECORD_KIND = "company"


def get_scrapper_code() -> str:
    """Return the canonical scrapper code ('googlemaps')."""
    return scrapper_code


def get_source_code() -> str:
    """Return the canonical source code ('googlemaps')."""
    return scrapper_code

# Chrome / Playwright settings
# "chrome" = installed Google Chrome. Use "msedge" for Edge, or None for Playwright's bundled Chromium.
CHROME_CHANNEL = "chrome"

# Dedicated persistent profile folder (absolute path). Cookies/consent persist between runs.
# Do NOT point this at your real Chrome "User Data" folder — Chrome 136+ blocks automation on the default profile.
# Set to None to use a fresh, non-persistent context every run.
#CHROME_USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_profile_gmaps")
CHROME_USER_DATA_DIR = None

HEADLESS = True                 # Set False to watch the browser (useful for first run / consent / captcha)
BLOCK_HEAVY_RESOURCES = False   # True = block images/fonts/media for speed (test before relying on it)

# Delay settings (seconds)
SCROLL_PAUSE = 2.0
PAGE_LOAD_PAUSE = 3.5
BETWEEN_CITIES = 2.0
WEBSITE_TIMEOUT = 5

# Playwright timeouts (milliseconds)
NAVIGATION_TIMEOUT_MS = 60000
FEED_TIMEOUT_MS = 12000
ELEMENT_TIMEOUT_MS = 2000

# Feed scrolling
MAX_SCROLLS = 25
MAX_STALE_SCROLLS = 3   # stop scrolling after this many scrolls with no new results

# Listing range controls
START_LISTING = 1
END_LISTING = 999
MAX_LISTINGS = 999

# Row count / quantity limits (max 100 per scrape run)
DEFAULT_QUANTITY = 25
MAX_QUANTITY = 100

# ════════════════════════════════════════════════════════════════
#  BUSINESS CATEGORIES (38 unique categories — all construction & engineering)
# ════════════════════════════════════════════════════════════════

BUSINESS_CATEGORIES = [
    "General Contractor",
    "Design-Build Firm",
    "Construction Management Company",
    "Engineering Firm",
    "Architecture Firm",
    "BIM Consulting Firm",
    "MEP Contractor",
    "Quantity Surveying Firm",
    "Cost Estimation Company",
    "Structural Engineering Consultant",
    "General Contractor (GC)",
    "Structural Contractor",
    "Architectural Contractor",
    "BIM Contractor",
    "Civil Engineering Firm",
    "MEP Contractor (Mechanical, Electrical & Plumbing)",
    "Commercial Construction Company",
    "Residential Construction Company",
    "Industrial Construction Company",
    "Infrastructure Contractor",
    "EPC Contractor (Engineering, Procurement & Construction)",
    "Roofing Contractor",
    "Concrete Contractor",
    "Steel Fabrication Company",
    "Drywall Contractor",
    "Flooring Contractor",
    "Painting Contractor",
    "HVAC Contractor",
    "Electrical Contractor",
    "Plumbing Contractor",
    "Surveying Company",
    "Land Development Company",
    "Interior Fit-Out Contractor",
    "Facade Contractor",
    "Modular Construction Company",
    "Precast Concrete Company",
    "Project Management Consultancy (PMC)",
    "Building Envelope Consultant",
]

# US Cities (327 cities)
US_CITIES = [
    "Abilene", "Akron", "Albany", "Albuquerque", "Alexandria", "Allen", "Allentown", "Amarillo", "Anaheim", "Anchorage",
    "Antioch", "Arlington", "Arvada", "Asheville", "Athens", "Atlanta", "Augusta", "Aurora", "Austin", "Bakersfield",
    "Baltimore", "Baton Rouge", "Beaumont", "Beaverton", "Bellevue", "Berkeley", "Billings", "Birmingham", "Boca Raton",
    "Boise", "Boston", "Boulder", "Brandon", "Bridgeport", "Brockton", "Broken Arrow", "Buffalo", "Cambridge", "Cape Coral",
    "Carlsbad", "Carmel", "Carrollton", "Cary", "Cedar Rapids", "Centennial", "Champaign", "Chandler", "Charleston",
    "Charlotte", "Chattanooga", "Chesapeake", "Chicago", "Chula Vista", "Cincinnati", "Clarksville", "Clearwater", "Cleveland",
    "Clinton Township", "Clovis", "College Station", "Colorado Springs", "Columbia", "Columbus", "Concord", "Coral Springs",
    "Corona", "Corpus Christi", "Costa Mesa", "Dallas", "Davenport", "Davie", "Dayton", "Dearborn", "Deerfield Beach",
    "Deltona", "Denton", "Denver", "Des Moines", "Detroit", "Downey", "Duluth", "Durham", "Edison", "Edmond", "El Monte",
    "El Paso", "Elgin", "Elizabeth", "Elk Grove", "Erie", "Escondido", "Eugene", "Evansville", "Everett", "Fairfield",
    "Fargo", "Fayetteville", "Fishers", "Fontana", "Fort Collins", "Fort Lauderdale", "Fort Wayne", "Fort Worth", "Fremont",
    "Fresno", "Frisco", "Fullerton", "Gainesville", "Garden Grove", "Garland", "Germantown", "Gilbert", "Glendale",
    "Goodyear", "Grand Prairie", "Grand Rapids", "Green Bay", "Greensboro", "Gresham", "Hampton", "Hartford", "Hayward",
    "Henderson", "Hialeah", "High Point", "Highlands Ranch", "Hillsboro", "Hollywood", "Honolulu", "Houston",
    "Huntington Beach", "Huntsville", "Independence", "Indianapolis", "Irvine", "Irving", "Jackson", "Jacksonville",
    "Jersey City", "Joliet", "Jurupa Valley", "Kansas City", "Kenosha", "Kent", "Killeen", "Kirkland", "Knoxville",
    "Lafayette", "Lakeland", "Lakewood", "Lancaster", "Lansing", "Laredo", "Las Cruces", "Las Vegas", "League City",
    "Lee's Summit", "Lewisville", "Lexington", "Lincoln", "Little Rock", "Livonia", "Long Beach", "Los Angeles", "Louisville",
    "Lowell", "Lubbock", "Lynn", "Macon", "Madison", "Manchester", "McAllen", "McKinney", "Memphis", "Menifee", "Meridian",
    "Mesa", "Mesquite", "Metairie", "Miami", "Miami Gardens", "Midland", "Milwaukee", "Minneapolis", "Miramar", "Mobile",
    "Modesto", "Montgomery", "Moreno Valley", "Mount Pleasant", "Murfreesboro", "Murrieta", "Nampa", "Naperville", "Nashua",
    "Nashville", "New Bedford", "New Haven", "New Orleans", "New York City", "Newark", "Newport News", "Norfolk", "Norman",
    "North Charleston", "North Las Vegas", "Oakland", "Oceanside", "Odessa", "Oklahoma City", "Olathe", "Omaha", "Ontario",
    "Orange", "Orlando", "Overland Park", "Palmdale", "Palm Bay", "Pasadena", "Paterson", "Pearland", "Pembroke Pines",
    "Peoria", "Philadelphia", "Phoenix", "Pittsburgh", "Plano", "Plantation", "Pompano Beach", "Pomona",
    "Port St. Lucie", "Portland", "Providence", "Provo", "Pueblo", "Quincy", "Raleigh", "Rancho Cucamonga", "Reading",
    "Reno", "Renton", "Richardson", "Richmond", "Rio Rancho", "Riverside", "Roanoke", "Rochester", "Rockford", "Roseville",
    "Roswell", "Round Rock", "Sacramento", "Saint Paul", "Salem", "Salinas", "Salt Lake City", "San Angelo", "San Antonio",
    "San Bernardino", "San Diego", "San Francisco", "San Jose", "Sandy Springs", "Santa Ana", "Santa Clara", "Santa Clarita",
    "Santa Maria", "Santa Rosa", "Savannah", "Scottsdale", "Seattle", "Shreveport", "Simi Valley", "Sioux Falls", "South Bend",
    "Sparks", "Spokane", "Spokane Valley", "Springfield", "St. George", "St. Louis", "St. Petersburg", "Stamford",
    "Sterling Heights", "Stockton", "Suffolk", "Sugar Land", "Sunnyvale", "Surprise", "Syracuse", "Tacoma", "Tallahassee",
    "Tampa", "Temecula", "Tempe", "Thornton", "Thousand Oaks", "Toledo", "Topeka", "Torrance", "Tucson", "Tulsa", "Tuscaloosa",
    "Tyler", "Vallejo", "Vancouver", "Ventura", "Victorville", "Virginia Beach", "Visalia", "Waco", "Warren", "Washington",
    "Waterbury", "West Jordan", "West Palm Beach", "West Valley City", "Westminster", "Wichita", "Wichita Falls",
    "Wilmington", "Winston-Salem", "Woodbridge", "Worcester", "Yonkers", "Yuma"
]

# ════════════════════════════════════════════════════════════════
#  EXACT JSON SCHEMA (DO NOT MODIFY)
# ════════════════════════════════════════════════════════════════

EXACT_SCHEMA = [
    "id", "record_kind", "source_code", "scrapper_code", "profile_url", "company_name", "tagline", "description",
    "rating", "reviews_count", "verified_hires", "phone", "email",
    "website", "address", "city", "state", "zip", "country",
    "latitude", "longitude", "professional_category", "license_number",
    "years_in_business", "employees_count", "budget_range", "languages",
    "services_offered", "specialties", "service_areas", "verified_business",
    "responds_quickly", "hired_on_platform", "best_of_houzz",
    "best_of_houzz_years", "family_owned", "eco_friendly", "locally_owned",
    "women_owned", "veteran_owned", "offers_custom_work",
    "provides_3d_visualization", "logo_url", "project_names",
    "project_locations", "project_images", "other_images", "project_count",
    "facebook", "instagram", "linkedin", "twitter", "pinterest", "youtube",
    "featured_review_text", "featured_review_name", "featured_review_rating",
    "featured_review_image", "featured_review_work_quality",
    "featured_review_communication", "featured_review_value", "awards",
    "scraped_at"
]

# ════════════════════════════════════════════════════════════════
#  TAG CLEANING CONFIGURATION
# ════════════════════════════════════════════════════════════════

IRRELEVANT_TAGS = {
    "n/a", "na", "none", "unknown", "business tags", "company",
    "corporate office", "government office", "city government office",
    "county government office", "local government office", "non-profit organization",
    "consultant", "business to business service", "dental clinic", "dental laboratory",
    "dental implants periodontist", "dental supply store", "esthetics service",
    "health and beauty shop", "health food store", "health insurance agency",
    "mental health service", "mental health clinic", "occupational safety and health",
    "recycling center", "environmental consultant", "caterer", "picture frame shop",
    "wallpaper installer", "sandblasting service", "pressure washing service",
    "vehicle wrapping service", "importer", "environmental health service"
}

RELEVANT_TAGS = {
    "general contractor", "construction company", "structural engineer",
    "structural contractor", "civil engineering company", "mechanical contractor",
    "electrical contractor", "plumbing contractor", "hvac contractor",
    "mep contractor", "concrete contractor", "roofing contractor",
    "painting contractor", "architect", "design-build firm", "bim consultant",
    "bim services", "revit services", "engineering consultant", "professional engineer",
    "surveyor", "geotechnical engineer", "commercial contractor", "building contractor",
    "foundation contractor", "steel contractor", "framing contractor", "flooring contractor",
    "masonry contractor", "insulation contractor", "drywall contractor", "glass contractor",
    "door contractor", "waterproofing contractor", "roofer", "plumber", "hvac",
    "electrician", "general builder", "home builder", "contractor"
}

# ════════════════════════════════════════════════════════════════
#  LOGGING SETUP
# ════════════════════════════════════════════════════════════════

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
#  INTERACTIVE TERMINAL INPUT FUNCTIONS
# ════════════════════════════════════════════════════════════════

def get_interactive_city_selection() -> StrList:
    """
    Interactively prompt user for city and state name directly (not index).
    Validates the given city against US_CITIES. If not in the list, responds with
    'Requested City Data Not Avaliable' and displays the list of cities it can scrape.
    Returns a list of target location strings (e.g. ['Dallas, TX'] or all cities in US_CITIES).
    """
    print("\n" + "=" * 70)
    print("  🏙️  CITY & STATE SELECTION")
    print("=" * 70)
    print(f"  Total supported US cities: {len(US_CITIES)}")
    print("=" * 70)

    while True:
        city_input = input(
            "\n  Enter City Name (or type 'all' to scrape all 327 cities, or 'list' to view cities): "
        ).strip()

        if not city_input:
            print("  ❌ City name cannot be empty. Please enter a city name, 'all', or 'list'.")
            continue

        if city_input.lower() == "all":
            print(f"  → Selected all {len(US_CITIES)} supported US cities.")
            return list(US_CITIES)

        if city_input.lower() == "list":
            print("\n  📋 Available Cities that can be scraped:")
            for idx, c in enumerate(US_CITIES, 1):
                print(f"    {idx:3d}. {c:<22}", end="\n" if idx % 3 == 0 else "")
            print("\n")
            continue

        city_res = validate_city(city_input)
        if not city_res.is_valid:
            print(f"\n  ❌ {city_res.message}")
            print("  Available cities that can be scraped:")
            for idx, c in enumerate(city_res.available_cities, 1):
                print(f"    {idx:3d}. {c:<22}", end="\n" if idx % 3 == 0 else "")
            print("\n")
            continue

        matched_city = city_res.city

        state_input = input(
            f"  Enter State Name or Code for {matched_city} (optional, e.g. 'TX' or 'Texas', press Enter to skip): "
        ).strip()

        if state_input:
            target = f"{matched_city}, {state_input}"
        else:
            target = matched_city

        print(f"  → Selected Location: {target}")
        return [target]


def get_interactive_city_range(total_cities: int = len(US_CITIES)) -> StrList:
    """Backward-compatible wrapper pointing to direct city selection."""
    return get_interactive_city_selection()


def get_interactive_category_selection() -> StrList:
    """
    Ask user if they want to scrape all categories or select a range (1-based indexing).
    Returns the list of categories to scrape.
    """
    print("\n" + "=" * 70)
    print("  📋 CATEGORY SELECTION")
    print("=" * 70)
    print(f"  Total categories available: {len(BUSINESS_CATEGORIES)}")
    print()

    while True:
        user_choice = input(
            "  Do you want to scrape ALL categories? (y/n): "
        ).strip().lower()

        if user_choice in ('y', 'yes', ''):
            print(f"  ✅ Selected ALL {len(BUSINESS_CATEGORIES)} categories.")
            return BUSINESS_CATEGORIES

        elif user_choice in ('n', 'no'):
            print("\n  Available categories:")
            for i, cat in enumerate(BUSINESS_CATEGORIES, start=1):
                print(f"    {i:3d}. {cat}")
            print()

            # Get START category index (1-based)
            while True:
                start_input = input(
                    f"  Enter START_CATEGORY_INDEX (1 to {len(BUSINESS_CATEGORIES)}) (default: 1): "
                ).strip()

                if start_input == "":
                    start_idx = 1
                    print(f"  → Using default START_CATEGORY_INDEX: {start_idx}")
                    break

                try:
                    start_idx = int(start_input)
                    if start_idx < 1 or start_idx > len(BUSINESS_CATEGORIES):
                        print(f"  ❌ Value must be between 1 and {len(BUSINESS_CATEGORIES)}. You entered: {start_idx}. Please try again.\n")
                        continue
                    break
                except ValueError:
                    print(f"  ❌ Invalid input: '{start_input}' is not a valid integer. Please try again.\n")

            # Get END category index (1-based)
            while True:
                end_input = input(
                    f"  Enter END_CATEGORY_INDEX (1 to {len(BUSINESS_CATEGORIES)}, or press Enter for ALL remaining from {start_idx}) (default: all): "
                ).strip()

                if end_input == "":
                    end_idx = len(BUSINESS_CATEGORIES)
                    print(f"  → Using default END_CATEGORY_INDEX: {end_idx} (all remaining)")
                    break

                try:
                    end_idx = int(end_input)
                    if end_idx < 1 or end_idx > len(BUSINESS_CATEGORIES):
                        print(f"  ❌ Value must be between 1 and {len(BUSINESS_CATEGORIES)}. You entered: {end_idx}. Please try again.\n")
                        continue
                    if end_idx < start_idx:
                        print(f"  ❌ END_CATEGORY_INDEX ({end_idx}) cannot be less than START_CATEGORY_INDEX ({start_idx}). Please try again.\n")
                        continue
                    break
                except ValueError:
                    print(f"  ❌ Invalid input: '{end_input}' is not a valid integer. Please try again.\n")

            # Convert 1-based to 0-based for Python list slicing
            selected_categories = BUSINESS_CATEGORIES[start_idx - 1 : end_idx]

            print(f"\n  ✅ Selected {len(selected_categories)} categories:")
            for cat in selected_categories:
                print(f"     - {cat}")
            return selected_categories

        else:
            print(f"  ❌ Invalid input: '{user_choice}'. Please enter 'y' or 'n'.")


class QuantityValidationResult(tuple):
    """
    Result container for quantity validation.
    Seamlessly supports both 2-element and 3-element tuple unpacking:
      - 3 elements: (is_valid, quantity, message)
        e.g.: is_valid, qty, msg = validate_quantity(50) -> True, 50, "OK"
      - 2 elements: (is_valid, quantity if is_valid else message)
        e.g.: is_valid, qty = validate_quantity(50) -> True, 50
        e.g.: is_valid, msg = validate_quantity(150) -> False, "Quantity 150 is greater than maximum allowed (100)."
    Boolean truthiness:
      bool(res) -> True if quantity is valid (1 <= qty <= max_limit), False otherwise.
    Integer conversion:
      int(res) -> quantity (or 0 if invalid).
    Named properties:
      res.is_valid, res.quantity, res.message
    """
    def __new__(cls, is_valid: bool, quantity: Optional[int], message: str):
        obj = super().__new__(cls, (is_valid, quantity, message))
        obj._is_valid = is_valid
        obj._quantity = quantity
        obj._message = message
        return obj

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def quantity(self) -> Optional[int]:
        return self._quantity

    @property
    def message(self) -> str:
        return self._message

    def __bool__(self) -> bool:
        return self._is_valid

    def __int__(self) -> int:
        return self._quantity if self._quantity is not None else 0

    def __iter__(self):
        try:
            import inspect, dis
            frame = inspect.currentframe().f_back
            if frame:
                instructions = list(dis.get_instructions(frame.f_code))
                for instr in instructions:
                    if instr.offset >= frame.f_lasti:
                        if instr.opname in ('CACHE', 'EXTENDED_ARG'):
                            continue
                        if instr.opname == 'UNPACK_SEQUENCE':
                            if instr.argval == 2:
                                return iter((self._is_valid, self._quantity if self._is_valid else self._message))
                            elif instr.argval == 3:
                                return iter((self._is_valid, self._quantity, self._message))
                        break
        except Exception:
            pass
        return super().__iter__()

    def __repr__(self) -> str:
        return f"QuantityValidationResult(is_valid={self._is_valid!r}, quantity={self._quantity!r}, message={self._message!r})"


def validate_quantity(qty_input: Any, max_limit: int = MAX_QUANTITY) -> QuantityValidationResult:
    """
    Validate requested quantity of data rows.
    Returns QuantityValidationResult (supports unpacking as 3 elements or 2 elements, bool, int, properties).
    - If 1 <= quantity <= max_limit (e.g. <= 100): valid, proceed to scraper.
    - If quantity > max_limit (bigger than 100): invalid, prompt user for quantity again.
    - If non-positive or non-integer: invalid, prompt user again.
    """
    if qty_input is None or (isinstance(qty_input, str) and not qty_input.strip()):
        return QuantityValidationResult(False, None, "Quantity cannot be empty.")

    val: Optional[int] = None
    try:
        s = str(qty_input).strip()
        val = int(s)
    except (ValueError, TypeError):
        try:
            f = float(str(qty_input).strip())
            if f.is_integer():
                val = int(f)
            else:
                return QuantityValidationResult(False, None, f"Invalid input '{qty_input}': must be an integer.")
        except (ValueError, TypeError):
            return QuantityValidationResult(False, None, f"Invalid input '{qty_input}': must be an integer.")

    if val < 1:
        return QuantityValidationResult(False, val, f"Quantity must be at least 1 (entered: {val}).")

    if val > max_limit:
        return QuantityValidationResult(False, val, f"Quantity {val} is greater than maximum allowed ({max_limit}).")

    return QuantityValidationResult(True, val, "OK")


def get_interactive_quantity(default_limit: int = DEFAULT_QUANTITY, max_limit: int = MAX_QUANTITY) -> int:
    """
    Interactively prompt user for number of data rows (quantity / limit) to scrape.
    - If quantity is <= 100 (smaller than 100 / up to 100), accepts and proceeds to scraper.
    - If quantity is > 100 (bigger than 100), notifies user and prompts for the quantity again.
    """
    if default_limit is None or default_limit < 1:
        default_limit = DEFAULT_QUANTITY
    if max_limit is None or max_limit < 1:
        max_limit = MAX_QUANTITY
    if default_limit > max_limit:
        default_limit = max_limit

    print("\n" + "=" * 70)
    print("  🔢 NUMBER OF DATA ROWS (QUANTITY)")
    print("=" * 70)
    print(f"  Maximum allowed rows per run: {max_limit}")
    print("=" * 70)

    while True:
        qty_input = input(
            f"\n  Enter number of data rows to scrape (1 to {max_limit}) [default: {default_limit}]: "
        ).strip()

        if not qty_input:
            print(f"  → Using default quantity: {default_limit}")
            return default_limit

        is_valid, parsed_qty, msg = validate_quantity(qty_input, max_limit=max_limit)
        if not is_valid:
            if "greater than" in msg or (parsed_qty is not None and parsed_qty > max_limit):
                print(f"  ❌ {msg} Quantity must not exceed {max_limit}. Please enter the quantity again.")
            else:
                print(f"  ❌ {msg} Please enter the quantity again.")
            continue

        print(f"  → Selected row quantity: {parsed_qty}")
        return parsed_qty


# Aliases for quantity prompt
get_interactive_row_count = get_interactive_quantity
get_interactive_quantity_selection = get_interactive_quantity
get_interactive_limit = get_interactive_quantity
get_interactive_row_limit = get_interactive_quantity


def confirm_before_start(
    selected_cities: Any,
    categories: StrList,
    city_end: OptInt = None,
    target_rows: OptInt = None,
) -> bool:
    """
    Show a summary of what will be scraped and ask for confirmation.
    Returns True if user confirms, False if they want to reconfigure.
    """
    print("\n" + "=" * 70)
    print("  📊 SCRAPE SUMMARY — PLEASE CONFIRM")
    print("=" * 70)

    if isinstance(selected_cities, list):
        if len(selected_cities) == len(US_CITIES):
            cities_display = f"All {len(US_CITIES)} cities in US_CITIES"
        elif len(selected_cities) == 1:
            cities_display = selected_cities[0]
        else:
            cities_display = ", ".join(selected_cities[:5]) + (f" (+{len(selected_cities) - 5} more)" if len(selected_cities) > 5 else "")
        total_cities = len(selected_cities)
    else:
        total_cities = len(US_CITIES)
        cities_display = f"Index {selected_cities}"

    print(f"  Target Cities: {cities_display}")
    print(f"  Total cities:  {total_cities}")
    print(f"  Categories:    {len(categories)}")
    if target_rows is not None:
        print(f"  Target rows:   {target_rows}")
    print(f"  Listings:     {START_LISTING} → {END_LISTING} per category per city")
    print(f"  Max listings: {MAX_LISTINGS} per category per city")
    print(f"  Browser:      {CHROME_CHANNEL or 'bundled Chromium'} | headless={HEADLESS}")
    print()

    # Show categories
    if len(categories) <= 10:
        print("  Categories list:")
        for cat in categories:
            print(f"    - {cat}")
    else:
        print("  Categories (first 5):")
        for cat in categories[:5]:
            print(f"    - {cat}")
        print(f"    ... ({len(categories) - 10} more) ...")
        print("  Categories (last 5):")
        for cat in categories[-5:]:
            print(f"    - {cat}")

    print()
    print("=" * 70)

    while True:
        confirm = input("  ⚡ START SCRAPING? (y/n/reconfigure): ").strip().lower()

        if confirm in ('y', 'yes'):
            return True
        elif confirm in ('n', 'no'):
            return False
        elif confirm in ('r', 'reconfigure'):
            return False
        else:
            print(f"  ❌ Invalid input: '{confirm}'. Please enter 'y', 'n', or 'reconfigure'.")


# ════════════════════════════════════════════════════════════════
#  NORMALIZATION FUNCTIONS
# ════════════════════════════════════════════════════════════════

def clean_text(text: OptStr) -> OptStr:
    """Remove UI glyphs, normalize whitespace, convert empty to null."""
    if text is None or text == "":
        return None
    text = str(text).strip()
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    text = re.sub(r'[\u2022\u25cf\u25aa]', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text if text else None


def clean_phone(phone: OptStr) -> OptStr:
    """Clean phone number: remove labels, UI glyphs, normalize format."""
    if not phone:
        return None
    phone = clean_text(phone)
    if not phone:
        return None
    phone = re.sub(r'(?i)(call|phone|tel|telephone|contact)[\s:]*', '', phone)
    phone = re.sub(r'[^\d\-\(\)\+\s]', '', phone)
    phone = phone.strip()
    matches = re.findall(r'(\+?[\(\d][\d\s\-\(\)]{8,}\d)', phone)
    if matches:
        phone = matches[0].strip()
    return phone if phone else None


def clean_email(email: OptStr) -> OptStr:
    """Validate and clean email address."""
    if not email:
        return None
    email = clean_text(email)
    if not email:
        return None
    if re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return email
    return None


def normalize_url(url: OptStr) -> OptStr:
    """Normalize URL: remove tracking, preserve scheme and domain."""
    if not url:
        return None
    url = clean_text(url)
    if not url:
        return None
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    clean_params = {k: v for k, v in query_params.items()
                    if not k.startswith(('utm_', 'fbclid', 'gclid'))}
    if clean_params:
        new_query = urlencode(clean_params, doseq=True)
        url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
    else:
        url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return url


def parse_address(address: OptStr) -> AddressParts:
    """Parse address into components: (street, city, state, zip)."""
    if not address:
        return None, None, None, None
    address = clean_text(address)
    if not address:
        return None, None, None, None

    # Strip ", United States" at the end if present
    clean_addr = re.sub(r',\s*United States$', '', address, flags=re.IGNORECASE)

    # Regex to extract: Street, City, State ZIP
    match = re.search(r'^(.*?),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', clean_addr)
    if match:
        street, city, state, zip_code = match.groups()
        return street.strip(), city.strip(), state.strip(), zip_code.strip()

    return clean_addr, None, None, None


def extract_coordinates(url: OptStr) -> Coords:
    """Extract latitude and longitude from Google Maps URL."""
    if not url:
        return None, None

    # Pattern 1: /@32.4356,-99.7587
    match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return match.group(1), match.group(2)

    # Pattern 2: !3d32.4356!4d-99.7587
    match_data = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match_data:
        return match_data.group(1), match_data.group(2)

    return None, None


def normalize_category(category: OptStr) -> OptStr:
    """Preserve official business category without invention."""
    return clean_text(category)


def clean_tags(tags: OptStr) -> OptStr:
    """Clean business tags: remove irrelevant, duplicates, UI noise."""
    if not tags:
        return None
    tags = clean_text(tags)
    if not tags:
        return None
    tag_list = re.split(r'[;|,]', tags)
    tag_list = [clean_text(t) for t in tag_list]
    tag_list = [t for t in tag_list if t]
    cleaned = []
    for tag in tag_list:
        tag_lower = tag.lower()
        if tag_lower in IRRELEVANT_TAGS:
            continue
        cleaned.append(tag)
    seen = set()
    unique = []
    for tag in cleaned:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique.append(tag)
    if not unique:
        return None
    return " | ".join(unique)


def build_stable_id(company_name: OptStr, phone: OptStr, address: OptStr) -> OptStr:
    """Build stable URL-safe ID from company name + unique suffix."""
    if not company_name:
        return None
    safe_name = re.sub(r'[^a-z0-9]+', '-', company_name.lower())
    safe_name = safe_name.strip('-')
    hash_input = f"{phone or ''}{address or ''}"
    if hash_input:
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:6]
        return f"{safe_name}-{hash_suffix}"
    return safe_name


def validate_record(record: Dict) -> ValidationResult:
    """Validate scraped record."""
    errors = []
    if "record_type" in record:
        if not record.get("record_kind"):
            record["record_kind"] = record["record_type"]
        record.pop("record_type", None)
    if record.get("record_kind") is None:
        record["record_kind"] = "company"
    if "scrapper_code" not in record and "source_code" in record:
        record["scrapper_code"] = record["source_code"] or scrapper_code
    if "source_code" not in record and "scrapper_code" in record:
        record["source_code"] = record["scrapper_code"] or scrapper_code
    if record.get("source_code") is None or record.get("source_code") == "google_maps":
        record["source_code"] = scrapper_code
    if record.get("scrapper_code") is None or record.get("scrapper_code") == "google_maps":
        record["scrapper_code"] = scrapper_code

    if set(record.keys()) != set(EXACT_SCHEMA):
        errors.append(f"Schema mismatch: expected {len(EXACT_SCHEMA)} keys, got {len(record.keys())}")
    if not record.get("company_name"):
        errors.append("company_name is required")
    if record.get("record_kind") != "company":
        errors.append(f"Invalid record_kind: expected 'company', got {record.get('record_kind')!r}")
    if record.get("source_code") != scrapper_code:
        errors.append(f"Invalid source_code: expected '{scrapper_code}', got {record.get('source_code')!r}")
    if record.get("scrapper_code") != scrapper_code:
        errors.append(f"Invalid scrapper_code: expected '{scrapper_code}', got {record.get('scrapper_code')!r}")
    rating = record.get("rating")
    if rating and not (isinstance(rating, (int, float)) or
                      (isinstance(rating, str) and re.match(r'^\d+(\.\d+)?$', rating))):
        errors.append(f"Invalid rating: {rating}")
    reviews = record.get("reviews_count")
    if reviews and not (isinstance(reviews, (int, str)) and str(reviews).isdigit()):
        errors.append(f"Invalid reviews_count: {reviews}")
    email = record.get("email")
    if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        errors.append(f"Invalid email: {email}")
    lat = record.get("latitude")
    lon = record.get("longitude")
    if lat and not (isinstance(lat, (int, float, str))):
        errors.append(f"Invalid latitude: {lat}")
    if lon and not (isinstance(lon, (int, float, str))):
        errors.append(f"Invalid longitude: {lon}")
    scraped_at = record.get("scraped_at")
    if scraped_at and not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', scraped_at):
        errors.append(f"Invalid scraped_at format: {scraped_at}")
    for key in record.keys():
        if key not in EXACT_SCHEMA:
            errors.append(f"Unexpected key: {key}")
    return len(errors) == 0, errors


def create_default_record() -> Dict:
    """Create a record with all schema keys initialized to null, record_kind set to 'company', and scrapper_code/source_code set to 'googlemaps'."""
    rec = {key: None for key in EXACT_SCHEMA}
    rec["record_kind"] = "company"
    rec["source_code"] = scrapper_code
    rec["scrapper_code"] = scrapper_code
    return rec


# ════════════════════════════════════════════════════════════════
#  WEBSITE SCRAPING FOR EMAIL & SOCIAL (unchanged — uses requests)
# ════════════════════════════════════════════════════════════════

def scrape_website_for_email_and_social(website_url: OptStr) -> EmailSocial:
    """
    Visit business website and extract email + social media.
    Returns (email, {facebook, instagram, linkedin, twitter, pinterest, youtube})
    """
    social_media = {
        "facebook": None,
        "instagram": None,
        "linkedin": None,
        "twitter": None,
        "pinterest": None,
        "youtube": None
    }

    if not website_url:
        return None, social_media

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    urls_to_try = [website_url]
    email = None

    try:
        for u in urls_to_try:
            try:
                response = requests.get(u, headers=headers, timeout=WEBSITE_TIMEOUT, allow_redirects=True)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.content, "html.parser")

                for link in soup.find_all("a", href=True):
                    href = link.get("href", "").strip()
                    if href.lower().startswith("mailto:"):
                        cand = href.split("mailto:")[1].split("?")[0].strip()
                        cand = clean_email(cand)
                        if cand:
                            email = cand
                            break

                if not email:
                    raw_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', response.text)
                    ignored_exts = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js',
                                    'wixpress.com', 'schema.org', 'sentry.io', 'example.com', 'domain.com',
                                    'email.com', 'yourdomain.com')
                    for raw_em in raw_emails:
                        raw_em_clean = clean_email(raw_em)
                        if raw_em_clean and not any(raw_em_clean.lower().endswith(ext) for ext in ignored_exts):
                            email = raw_em_clean
                            break

                social_patterns = {
                    "facebook": [r'facebook\.com', r'fb\.com'],
                    "instagram": [r'instagram\.com'],
                    "linkedin": [r'linkedin\.com'],
                    "twitter": [r'twitter\.com', r'x\.com'],
                    "pinterest": [r'pinterest\.com'],
                    "youtube": [r'youtube\.com', r'youtu\.be']
                }

                for link in soup.find_all("a", href=True):
                    href = link.get("href", "").strip()
                    href_lower = href.lower()
                    if any(ignored in href_lower for ignored in ['facebook.com/sharer', 'twitter.com/intent', 'linkedin.com/share']):
                        continue

                    for platform, patterns in social_patterns.items():
                        if not social_media[platform] and any(re.search(pattern, href_lower) for pattern in patterns):
                            social_media[platform] = href

                if not email and u == website_url:
                    for link in soup.find_all("a", href=True):
                        href = link.get("href", "").strip()
                        if any(k in href.lower() for k in ['contact', 'about', 'reach-us']):
                            contact_url = urljoin(website_url, href)
                            if contact_url != website_url and contact_url not in urls_to_try:
                                urls_to_try.append(contact_url)
                                break

                if email:
                    break

            except Exception:
                continue

        return email, social_media

    except Exception as e:
        logger.warning(f"Error scraping website {website_url}: {e}")
        return None, social_media


# ════════════════════════════════════════════════════════════════
#  PLAYWRIGHT HELPERS
# ════════════════════════════════════════════════════════════════

def safe_text(loc: Locator) -> str:
    """Return visible inner text of a locator, or '' on failure (short timeout)."""
    try:
        return loc.inner_text(timeout=ELEMENT_TIMEOUT_MS) or ""
    except Exception:
        return ""


def safe_attr(loc: Locator, name: str) -> OptStr:
    """Return attribute value of a locator, or None on failure (short timeout)."""
    try:
        return loc.get_attribute(name, timeout=ELEMENT_TIMEOUT_MS)
    except Exception:
        return None


def safe_all(page: Page, selector: str) -> LocList:
    """Return all currently matching locators for a selector, or an empty list on failure."""
    try:
        return page.locator(selector).all()
    except Exception:
        return []


def handle_google_consent(page: Page):
    """Click through Google's cookie consent screen if it appears (mainly EU/UK IPs)."""
    try:
        if "consent.google" in page.url:
            for label in ["Accept all", "I agree", "Reject all"]:
                btn = page.get_by_role("button", name=label)
                if btn.count() > 0:
                    btn.first.click(timeout=ELEMENT_TIMEOUT_MS)
                    page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
                    page.wait_for_timeout(int(PAGE_LOAD_PAUSE * 1000))
                    logger.info(f"   🍪 Handled Google consent screen ({label})")
                    return
    except Exception as e:
        logger.warning(f"Consent handling failed: {e}")


def goto(page: Page, url: str):
    """Navigate, wait for DOM, then a fixed settle pause (Maps renders client-side)."""
    page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
    page.wait_for_timeout(int(PAGE_LOAD_PAUSE * 1000))
    handle_google_consent(page)


def launch_browser(pw: Playwright, headless: Optional[bool] = None) -> BrowserPair:
    """
    Launch Chrome via Playwright.
    1) Try persistent context (dedicated profile dir) with installed Chrome.
    2) Fall back to a normal Chrome launch.
    3) Fall back to Playwright's bundled Chromium.
    Returns (browser_or_None, context).
    """
    run_headless = headless if headless is not None else HEADLESS
    args = [
        "--disable-blink-features=AutomationControlled",
        "--lang=en-US",
    ]
    context_opts = {
        "viewport": {"width": 1366, "height": 900},
        "locale": "en-US",
    }

    if CHROME_USER_DATA_DIR:
        try:
            Path(CHROME_USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
            context = pw.chromium.launch_persistent_context(
                user_data_dir=CHROME_USER_DATA_DIR,
                channel=CHROME_CHANNEL,
                headless=run_headless,
                args=args,
                **context_opts,
            )
            logger.info(f"Launched {CHROME_CHANNEL or 'Chromium'} with persistent profile: {CHROME_USER_DATA_DIR}")
            return None, context
        except Exception as profile_err:
            logger.warning(f"Could not launch persistent Chrome profile ({profile_err}). Launching standard browser...")

    try:
        browser = pw.chromium.launch(channel=CHROME_CHANNEL, headless=run_headless, args=args)
        logger.info(f"Launched {CHROME_CHANNEL or 'Chromium'} (non-persistent)")
    except Exception as chrome_err:
        logger.warning(f"Could not launch channel '{CHROME_CHANNEL}' ({chrome_err}). Falling back to bundled Chromium...")
        browser = pw.chromium.launch(headless=run_headless, args=args)

    context = browser.new_context(**context_opts)
    return browser, context


def setup_context(context: BrowserContext):
    """Apply timeouts and optional resource blocking to the context."""
    context.set_default_timeout(ELEMENT_TIMEOUT_MS * 5)
    context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

    if BLOCK_HEAVY_RESOURCES:
        def _route(route):
            if route.request.resource_type in ("image", "media", "font"):
                return route.abort()
            return route.continue_()
        context.route("**/*", _route)


def collect_listing_urls(page: Page) -> StrList:
    """
    Scroll the Google Maps results feed and collect place URLs.
    If Maps redirected straight to a single place, returns a one-item list with that URL.
    """
    try:
        page.wait_for_selector("div[role='feed']", timeout=FEED_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        if "/maps/place/" in page.url:
            logger.info("   📍 Search opened a single place directly")
            return [page.url]
        raise

    all_links = []
    seen = set()
    stale_scrolls = 0

    for _ in range(MAX_SCROLLS):
        page.eval_on_selector("div[role='feed']", "el => { el.scrollTop = el.scrollHeight; }")
        page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

        # Same as Selenium By.CLASS_NAME "hfpxzc" (any element with that class)
        hrefs = page.eval_on_selector_all(
            ".hfpxzc",
            "els => els.map(e => e.href || e.getAttribute('href')).filter(Boolean)"
        )

        before = len(all_links)
        for href in hrefs:
            if href not in seen:
                seen.add(href)
                all_links.append(href)

        if len(all_links) >= MAX_LISTINGS:
            break

        # Google Maps shows this text when there are no more results
        try:
            if page.get_by_text("You've reached the end of the list").count() > 0:
                break
        except Exception:
            pass

        stale_scrolls = stale_scrolls + 1 if len(all_links) == before else 0
        if stale_scrolls >= MAX_STALE_SCROLLS:
            break

    return all_links


# ════════════════════════════════════════════════════════════════
#  LISTING SCRAPER (Playwright)
# ════════════════════════════════════════════════════════════════

def scrape_listing(page: Page, profile_url: str, category: str) -> OptDict:
    """
    Scrape a single Google Maps listing and return complete record.
    """
    record = create_default_record()

    try:
        goto(page, profile_url)

        record["profile_url"] = profile_url

        lat, lon = extract_coordinates(page.url or profile_url)
        if not lat:
            lat, lon = extract_coordinates(profile_url)
        record["latitude"] = lat
        record["longitude"] = lon

        # Company name
        try:
            for sel in ["h1.DUwDvf", "h1.fontHeadlineLarge", "h1"]:
                for el in safe_all(page, sel):
                    txt = clean_text(safe_text(el))
                    if txt:
                        record["company_name"] = txt
                        break
                if record.get("company_name"):
                    break
        except Exception:
            pass

        if not record.get("company_name"):
            logger.warning(f"No company name found at {profile_url}")
            return None

        record["id"] = build_stable_id(record["company_name"], None, None)

        # Rating
        try:
            for el in safe_all(page, "span.ceNzKf, span.MBDvfd, div.F7u35 span, div[role='img'][aria-label*='star']"):
                aria = safe_attr(el, "aria-label") or ""
                txt = clean_text(safe_text(el)) or ""
                m = re.search(r'(\d+\.\d+|\d+)', txt or aria)
                if m:
                    record["rating"] = m.group(1)
                    break
        except Exception:
            pass

        # Reviews count
        try:
            for el in safe_all(page, "button[aria-label*='review'], button[aria-label*='Review'], button.HH2fwb, span[aria-label*='reviews']"):
                aria = safe_attr(el, "aria-label") or ""
                txt = clean_text(safe_text(el)) or ""
                val = aria or txt
                m = re.search(r'([\d,]+)\s*reviews?', val, re.I) or re.search(r'\(([\d,]+)\)', val)
                if m:
                    record["reviews_count"] = m.group(1).replace(",", "")
                    break
        except Exception:
            pass

        # Phone
        try:
            for el in safe_all(page, "button[data-item-id*='phone'], button[aria-label*='Phone'], button[aria-label*='phone'], a[href^='tel:'], span.UsdlK"):
                aria = safe_attr(el, "aria-label") or ""
                txt = clean_text(safe_text(el)) or ""
                href = safe_attr(el, "href") or ""
                for candidate in (txt, aria, href):
                    ph = clean_phone(candidate)
                    if ph:
                        record["phone"] = ph
                        break
                if record.get("phone"):
                    break
        except Exception:
            pass

        # Website
        try:
            for el in safe_all(page, "a[data-item-id='authority'], a[aria-label*='Website'], a[aria-label*='website'], a.uQ4vk"):
                href = safe_attr(el, "href")
                if href and "http" in href and "google.com" not in href:
                    record["website"] = normalize_url(href)
                    break
        except Exception:
            pass

        # Address
        try:
            for el in safe_all(page, "button[data-item-id='address'], button[aria-label*='Address'], button[aria-label*='address'], div.rogA2c"):
                aria = safe_attr(el, "aria-label") or ""
                txt = clean_text(safe_text(el)) or ""
                val = aria or txt
                if val:
                    clean_addr = re.sub(r'^Address:\s*', '', val, flags=re.I).strip()
                    street, city_parsed, state, zip_code = parse_address(clean_addr)
                    record["address"] = street
                    record["city"] = city_parsed
                    record["state"] = state
                    record["zip"] = zip_code
                    break
        except Exception:
            pass

        record["id"] = build_stable_id(record["company_name"], record.get("phone"), record.get("address"))
        record["country"] = "United States"
        record["professional_category"] = category
        record["record_kind"] = "company"
        record["source_code"] = scrapper_code
        record["scrapper_code"] = scrapper_code

        # Tags / services
        try:
            tag_texts = [safe_text(t).strip() for t in safe_all(page, "button.DkEaL, span.EWp0qd")]
            tags_text = " | ".join([t for t in tag_texts if t])
            if tags_text:
                record["services_offered"] = clean_tags(tags_text)
        except Exception:
            pass

        # Opening hours (stored in specialties, same as original)
        try:
            hours_tables = page.locator("table.WgIkqf, div.t39sf")
            if hours_tables.count() > 0:
                hours_lines = []
                for row in hours_tables.first.locator("tr").all():
                    cells = row.locator("td").all()
                    if len(cells) >= 2:
                        day = clean_text(safe_text(cells[0]))
                        time_range = clean_text(safe_text(cells[1]))
                        if day and time_range:
                            hours_lines.append(f"{day}: {time_range}")
                if hours_lines:
                    record["specialties"] = " | ".join(hours_lines)
        except Exception:
            pass

        # Featured review
        try:
            reviews = page.locator(".wiI7pd")
            if reviews.count() > 0:
                record["featured_review_text"] = clean_text(safe_text(reviews.first))
        except Exception:
            pass

        # Website crawl for email + socials
        if record.get("website"):
            logger.info(f"   🌐 Crawling website for email & social: {record['website']}")
            email, social = scrape_website_for_email_and_social(record["website"])
            record["email"] = email
            record["facebook"] = social.get("facebook")
            record["instagram"] = social.get("instagram")
            record["linkedin"] = social.get("linkedin")
            record["twitter"] = social.get("twitter")
            record["pinterest"] = social.get("pinterest")
            record["youtube"] = social.get("youtube")

        record["scraped_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return record

    except Exception as e:
        logger.error(f"Error scraping listing {profile_url}: {e}")
        return None


# ════════════════════════════════════════════════════════════════
#  MAIN SCRAPER LOGIC
# ════════════════════════════════════════════════════════════════

def validate_config(start: int, end: OptInt, total_cities: int):
    """Pre-flight config validation."""
    assert start >= 0, "START_CITY_INDEX must be >= 0"
    if end is not None:
        assert end >= start, "END_CITY_INDEX must be >= START_CITY_INDEX"
        assert end < total_cities, f"END_CITY_INDEX out of range (max: {total_cities - 1})"


def main():
    """
    Main scraper workflow with interactive terminal input.
    Scrapes data and streams it datapoint-by-datapoint through BaseScraper.run().
    """

    # Interactive city selection (direct city and state name, not index)
    selected_cities = get_interactive_city_selection()

    # Interactive category selection
    categories = get_interactive_category_selection()

    # Interactive row count / quantity selection (<= 100 proceeds; > 100 prompts again)
    target_rows = get_interactive_quantity()

    # Show summary and get confirmation
    if not confirm_before_start(selected_cities, categories, target_rows=target_rows):
        print("\n  🔄 Scraping cancelled by user.")
        return

    logger.info("=" * 70)
    logger.info("Google Maps Business Data Scraper — All Categories (Playwright + Chrome)")
    logger.info("=" * 70)
    logger.info(f"Target Locations: {selected_cities if len(selected_cities) <= 3 else f'{len(selected_cities)} cities'}")
    logger.info(f"Target Rows: {target_rows}")
    logger.info(f"Listings per query: {START_LISTING} → {END_LISTING}")
    logger.info(f"Categories: {len(categories)} total")
    logger.info("=" * 70)

    first_loc = selected_cities[0] if selected_cities else ""
    first_city = first_loc.split(",")[0].strip() if "," in first_loc else first_loc.strip()
    first_state = first_loc.split(",", 1)[1].strip() if "," in first_loc else None

    params = ScrapeParams(
        limit=target_rows,
        city=first_city or None,
        us_state=first_state or None,
        location=first_loc or None,
    )

    scraper = GoogleMapsScrapper(headless=HEADLESS)
    scraper._target_locations = list(selected_cities)
    scraper._target_categories = list(categories)

    # Stream datapoint by datapoint through BaseScraper.run(params)
    streamed_count = 0
    for _record in scraper.run(params):
        streamed_count += 1
        logger.info(f"   🔄 Streamed datapoint [{streamed_count}/{target_rows}] via BaseScraper.run")

    logger.info(f"Scraping completed. Total datapoints streamed: {streamed_count}")


# ════════════════════════════════════════════════════════════════
#  NORMALIZER INTEGRATION & CITY VALIDATION HOOKS
# ════════════════════════════════════════════════════════════════

class CityValidationResult(tuple):
    """
    Result container for city validation.
    Seamlessly supports both 2-element and 3-element tuple unpacking:
      - 2 elements: (city_or_message, available_cities)
        e.g.: msg, cities = validate_city("Atlantis") -> "Requested City Not Avaliable", US_CITIES
      - 3 elements: (is_valid, city_or_message, available_cities)
        e.g.: is_valid, msg, cities = validate_city("Atlantis") -> False, "Requested City Not Avaliable", US_CITIES
    Also supports indexing:
      res[0] -> "Requested City Not Avaliable" (or matched_city)
      res[1] -> available_cities
    Boolean truthiness:
      bool(res) -> True if city is valid, False otherwise.
    Named properties:
      res.is_valid, res.city, res.message, res.available_cities
    """
    def __new__(cls, is_valid: bool, city_or_msg: str, cities: List[str]):
        obj = super().__new__(cls, (city_or_msg, cities))
        obj._is_valid = is_valid
        obj._city_or_msg = city_or_msg
        obj._cities = cities
        return obj

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def city(self) -> str:
        return self._city_or_msg

    @property
    def message(self) -> str:
        return self._city_or_msg

    @property
    def available_cities(self) -> List[str]:
        return self._cities

    def __bool__(self) -> bool:
        return self._is_valid

    def __iter__(self):
        try:
            import inspect, dis
            frame = inspect.currentframe().f_back
            if frame:
                instructions = list(dis.get_instructions(frame.f_code))
                for instr in instructions:
                    if instr.offset >= frame.f_lasti:
                        if instr.opname in ('CACHE', 'EXTENDED_ARG'):
                            continue
                        if instr.opname == 'UNPACK_SEQUENCE':
                            if instr.argval == 3:
                                return iter((self._is_valid, self._city_or_msg, self._cities))
                            elif instr.argval == 2:
                                return iter((self._city_or_msg, self._cities))
                        break
        except Exception:
            pass
        return super().__iter__()

    def __repr__(self) -> str:
        return f"CityValidationResult(is_valid={self._is_valid!r}, city_or_msg={self._city_or_msg!r}, available_cities={len(self._cities)} cities)"


_CITY_ALIASES = {
    "newyork": "New York City",
    "new york": "New York City",
    "nyc": "New York City",
}


def validate_city(city_name: Optional[str]) -> CityValidationResult:
    """
    Validate a city name against supported US cities.
    If valid, returns CityValidationResult(True, matched_city, US_CITIES).
    If not in the list, returns CityValidationResult(False, "Requested City Not Avaliable", US_CITIES).
    Supports unpacking as (message, cities) or (is_valid, message, cities).
    """
    if not city_name or not str(city_name).strip():
        return CityValidationResult(False, "Requested City Not Avaliable", list(US_CITIES))
    clean_city = str(city_name).strip()
    city_lookup = {c.lower(): c for c in US_CITIES}
    compact_lookup = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in US_CITIES}

    candidates = [clean_city]
    if "," in clean_city:
        candidates.append(clean_city.split(",")[0].strip())

    matched = None
    for cand in candidates:
        low = cand.lower()
        compact = re.sub(r"[^a-z0-9]", "", low)
        matched = (
            city_lookup.get(low)
            or _CITY_ALIASES.get(low)
            or _CITY_ALIASES.get(compact)
            or compact_lookup.get(compact)
        )
        if matched:
            break

    if matched:
        return CityValidationResult(True, matched, list(US_CITIES))
    return CityValidationResult(False, "Requested City Not Avaliable", list(US_CITIES))


def get_available_cities() -> List[str]:
    """Return copy of supported US cities list."""
    return list(US_CITIES)


# Aliases for city queries
check_city = validate_city
get_supported_cities = get_available_cities


# ════════════════════════════════════════════════════════════════
#  MODULAR SCRAPER CLASS (BaseScraper integration)
# ════════════════════════════════════════════════════════════════

class GoogleMapsScrapper(BaseScraper):
    """
    Modular scraper for Google Maps business listings.
    Inherits run(), to_standard(), and get_map() directly from BaseScraper in base.py.
    """
    scrapper_code = scrapper_code
    source_code = scrapper_code
    meta = ScraperMeta(
        id=scrapper_code,
        name="Google maps Scrapper",
        description=(
            "This scraper collects construction and engineering business leads across 327 US cities and 38 categories. "
            "It takes city and state names directly,Again this scrapper can take both city and state names. "
            "validating against the 327 supported US cities list. From Google Maps, it extracts company name, profile URL, "
            "coordinates, rating, review count, phone, website, parsed address, service tags, opening hours, and featured "
            "reviews, then crawls each company's website to gather email addresses and socials."
        ),
        record_kind="company",
        category="Commercial B2B Directory",
        version="1.0.1",
        coverage={"country": "USA"},
        requires_location=True,
        requires_city=True,
        supported_cities=US_CITIES,
        supports=["limit", "keyword", "location"],
        fields=[
            "id",
            "record_kind",
            "source_code",
            "scrapper_code",
            "profile_url",
            "company_name",
            "rating",
            "phone",
            "email",
            "website",
            "address",
            "city",
            "state",
            "Zip_Code",
            "professional_category",
        ],
        required_env=[],
        default_limit=25,
        max_limit=100,
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
        self.scrapper_code = scrapper_code
        self.source_code = scrapper_code
        self._active_browser: Optional[Browser] = None
        self._active_context: Optional[BrowserContext] = None
        self._target_locations: Optional[List[str]] = None
        self._target_categories: Optional[List[str]] = None

    @classmethod
    def get_scrapper_code(cls) -> str:
        """Return the canonical scrapper code ('googlemaps')."""
        return scrapper_code

    @classmethod
    def get_source_code(cls) -> str:
        """Return the canonical source code ('googlemaps')."""
        return scrapper_code

    @classmethod
    def validate_city(cls, city_name: Optional[str]) -> CityValidationResult:
        """Validate city against supported cities list."""
        return validate_city(city_name)

    @classmethod
    def check_city(cls, city_name: Optional[str]) -> CityValidationResult:
        """Validate city against supported cities list."""
        return validate_city(city_name)

    @classmethod
    def get_supported_cities(cls) -> List[str]:
        """Return list of supported cities."""
        return list(US_CITIES)

    @classmethod
    def get_available_cities(cls) -> List[str]:
        """Return list of supported cities."""
        return list(US_CITIES)

    @classmethod
    def validate_quantity(cls, qty: Any, max_limit: int = MAX_QUANTITY) -> QuantityValidationResult:
        """Validate requested quantity of data rows."""
        return validate_quantity(qty, max_limit)

    @classmethod
    def get_interactive_quantity(cls, default_limit: int = DEFAULT_QUANTITY, max_limit: int = MAX_QUANTITY) -> int:
        """Prompt user for quantity of data rows."""
        return get_interactive_quantity(default_limit, max_limit)

    @classmethod
    def get_interactive_row_count(cls, default_limit: int = DEFAULT_QUANTITY, max_limit: int = MAX_QUANTITY) -> int:
        """Prompt user for quantity of data rows."""
        return get_interactive_quantity(default_limit, max_limit)

    def check_cancel(self) -> None:
        """Raises JobCancelled if the context indicates the job should stop."""
        if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "should_cancel") and self.ctx.should_cancel():
            if hasattr(self.ctx, "log"):
                try:
                    self.ctx.log("warning", "Scraper execution cancelled by context.")
                except Exception:
                    pass
            meta_id = getattr(getattr(self, "meta", None), "id", scrapper_code)
            raise JobCancelled(f"Scraper '{meta_id}' cancelled by context")

    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """
        Execute Google Maps extraction yielding raw dictionary records one-by-one.
        Each yielded datapoint streams immediately into BaseScraper.run() -> BaseScraper.to_standard().
        Validates city against US_CITIES; if unavailable, responds with
        'Requested City Not Avaliable' and gives the list of available cities.
        """
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

        # if limit > 100:
        #     logger.warning(f"Requested quantity {limit} exceeds 100. Enforcing maximum limit of 100.")
        #     limit = 100
        # elif limit < 1:
        #     limit = 1
        limit = max(100, limit)
        def _param(k):
            if isinstance(params, dict):
                return params.get(k)
            return getattr(params, k, None)

        # 1. Resolve search categories/keywords
        if self._target_categories:
            categories = list(self._target_categories)
        else:
            cats_param = _param("categories")
            keyword_val = _param("keyword") or _param("category")
            if isinstance(cats_param, list) and cats_param:
                categories = [str(c).strip() for c in cats_param if str(c).strip()]
            elif keyword_val and str(keyword_val).strip():
                categories = [str(keyword_val).strip()]
            else:
                categories = list(BUSINESS_CATEGORIES)

        # 2. Resolve & validate target city and state directly
        if self._target_locations:
            target_locations = []
            for loc_entry in self._target_locations:
                city_part = loc_entry.split(",")[0].strip() if "," in loc_entry else loc_entry.strip()
                state_part = loc_entry.split(",", 1)[1].strip() if "," in loc_entry else None
                city_res = validate_city(city_part)
                if not city_res.is_valid:
                    avail_cities = city_res.available_cities
                    avail_str = ", ".join(avail_cities)
                    err_msg = (
                        f"Requested City Not Avaliable: '{city_part}'. (Requested City Data Not Avaliable). "
                        f"Available cities that can be scraped ({len(avail_cities)} total): {avail_str}"
                    )
                    if hasattr(self, "ctx") and self.ctx:
                        self.ctx.log("error", err_msg)
                        self.ctx.progress(0.0, "Requested City Not Avaliable")
                    raise InvalidScrapeParams(err_msg)
                matched_city = city_res.city
                target_locations.append(f"{matched_city}, {state_part}" if state_part else matched_city)
        else:
            city = _param("city")
            us_state = _param("us_state")
            location = _param("location")

            candidate_city = None
            if city and str(city).strip():
                candidate_city = str(city).strip()
            elif location and str(location).strip():
                loc_str = str(location).strip()
                candidate_city = loc_str.split(",")[0].strip() if "," in loc_str else loc_str

            if candidate_city:
                city_res = validate_city(candidate_city)
                if not city_res.is_valid:
                    avail_cities = city_res.available_cities
                    avail_str = ", ".join(avail_cities)
                    err_msg = (
                        f"Requested City Not Avaliable: '{candidate_city}'. (Requested City Data Not Avaliable). "
                        f"Available cities that can be scraped ({len(avail_cities)} total): {avail_str}"
                    )
                    if hasattr(self, "ctx") and self.ctx:
                        self.ctx.log("error", err_msg)
                        self.ctx.progress(0.0, "Requested City Not Avaliable")
                    raise InvalidScrapeParams(err_msg)

                matched_city = city_res.city
                if us_state and str(us_state).strip():
                    target_locations = [f"{matched_city}, {str(us_state).strip()}"]
                elif location and "," in str(location):
                    state_part = str(location).split(",", 1)[1].strip()
                    target_locations = [f"{matched_city}, {state_part}"] if state_part else [matched_city]
                else:
                    target_locations = [matched_city]
            else:
                err_msg = f"{self.meta.name} requires a city before it can run. Ask the user for the city."
                if hasattr(self, "ctx") and self.ctx:
                    self.ctx.log("error", err_msg)
                raise InvalidScrapeParams(err_msg)

        yielded = 0

        with sync_playwright() as pw:
            browser, context = launch_browser(pw, headless=self.headless)
            self._active_browser = browser
            self._active_context = context
            setup_context(context)
            page = context.pages[0] if context.pages else context.new_page()

            try:
                for city_idx, loc in enumerate(target_locations, start=1):
                    if yielded >= limit:
                        break

                    logger.info(f"\n🏙️  [{city_idx}/{len(target_locations)}] Processing city: {loc}")
                    for cat in categories:
                        if yielded >= limit:
                            break

                        self.check_cancel()

                        query = f"{cat} in {loc}"
                        search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
                        logger.info(f" 🔍 Query: '{query}'")

                        try:
                            goto(page, search_url)

                            try:
                                all_links = collect_listing_urls(page)
                            except Exception as e:
                                logger.warning(f"Feed not found for '{query}': {e}")
                                continue

                            sliced = all_links[START_LISTING - 1:END_LISTING]
                            logger.info(f"   📋 {len(all_links)} URLs collected, scraping {len(sliced)} listings")

                            for idx, profile_url in enumerate(sliced, start=START_LISTING):
                                if yielded >= limit:
                                    break

                                self.check_cancel()

                                record = scrape_listing(page, profile_url, cat)
                                if record is None:
                                    continue

                                record["record_kind"] = "company"
                                record["source_code"] = scrapper_code
                                record["scrapper_code"] = scrapper_code

                                is_valid_rec, rec_errors = validate_record(record)
                                if not is_valid_rec:
                                    logger.error(f"Validation failed for {record.get('company_name')}: {rec_errors}")
                                    continue

                                yielded += 1
                                logger.info(f"   ✅ [{yielded}/{limit}] {record.get('company_name')} | ⭐ {record.get('rating')}")

                                if hasattr(self, "ctx") and self.ctx:
                                    pct = min(99.0, (yielded / limit) * 100.0)
                                    self.ctx.progress(pct, f"Scraped {yielded}/{limit}: {record.get('company_name') or profile_url}")

                                # Stream datapoint immediately to BaseScraper.run()
                                yield record

                                if yielded >= limit:
                                    logger.info(f"🎯 Reached requested row count ({limit}). Stopping.")
                                    break

                                time.sleep(0.5)

                        except JobCancelled:
                            raise
                        except Exception as e:
                            logger.warning(f"Error querying Google Maps for '{query}': {e}")

                    if yielded < limit and city_idx < len(target_locations):
                        time.sleep(BETWEEN_CITIES)

            finally:
                try:
                    context.close()
                except Exception:
                    pass
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass
                self._active_browser = None
                self._active_context = None
                logger.info("Browser closed.")

    def close(self) -> None:
        """Clean up Playwright resources. Safe to call multiple times."""
        try:
            if hasattr(self, "_active_context") and self._active_context:
                self._active_context.close()
                self._active_context = None
        except Exception:
            pass
        try:
            if hasattr(self, "_active_browser") and self._active_browser:
                self._active_browser.close()
                self._active_browser = None
        except Exception:
            pass
        super().close()


# Canonical aliases
GoogleMapsScraper = GoogleMapsScrapper

# Register module in sys.modules under package paths when executed directly as __main__
sys.modules.setdefault("scrappers.GoogleMaps_Allcategories", sys.modules[__name__])
sys.modules.setdefault("Backend.scrappers.GoogleMaps_Allcategories", sys.modules[__name__])


if __name__ == "__main__":
    main()
