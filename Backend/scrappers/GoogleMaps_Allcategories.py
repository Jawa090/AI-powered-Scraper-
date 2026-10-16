from Backend.scrappers.normalize import normalizer
from scrappers.base import BaseScraper, InvalidScrapeParams, ScraperMeta, ScrapeParams, StandardRecord
import csv
import json
import time
import os
import sys
import re
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse, parse_qs, urlencode, urljoin
from pathlib import Path
from collections import defaultdict
from .normalize import Normalize
import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from playwright.sync_api import (
    sync_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    Locator,
    TimeoutError as PlaywrightTimeoutError,
)

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

# ================== CONFIG ==================
# Chrome / Playwright settings
# "chrome" = installed Google Chrome. Use "msedge" for Edge, or None for Playwright's bundled Chromium.
CHROME_CHANNEL = "chrome"

# Dedicated persistent profile folder (absolute path). Cookies/consent persist between runs.
# Do NOT point this at your real Chrome "User Data" folder — Chrome 136+ blocks automation on the default profile.
# Set to None to use a fresh, non-persistent context every run.
CHROME_USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_profile_gmaps")

HEADLESS = True                 # Set False to watch the browser (useful for first run / consent / captcha)
BLOCK_HEAVY_RESOURCES = False   # True = block images/fonts/media for speed (test before relying on it)

# Output files (NO JSONL — JSON, CSV and XLSX)
CSV_FILE = "ServicesFromGM.csv"
JSON_FILE = "ServicesFromGM.json"
XLSX_FILE = "ServicesFromGM.xlsx"
LOG_FILE = "scraper.log"

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
MAX_SCROLLS = 10
MAX_STALE_SCROLLS = 3   # stop scrolling after this many scrolls with no new results

# Listing range controls
START_LISTING = 1
END_LISTING = 999
MAX_LISTINGS = 999

# Export formats (JSONL completely removed)
EXPORT_CSV = True
EXPORT_XLSX = True

# XLSX settings
XLSX_SHEET_NAME = "Businesses"
XLSX_SAVE_EVERY = 25        # Checkpoint JSON + XLSX every N new records (0 = only at the end)
XLSX_MAX_COL_WIDTH = 60
XLSX_FLOAT_COLUMNS = {"rating", "latitude", "longitude"}
XLSX_INT_COLUMNS = {"reviews_count"}
EXCEL_CELL_LIMIT = 32767    # Excel's max characters per cell

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
    "id", "profile_url", "company_name", "tagline", "description",
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
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
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

    city_lookup = {c.lower(): c for c in US_CITIES}

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

        matched_city = city_lookup.get(city_input.lower())
        if not matched_city:
            print("\n  ❌ Requested City Data Not Avaliable")
            print("  Available cities that can be scraped:")
            for idx, c in enumerate(US_CITIES, 1):
                print(f"    {idx:3d}. {c:<22}", end="\n" if idx % 3 == 0 else "")
            print("\n")
            continue

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


def confirm_before_start(selected_cities: Any, categories: StrList, city_end: OptInt = None) -> bool:
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
    print(f"  Listings:     {START_LISTING} → {END_LISTING} per category per city")
    print(f"  Max listings: {MAX_LISTINGS} per category per city")
    print(f"  Browser:      {CHROME_CHANNEL or 'bundled Chromium'} | headless={HEADLESS}")
    print(f"  Outputs:      JSON={JSON_FILE} | CSV={CSV_FILE if EXPORT_CSV else 'off'} | XLSX={XLSX_FILE if EXPORT_XLSX else 'off'}")
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
    matches = re.findall(r'(\+?\d[\d\s\-\(\)]{8,}\d)', phone)
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
    """Validate record before saving."""
    errors = []
    if set(record.keys()) != set(EXACT_SCHEMA):
        errors.append(f"Schema mismatch: expected {len(EXACT_SCHEMA)} keys, got {len(record.keys())}")
    if not record.get("company_name"):
        errors.append("company_name is required")
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


# ════════════════════════════════════════════════════════════════
#  DEDUPLICATION
# ════════════════════════════════════════════════════════════════

class DeduplicationManager:
    """Track processed businesses to avoid duplicates across JSON and CSV."""

    def __init__(self):
        self.processed_keys: Set[str] = set()
        self.processed_urls: Set[str] = set()
        self.load_existing_records()

    def load_existing_records(self):
        """Load processed records from JSON array and CSV files (NO JSONL)."""
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, 'r', encoding='utf-8') as f:
                    records = json.load(f)
                    for record in records:
                        if record.get("id"):
                            self.processed_keys.add(record["id"])
                        if record.get("profile_url"):
                            self.processed_urls.add(record["profile_url"])
            except Exception as e:
                logger.error(f"Error loading deduplication data from JSON: {e}")

        if os.path.exists(CSV_FILE):
            try:
                with open(CSV_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for record in reader:
                        if record.get("id"):
                            self.processed_keys.add(record["id"])
                        if record.get("profile_url"):
                            self.processed_urls.add(record["profile_url"])
            except Exception as e:
                logger.error(f"Error loading deduplication data from CSV: {e}")

        if self.processed_keys or self.processed_urls:
            logger.info(f"Loaded {len(self.processed_keys)} deduplication keys from existing files")

    def is_duplicate(self, stable_id: OptStr, profile_url: OptStr) -> bool:
        """Check if business already processed."""
        if stable_id and stable_id in self.processed_keys:
            return True
        if profile_url and profile_url in self.processed_urls:
            return True
        return False

    def mark_processed(self, stable_id: OptStr, profile_url: OptStr):
        """Mark business as processed."""
        if stable_id:
            self.processed_keys.add(stable_id)
        if profile_url:
            self.processed_urls.add(profile_url)


dedup_manager = DeduplicationManager()

# ════════════════════════════════════════════════════════════════
#  ATOMIC CSV STORAGE + JSON COLLECTION
# ════════════════════════════════════════════════════════════════

def save_record_atomically(record: Dict) -> bool:
    """
    Save a single record to CSV atomically.
    JSON and XLSX are built from the collected records (checkpoints + end of run).
    """
    is_valid, errors = validate_record(record)
    if not is_valid:
        logger.error(f"Validation failed for {record.get('company_name')}: {errors}")
        return False

    try:
        if EXPORT_CSV:
            if not os.path.exists(CSV_FILE):
                with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=EXACT_SCHEMA)
                    writer.writeheader()

            with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=EXACT_SCHEMA)
                writer.writerow(record)
                f.flush()

        logger.info(f"Saved: {record.get('company_name')} ({record.get('id')})")
        return True

    except Exception as e:
        logger.error(f"Error saving record {record.get('id')}: {e}")
        return False


def create_default_record() -> Dict:
    """Create a record with all schema keys initialized to null."""
    return {key: None for key in EXACT_SCHEMA}


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


def launch_browser(pw: Playwright) -> BrowserPair:
    """
    Launch Chrome via Playwright.
    1) Try persistent context (dedicated profile dir) with installed Chrome.
    2) Fall back to a normal Chrome launch.
    3) Fall back to Playwright's bundled Chromium.
    Returns (browser_or_None, context).
    """
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
                headless=HEADLESS,
                args=args,
                **context_opts,
            )
            logger.info(f"Launched {CHROME_CHANNEL or 'Chromium'} with persistent profile: {CHROME_USER_DATA_DIR}")
            return None, context
        except Exception as profile_err:
            logger.warning(f"Could not launch persistent Chrome profile ({profile_err}). Launching standard browser...")

    try:
        browser = pw.chromium.launch(channel=CHROME_CHANNEL, headless=HEADLESS, args=args)
        logger.info(f"Launched {CHROME_CHANNEL or 'Chromium'} (non-persistent)")
    except Exception as chrome_err:
        logger.warning(f"Could not launch channel '{CHROME_CHANNEL}' ({chrome_err}). Falling back to bundled Chromium...")
        browser = pw.chromium.launch(headless=HEADLESS, args=args)

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
                val = f"{aria} {txt} {href}"
                ph = clean_phone(val)
                if ph:
                    record["phone"] = ph
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

        record["country"] = "United States"
        record["professional_category"] = category

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
#  FINAL JSON SAVE
# ════════════════════════════════════════════════════════════════

def load_existing_json() -> DictList:
    """Load the existing JSON array file, or return an empty list."""
    if not os.path.exists(JSON_FILE):
        return []
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
            if isinstance(existing, list):
                return existing
    except Exception as e:
        logger.error(f"Error loading existing JSON for merge: {e}")
    return []


def save_final_json(records: DictList) -> DictList:
    """
    Save all collected records as a JSON array file.
    Merges with existing JSON data to prevent overwriting.
    Returns the full merged list (used to build the XLSX file).
    """
    existing_records = load_existing_json()

    existing_ids = {r.get("id") for r in existing_records if r.get("id")}
    for record in records:
        if record.get("id") and record["id"] not in existing_ids:
            existing_records.append(record)
            existing_ids.add(record["id"])

    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing_records, f, indent=2, ensure_ascii=False)

    logger.info(f"Final JSON saved: {JSON_FILE} with {len(existing_records)} total records")
    return existing_records


# ════════════════════════════════════════════════════════════════
#  XLSX EXPORT
# ════════════════════════════════════════════════════════════════

def to_xlsx_value(key: str, value):
    """Convert a record value into an Excel-safe cell value."""
    if value is None or value == "":
        return None

    # Numeric columns become real numbers in Excel (sortable / filterable)
    if key in XLSX_FLOAT_COLUMNS:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    if key in XLSX_INT_COLUMNS:
        try:
            return int(str(value).replace(",", ""))
        except (TypeError, ValueError):
            pass

    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)

    text = ILLEGAL_CHARACTERS_RE.sub("", str(value))
    if len(text) > EXCEL_CELL_LIMIT:
        text = text[:EXCEL_CELL_LIMIT]
    return text


def save_xlsx(records: DictList) -> OptStr:
    """
    Write all records to an .xlsx file (one row per record, columns = EXACT_SCHEMA).
    Writes to a temp file first, then replaces the target.
    If the target is open in Excel (locked), saves to a timestamped file instead.
    Returns the path written, or None on failure.
    """
    if not EXPORT_XLSX:
        return None

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = XLSX_SHEET_NAME

        # Header row
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        for col_idx, key in enumerate(EXACT_SCHEMA, start=1):
            cell = ws.cell(row=1, column=col_idx, value=key)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Data rows
        col_widths = [len(key) for key in EXACT_SCHEMA]
        for row_idx, record in enumerate(records, start=2):
            for col_idx, key in enumerate(EXACT_SCHEMA, start=1):
                value = to_xlsx_value(key, record.get(key))
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                # Prevent text starting with "=" from being treated as a formula
                if isinstance(value, str) and value.startswith("="):
                    cell.data_type = "s"
                if value is not None:
                    col_widths[col_idx - 1] = max(col_widths[col_idx - 1], min(len(str(value)), XLSX_MAX_COL_WIDTH))

        # Column widths, frozen header, filters
        for col_idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = min(width + 2, XLSX_MAX_COL_WIDTH)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # Atomic save: temp file -> replace
        tmp_path = XLSX_FILE + ".tmp"
        wb.save(tmp_path)
        try:
            os.replace(tmp_path, XLSX_FILE)
            logger.info(f"XLSX saved: {XLSX_FILE} with {len(records)} rows")
            return XLSX_FILE
        except PermissionError:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            alt_path = f"{Path(XLSX_FILE).stem}_{stamp}.xlsx"
            os.replace(tmp_path, alt_path)
            logger.warning(f"{XLSX_FILE} is locked (open in Excel?). Saved to {alt_path} instead.")
            return alt_path

    except Exception as e:
        logger.error(f"Error saving XLSX: {e}")
        return None


def checkpoint_exports(records: DictList):
    """Write JSON (merged) and XLSX mid-run so a crash doesn't lose everything."""
    try:
        merged = save_final_json(records)
        save_xlsx(merged)
    except Exception as e:
        logger.error(f"Checkpoint export failed: {e}")


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
    """Main scraper workflow with interactive terminal input."""

    # Optional: convert existing JSON to XLSX without scraping
    #   python GoogleMaps_Allcategories.py --xlsx-only
    if "--xlsx-only" in sys.argv:
        records = load_existing_json()
        logger.info(f"--xlsx-only: converting {len(records)} records from {JSON_FILE}")
        save_xlsx(records)
        return

    # Interactive city selection (direct city and state name, not index)
    selected_cities = get_interactive_city_selection()

    # Interactive category selection
    categories = get_interactive_category_selection()

    # Show summary and get confirmation
    if not confirm_before_start(selected_cities, categories):
        print("\n  🔄 Scraping cancelled by user.")
        return

    logger.info("=" * 70)
    logger.info("Google Maps Business Data Scraper — All Categories (Playwright + Chrome)")
    logger.info("=" * 70)
    logger.info(f"Target Locations: {selected_cities if len(selected_cities) <= 3 else f'{len(selected_cities)} cities'}")
    logger.info(f"Listings per query: {START_LISTING} → {END_LISTING}")
    logger.info(f"Categories: {len(categories)} total")
    logger.info(f"Export CSV: {EXPORT_CSV}")
    logger.info("Export JSON: True")
    logger.info(f"Export XLSX: {EXPORT_XLSX} (checkpoint every {XLSX_SAVE_EVERY or 'end only'})")
    logger.info("=" * 70)

    # Collect all records for final JSON / XLSX output
    all_records = []

    with sync_playwright() as pw:
        browser, context = launch_browser(pw)
        setup_context(context)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for city_idx, city in enumerate(selected_cities, start=1):
                logger.info(f"\n🏙️  [{city_idx}/{len(selected_cities)}] Processing city: {city}")
                for category in categories:
                    query = f"{category} in {city}"
                    search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
                    logger.info(f" 🔍 Query: '{query}'")

                    try:
                        goto(page, search_url)

                        try:
                            all_links = collect_listing_urls(page)
                        except Exception as e:
                            logger.warning(f"Feed not found for {query}: {e}")
                            continue

                        sliced = all_links[START_LISTING - 1:END_LISTING]
                        logger.info(f"   📋 {len(all_links)} URLs collected, scraping {len(sliced)} listings")

                        for idx, profile_url in enumerate(sliced, start=START_LISTING):
                            if dedup_manager.is_duplicate(None, profile_url):
                                logger.info(f"   ⏭️  Listing {idx} already scraped")
                                continue

                            record = scrape_listing(page, profile_url, category)
                            if record is None:
                                continue

                            if save_record_atomically(record):
                                dedup_manager.mark_processed(record.get("id"), profile_url)
                                all_records.append(record)
                                logger.info(f"   ✅ [{idx}] {record.get('company_name')} | ⭐ {record.get('rating')}")

                                if XLSX_SAVE_EVERY and len(all_records) % XLSX_SAVE_EVERY == 0:
                                    checkpoint_exports(all_records)

                            time.sleep(1)

                    except Exception as e:
                        logger.warning(f"Error processing {query}: {e}")

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
            logger.info("Browser closed.")

            merged_records = save_final_json(all_records)
            save_xlsx(merged_records)

            logger.info("Scraping workflow completed successfully.")

class GoogleMapsScrapper(BaseScraper):
    #this class inherets the abstract class from base.py and implements the abstract function there basically allowing it to work in a modular fashion
    meta = ScraperMeta(
    #this just tell the system what kind of data the scrapper is offering
        id="googlemaps",
        name="Google maps Scrapper",
        description="This scraper collects construction and engineering business leads across 327 US cities and 38 categories, outputting deduplicated 59-field records to CSV and JSON. It takes city and state names directly, validating against the 327 supported US cities list. From Google Maps, it extracts company name, profile URL, coordinates, rating, review count, phone, website, parsed address, service tags, opening hours, and featured reviews, then crawls each company's website to gather email addresses and socials.",
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

    def scrape(self, params: "ScrapeParams") -> "Iterator[Dict[str, Any]]":
        """
        Execute Google Maps extraction yielding raw dictionary records.
        Runs Playwright, queries Google Maps for the requested keyword/category
        and location, collects listing links, and scrapes individual places.
        Validates city against US_CITIES; if unavailable, responds with
        'Requested City Data Not Avaliable' and gives the list of available cities.
        """
        global HEADLESS
        original_headless = HEADLESS
        if hasattr(self, "headless") and self.headless is not None:
            HEADLESS = self.headless

        limit = getattr(params, "limit", None) or getattr(self.meta, "default_limit", 25)

        # 1. Resolve search categories/keywords
        if getattr(params, "keyword", None) and str(params.keyword).strip():
            categories = [str(params.keyword).strip()]
        else:
            categories = BUSINESS_CATEGORIES

        # 2. Resolve & validate target city and state directly
        city = getattr(params, "city", None)
        us_state = getattr(params, "us_state", None)
        location = getattr(params, "location", None)

        candidate_city = None
        if city and str(city).strip():
            candidate_city = str(city).strip()
        elif location and str(location).strip():
            loc_str = str(location).strip()
            candidate_city = loc_str.split(",")[0].strip() if "," in loc_str else loc_str

        city_lookup = {c.lower(): c for c in US_CITIES}

        if candidate_city:
            matched_city = city_lookup.get(candidate_city.lower())
            if not matched_city:
                available_cities_str = ", ".join(US_CITIES)
                err_msg = (
                    f"Requested City Data Not Avaliable: '{candidate_city}'. "
                    f"Available cities that can be scraped ({len(US_CITIES)} total): {available_cities_str}"
                )
                if hasattr(self, "ctx") and self.ctx:
                    self.ctx.log("error", err_msg)
                    self.ctx.progress(0.0, "Requested City Data Not Avaliable")
                raise InvalidScrapeParams(err_msg)

            # Valid matched city from US_CITIES!
            if us_state and str(us_state).strip():
                target_locations = [f"{matched_city}, {str(us_state).strip()}"]
            elif location and "," in str(location):
                state_part = str(location).split(",", 1)[1].strip()
                target_locations = [f"{matched_city}, {state_part}"] if state_part else [matched_city]
            else:
                target_locations = [matched_city]
        elif us_state and str(us_state).strip():
            target_locations = [f"{str(us_state).strip()}, USA"]
        else:
            target_locations = US_CITIES

        yielded = 0
        seen_urls: Set[str] = set()

        with sync_playwright() as pw:
            browser, context = launch_browser(pw)
            setup_context(context)
            page = context.pages[0] if context.pages else context.new_page()

            try:
                for loc in target_locations:
                    if yielded >= limit:
                        break

                    for cat in categories:
                        if yielded >= limit:
                            break

                        self.check_cancel()

                        query = f"{cat} in {loc}"
                        search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
                        logger.info(f"🔍 Google Maps Query: '{query}'")

                        try:
                            goto(page, search_url)

                            try:
                                all_links = collect_listing_urls(page)
                            except Exception as e:
                                logger.warning(f"Feed not found for '{query}': {e}")
                                continue

                            for profile_url in all_links:
                                if yielded >= limit:
                                    break

                                self.check_cancel()

                                if profile_url in seen_urls:
                                    continue
                                seen_urls.add(profile_url)

                                record = scrape_listing(page, profile_url, cat)
                                if record is None:
                                    continue

                                yielded += 1
                                if hasattr(self, "ctx") and self.ctx:
                                    pct = min(99.0, (yielded / limit) * 100.0)
                                    self.ctx.progress(pct, f"Scraped {yielded}/{limit}: {record.get('company_name') or profile_url}")

                                yield record
                                time.sleep(0.5)

                        except Exception as e:
                            logger.warning(f"Error querying Google Maps for '{query}': {e}")

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
                HEADLESS = original_headless

    # def to_standard(self, raw: Dict[str, Any]) -> "StandardRecord":
    #     """Transform a raw Google Maps dictionary into a canonical StandardRecord."""
    #     from scrappers.utils import to_json_safe, state_code
    #     company_name = raw.get("company_name") or raw.get("name") or "Unknown Business"
    #     profile_url = raw.get("profile_url") or raw.get("url")
    #     raw_state = raw.get("state")
    #     us_state = state_code(raw_state) if raw_state else raw_state

    #     return StandardRecord(
    #         source_code=self.meta.id,
    #         record_kind=self.meta.record_kind,
    #         external_id=raw.get("id") or profile_url or company_name,
    #         source_url=profile_url or raw.get("website"),
    #         title=None,
    #         description=raw.get("description"),
    #         organization_name=company_name,
    #         contact_name=None,
    #         contact_title=None,
    #         email=raw.get("email"),
    #         phone=raw.get("phone"),
    #         website=raw.get("website"),
    #         city=raw.get("city"),
    #         us_state=us_state,
    #         postal_code=raw.get("zip"),
    #         category=raw.get("professional_category"),
    #         due_at=None,
    #         extra=to_json_safe({
    #             "rating": raw.get("rating"),
    #             "reviews_count": raw.get("reviews_count"),
    #             "latitude": raw.get("latitude"),
    #             "longitude": raw.get("longitude"),
    #             "address": raw.get("address"),
    #             "services_offered": raw.get("services_offered"),
    #             "specialties": raw.get("specialties"),
    #             "featured_review_text": raw.get("featured_review_text"),
    #             "facebook": raw.get("facebook"),
    #             "instagram": raw.get("instagram"),
    #             "linkedin": raw.get("linkedin"),
    #             "twitter": raw.get("twitter"),
    #             "pinterest": raw.get("pinterest"),
    #             "youtube": raw.get("youtube"),
    #             "scraped_at": raw.get("scraped_at"),
    #         }),
    #     )
    

if __name__ == "__main__":
    main()