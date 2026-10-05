#!/usr/bin/env python3

"""
JWiz Production Scraper
=======================

IMPORTANT EXTRACTION RULES
---------------------------

1. Company Name MUST come from the JWiz search-result card.
2. Profile page MUST NEVER overwrite Company Name.
3. "Connecting Businesses To The Jewish Community Since 1989"
   is JWiz's site slogan and is NEVER a company name.
4. "Featured" is UI and is NEVER company data.
5. "Write a Review" is UI and is NEVER company data.
6. City is extracted from the location line only.
7. Street address is NEVER stored as City.
8. Site-wide JWiz social accounts are NEVER stored as company socials.
9. Missing data = "Not Found".
10. No guessing.
11. No Contact Person.
12. No Contact Title.
13. No CSI/MasterFormat Division.

FINAL CSV COLUMNS
-----------------
Company Name
City
State
Email
Phone
LinkedIn/Social
Residential/Commercial/Both
Lead Priority
Profile URL
"""

from __future__ import annotations

import csv
import logging
import math
import re
import sys
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Iterator
from scrappers.base import BaseScraper, ScrapeParams, RawRecord

# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://jwiz.com"

SEARCH_URL_TEMPLATE = (
    BASE_URL + "/search/{location}/{keyword}"
)

RESULTS_PER_PAGE = 100

REQUEST_TIMEOUT = 30

SEARCH_DELAY = 1.0
PROFILE_DELAY = 1.0

MAX_RETRIES = 3

MASTER_FILE = Path("master_leads.csv")

LOG_DIR = Path("logs")

NOT_FOUND = "Not Found"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


# ============================================================
# FINAL OUTPUT SCHEMA
# ============================================================

OUTPUT_FIELDS = [
    "Company Name",
    "City",
    "State",
    "Email",
    "Phone",
    "LinkedIn/Social",
    "Residential/Commercial/Both",
    "Lead Priority",
    "Profile URL",
]


# ============================================================
# JWIZ SITE-WIDE SOCIAL LINKS
# ============================================================
#
# These were contaminating the CSV.
#
# They are JWiz promotional/site-level accounts and must NEVER
# be treated as the business's own social media.
# ============================================================

BLOCKED_SOCIAL_URLS = {
    "https://www.facebook.com/JewishMarketingSolutionsDAG",
    "https://twitter.com/jewish_yp",
}


BLOCKED_SOCIAL_KEYS = {
    "jewishmarketingsolutionsdag",
    "jewish_yp",
}


# ============================================================
# STATES
# ============================================================

STATES = [
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
]


STATE_CODES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


STATE_LOOKUP = {
    state.lower(): state
    for state in STATES
}


# ============================================================
# CATEGORY
# ============================================================

@dataclass(frozen=True)
class Category:
    number: int
    name: str
    market: str
    keywords: Tuple[str, ...]


CATEGORIES = [
    Category(
        1,
        "General Contractor",
        "Both",
        (
            "General Contracting",
            "General Contractor",
            "Contractor",
        ),
    ),

    Category(
        2,
        "Roofing Contractor",
        "Both",
        (
            "Roofing",
            "Roofing Contractor",
        ),
    ),

    Category(
        3,
        "Concrete Contractor",
        "Both",
        (
            "Concrete",
            "Concrete Contractor",
        ),
    ),

    Category(
        4,
        "HVAC Contractor",
        "Both",
        (
            "HVAC",
            "HVAC Contractor",
        ),
    ),

    Category(
        5,
        "Electrical Contractor",
        "Both",
        (
            "Electrical Contractor",
            "Electrician",
        ),
    ),

    Category(
        6,
        "Plumbing Contractor",
        "Both",
        (
            "Plumbing",
            "Plumbing Contractor",
        ),
    ),

    Category(
        7,
        "Masonry Contractor",
        "Both",
        (
            "Masonry",
            "Masonry Contractor",
        ),
    ),

    Category(
        8,
        "Framing Contractor",
        "Residential",
        (
            "Framing",
            "Framing Contractor",
        ),
    ),

    Category(
        9,
        "Siding Contractor",
        "Residential",
        (
            "Siding",
            "Siding Contractor",
        ),
    ),

    Category(
        10,
        "Excavation Contractor",
        "Both",
        (
            "Excavation",
            "Excavation Contractor",
        ),
    ),

    Category(
        11,
        "Structural Steel",
        "Commercial",
        (
            "Structural Steel",
            "Steel Fabrication",
        ),
    ),

    Category(
        12,
        "Kitchen Remodeling",
        "Residential",
        (
            "Kitchen Remodeling",
            "Kitchen Remodel",
        ),
    ),

    Category(
        13,
        "Bathroom Remodeling",
        "Residential",
        (
            "Bathroom Remodeling",
            "Bathroom Remodel",
        ),
    ),

    Category(
        14,
        "Basement Remodeling",
        "Residential",
        (
            "Basement Remodeling",
            "Basement Finishing",
        ),
    ),

    Category(
        15,
        "Flooring Contractor",
        "Both",
        (
            "Flooring",
            "Flooring Contractor",
        ),
    ),

    Category(
        16,
        "Painting Contractor",
        "Both",
        (
            "Painting",
            "Painting Contractor",
        ),
    ),

    Category(
        17,
        "Drywall Contractor",
        "Both",
        (
            "Drywall",
            "Drywall Contractor",
        ),
    ),

    Category(
        18,
        "Window & Door Installation",
        "Both",
        (
            "Window Installation",
            "Door Installation",
        ),
    ),

    Category(
        19,
        "Fire Protection",
        "Commercial",
        (
            "Fire Protection",
            "Sprinkler Contractor",
        ),
    ),

    Category(
        20,
        "Landscaping",
        "Residential",
        (
            "Landscaping",
            "Landscape Contractor",
        ),
    ),

    Category(
        21,
        "Home Improvement",
        "Residential",
        (
            "Home Improvement",
            "Home Improvement Contractor",
        ),
    ),

    Category(
        22,
        "Renovation",
        "Both",
        (
            "Renovation",
            "Renovation Contractor",
        ),
    ),

    Category(
        23,
        "Deck & Patio",
        "Residential",
        (
            "Deck",
            "Patio",
        ),
    ),

    Category(
        24,
        "Insulation",
        "Both",
        (
            "Insulation",
            "Insulation Contractor",
        ),
    ),
]


# ============================================================
# DATA OBJECT
# ============================================================

@dataclass
class Lead:

    company_name: str = ""

    city: str = ""

    state: str = ""

    email: str = ""

    phone: str = ""

    social: List[str] = field(
        default_factory=list
    )

    profile_url: str = ""

    source_url: str = ""

    source_category: str = ""

    source_keyword: str = ""

    source_location: str = ""


# ============================================================
# HTTP CLIENT
# ============================================================

class HTTPClient:

    def __init__(self):

        self.session = requests.Session()

        retry = Retry(
            total=MAX_RETRIES,
            connect=MAX_RETRIES,
            read=MAX_RETRIES,
            status=MAX_RETRIES,
            backoff_factor=1.5,
            status_forcelist=(
                429,
                500,
                502,
                503,
                504,
            ),
            allowed_methods=frozenset(
                ["GET"]
            ),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=10,
            pool_maxsize=10,
        )

        self.session.mount(
            "https://",
            adapter,
        )

        self.session.mount(
            "http://",
            adapter,
        )

        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/xml;q=0.9,"
                    "*/*;q=0.8"
                ),
                "Accept-Language":
                    "en-US,en;q=0.9",
            }
        )

    def get(
        self,
        url: str,
    ) -> Optional[requests.Response]:

        try:

            response = self.session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            if response.status_code >= 400:

                logging.error(
                    "HTTP %s | %s",
                    response.status_code,
                    url,
                )

                return None

            return response

        except requests.RequestException as exc:

            logging.error(
                "REQUEST ERROR | %s | %s",
                url,
                exc,
            )

            return None

    def close(self):

        self.session.close()


# ============================================================
# NORMALIZATION
# ============================================================

def clean_text(value) -> str:

    if value is None:
        return ""

    value = str(value)

    value = value.replace(
        "\xa0",
        " ",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_key(value: str) -> str:

    value = clean_text(value).lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def normalize_phone(value: str) -> str:

    digits = re.sub(
        r"\D",
        "",
        value or "",
    )

    if (
        len(digits) == 11
        and digits.startswith("1")
    ):
        digits = digits[1:]

    return digits


def normalize_url(value: str) -> str:

    value = clean_text(value)

    if not value:
        return ""

    parsed = urlparse(value)

    if not parsed.scheme:
        return value.rstrip("/").lower()

    return (
        f"{parsed.scheme.lower()}://"
        f"{parsed.netloc.lower()}"
        f"{parsed.path.rstrip('/')}"
    )


# ============================================================
# SEARCH URL
# ============================================================

def build_search_url(
    location: str,
    keyword: str,
    offset: int = 0,
) -> str:

    url = SEARCH_URL_TEMPLATE.format(
        location=quote_plus(location),
        keyword=quote_plus(keyword),
    )

    if offset:
        url += f"/{offset}"

    return url


# ============================================================
# RESULT COUNT
# ============================================================

def get_result_count(
    soup: BeautifulSoup,
) -> Optional[int]:

    text = clean_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    patterns = [
        r"Showing\s+\d+\s*-\s*\d+\s+of\s+([\d,]+)\s+results?",
        r"Showing\s+\d+\s+of\s+([\d,]+)\s+results?",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:

            try:
                return int(
                    match.group(1).replace(
                        ",",
                        "",
                    )
                )

            except ValueError:
                pass

    return None


# ============================================================
# RESULT CARD DISCOVERY
# ============================================================

def find_result_cards(
    soup: BeautifulSoup,
) -> List[Tag]:

    selectors = [
        "ul.list-group > li.list-group-item",
        "li.list-group-item",
    ]

    for selector in selectors:

        cards = soup.select(
            selector
        )

        if cards:
            return cards

    return []


# ============================================================
# COMPANY NAME
# ============================================================

def extract_company_name(
    card: Tag,
) -> str:

    """
    CRITICAL:

    Company Name comes ONLY from the result card.

    We intentionally do NOT use:

        soup.h1
        soup.h2
        page title
        profile page heading
        meta title
        site slogan

    because JWiz profile/search pages contain:

        Connecting Businesses To The Jewish Community Since 1989

    which is the site slogan, NOT the business.
    """

    for link in card.find_all(
        "a",
        href=True,
    ):

        href = clean_text(
            link.get("href", "")
        )

        text = clean_text(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        if "/jewish/" not in href:
            continue

        # Ignore obvious UI.
        if is_ui_text(text):
            continue

        # Ignore slogan even if it somehow appears as a link.
        if is_jwiz_slogan(text):
            continue

        return text

    return ""


def is_jwiz_slogan(
    value: str,
) -> bool:

    return normalize_key(value) == normalize_key(
        "Connecting Businesses To The Jewish Community Since 1989"
    )


def is_ui_text(
    value: str,
) -> bool:

    normalized = normalize_key(
        value
    )

    blocked = {
        "featured",
        "write a review",
        "view ad",
        "view business card",
        "view coupon",
        "website",
        "email",
        "facebook",
        "instagram",
        "youtube",
        "twitter",
        "linkedin",
        "tiktok",
    }

    return normalized in blocked


# ============================================================
# PROFILE URL
# ============================================================

def extract_profile_url(
    card: Tag,
) -> str:

    for link in card.find_all(
        "a",
        href=True,
    ):

        href = clean_text(
            link.get("href", "")
        )

        if "/jewish/" in href:

            return urljoin(
                BASE_URL,
                href,
            )

    return ""


# ============================================================
# LOCATION
# ============================================================

def extract_location_line(
    card: Tag,
) -> str:

    """
    Search the card's individual text lines.

    We want something ending in:

        CITY, ST ZIP
    or
        STREET, CITY, ST ZIP
    or
        ST ZIP

    We DO NOT use arbitrary surrounding description text.
    """

    text = card.get_text(
        "\n",
        strip=True,
    )

    lines = []

    for line in text.splitlines():

        line = clean_text(line)

        if not line:
            continue

        if is_ui_text(line):
            continue

        lines.append(line)

    # Search from top to bottom.
    for line in lines:

        if looks_like_us_location(
            line
        ):
            return line

    return ""


def looks_like_us_location(
    value: str,
) -> bool:

    value = clean_text(value)

    # ZIP-based location.
    if re.search(
        r"\b\d{5}(?:-\d{4})?\b$",
        value,
    ):

        # State abbreviation immediately before ZIP.
        if re.search(
            r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?$",
            value,
            re.IGNORECASE,
        ):
            return True

        # Full state name before ZIP.
        state_pattern = "|".join(
            re.escape(x)
            for x in STATES
        )

        if re.search(
            rf"\b(?:{state_pattern})\s+\d{{5}}(?:-\d{{4}})?$",
            value,
            re.IGNORECASE,
        ):
            return True

    return False


# ============================================================
# CITY / STATE
# ============================================================

def extract_city_state(
    location: str,
) -> Tuple[str, str]:

    location = clean_text(
        location
    )

    if not location:
        return "", ""

    # --------------------------------------------------------
    # STATE ABBREVIATION
    # --------------------------------------------------------

    match = re.search(
        r"(?P<prefix>.*?)"
        r"(?:,\s*|\s+)"
        r"(?P<state>[A-Z]{2})"
        r"\s+"
        r"\d{5}(?:-\d{4})?"
        r"$",
        location,
        re.IGNORECASE,
    )

    if match:

        state_code = (
            match.group("state")
            .upper()
        )

        state = STATE_CODES.get(
            state_code,
            "",
        )

        prefix = clean_text(
            match.group("prefix")
        )

        city = extract_city(
            prefix
        )

        return city, state

    # --------------------------------------------------------
    # FULL STATE NAME
    # --------------------------------------------------------

    state_pattern = "|".join(
        re.escape(x)
        for x in sorted(
            STATES,
            key=len,
            reverse=True,
        )
    )

    match = re.search(
        rf"(?P<prefix>.*?)"
        rf"(?:,\s*|\s+)"
        rf"(?P<state>{state_pattern})"
        rf"\s+\d{{5}}(?:-\d{{4}})?"
        rf"$",
        location,
        re.IGNORECASE,
    )

    if match:

        state = STATE_LOOKUP.get(
            match.group("state").lower(),
            "",
        )

        prefix = clean_text(
            match.group("prefix")
        )

        city = extract_city(
            prefix
        )

        return city, state

    return "", ""


def extract_city(
    prefix: str,
) -> str:

    prefix = clean_text(
        prefix
    )

    if not prefix:
        return ""

    parts = [
        clean_text(x)
        for x in prefix.split(",")
        if clean_text(x)
    ]

    if not parts:
        return ""

    # The final comma-separated part before the state
    # is the city when a full address is present.
    candidate = parts[-1]

    # Remove suite/unit information.
    candidate = re.sub(
        r"\b(?:Suite|Ste|Unit|Floor|Fl|#)\s*[\w-]+\b",
        "",
        candidate,
        flags=re.IGNORECASE,
    )

    candidate = clean_text(
        candidate
    )

    if not candidate:
        return ""

    # A street itself is NOT a city.
    street_terms = (
        r"\bStreet\b",
        r"\bSt\.?\b",
        r"\bAvenue\b",
        r"\bAve\.?\b",
        r"\bRoad\b",
        r"\bRd\.?\b",
        r"\bBoulevard\b",
        r"\bBlvd\.?\b",
        r"\bDrive\b",
        r"\bDr\.?\b",
        r"\bLane\b",
        r"\bLn\.?\b",
        r"\bHighway\b",
        r"\bHwy\.?\b",
        r"\bParkway\b",
        r"\bPkwy\.?\b",
        r"\bCourt\b",
        r"\bCt\.?\b",
    )

    for pattern in street_terms:

        if re.search(
            pattern,
            candidate,
            re.IGNORECASE,
        ):
            return ""

    if re.fullmatch(
        r"P\.?\s*O\.?\s+Box\s+\d+",
        candidate,
        re.IGNORECASE,
    ):
        return ""

    return candidate


# ============================================================
# PHONE
# ============================================================

def extract_phone(
    card: Tag,
) -> str:

    # First preference: tel link.
    for link in card.select(
        'a[href^="tel:"]'
    ):

        value = clean_text(
            link.get(
                "href",
                "",
            )
        )

        phone = value[4:].strip()

        if normalize_phone(phone):
            return phone

    # Fallback.
    text = card.get_text(
        " ",
        strip=True,
    )

    match = re.search(
        r"(?<!\d)"
        r"(?:\+?1[\s.-]?)?"
        r"\(?\d{3}\)?"
        r"[\s.-]\d{3}"
        r"[\s.-]\d{4}"
        r"(?!\d)",
        text,
    )

    if match:
        return clean_text(
            match.group(0)
        )

    return ""


# ============================================================
# EMAIL
# ============================================================

def extract_email(
    card: Tag,
) -> str:

    for link in card.select(
        'a[href^="mailto:"]'
    ):

        href = clean_text(
            link.get(
                "href",
                "",
            )
        )

        email = (
            href[7:]
            .split("?", 1)[0]
            .strip()
        )

        if is_valid_email(email):
            return email.lower()

    text = card.get_text(
        " ",
        strip=True,
    )

    match = re.search(
        r"\b[A-Z0-9._%+-]+"
        r"@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(0).lower()

    return ""


def is_valid_email(
    value: str,
) -> bool:

    return bool(
        re.fullmatch(
            r"[A-Z0-9._%+-]+"
            r"@[A-Z0-9.-]+\.[A-Z]{2,}",
            value,
            re.IGNORECASE,
        )
    )


# ============================================================
# SOCIAL
# ============================================================

SOCIAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
)


def extract_social(
    card: Tag,
) -> List[str]:

    results = []

    for link in card.find_all(
        "a",
        href=True,
    ):

        href = clean_text(
            link.get(
                "href",
                "",
            )
        )

        if not href:
            continue

        lower = href.lower()

        if not any(
            domain in lower
            for domain in SOCIAL_DOMAINS
        ):
            continue

        normalized = normalize_url(
            href
        )

        if not normalized:
            continue

        if is_blocked_social(
            normalized
        ):
            continue

        results.append(
            normalized
        )

    # Unique while preserving order.
    output = []

    seen = set()

    for url in results:

        if url in seen:
            continue

        seen.add(url)

        output.append(url)

    return output


def is_blocked_social(
    url: str,
) -> bool:

    normalized = normalize_url(
        url
    )

    if normalized in BLOCKED_SOCIAL_URLS:
        return True

    key = normalize_key(
        normalized
    )

    for blocked in BLOCKED_SOCIAL_KEYS:

        if blocked in key:
            return True

    return False


# ============================================================
# PROFILE ENRICHMENT
# ============================================================

def enrich_profile(
    client: HTTPClient,
    lead: Lead,
) -> None:

    """
    PROFILE PAGE IS ENRICHMENT ONLY.

    NEVER update:

        lead.company_name

    from the profile page.

    This is the critical fix for the previous blunder.
    """

    if not lead.profile_url:
        return

    time.sleep(
        PROFILE_DELAY
    )

    response = client.get(
        lead.profile_url
    )

    if response is None:
        return

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # --------------------------------------------------------
    # EMAIL
    # --------------------------------------------------------

    profile_email = extract_profile_email(
        soup
    )

    if profile_email:
        lead.email = profile_email

    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------

    profile_phone = extract_profile_phone(
        soup
    )

    if profile_phone:
        lead.phone = profile_phone

    # --------------------------------------------------------
    # SOCIAL
    # --------------------------------------------------------

    profile_social = extract_profile_social(
        soup
    )

    if profile_social:

        merged = (
            lead.social
            + profile_social
        )

        lead.social = unique_urls(
            merged
        )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # NO COMPANY NAME EXTRACTION HERE.
    #
    # NO H1.
    # NO H2.
    # NO PAGE TITLE.
    #
    # Company Name was already captured from the search card.
    # --------------------------------------------------------


def extract_profile_email(
    soup: BeautifulSoup,
) -> str:

    for link in soup.select(
        'a[href^="mailto:"]'
    ):

        href = clean_text(
            link.get(
                "href",
                "",
            )
        )

        email = (
            href[7:]
            .split("?", 1)[0]
            .strip()
        )

        if is_valid_email(email):
            return email.lower()

    return ""


def extract_profile_phone(
    soup: BeautifulSoup,
) -> str:

    for link in soup.select(
        'a[href^="tel:"]'
    ):

        href = clean_text(
            link.get(
                "href",
                "",
            )
        )

        phone = href[4:].strip()

        if normalize_phone(phone):
            return phone

    return ""


def extract_profile_social(
    soup: BeautifulSoup,
) -> List[str]:

    results = []

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = clean_text(
            link.get(
                "href",
                "",
            )
        )

        if not href:
            continue

        if not any(
            domain in href.lower()
            for domain in SOCIAL_DOMAINS
        ):
            continue

        normalized = normalize_url(
            href
        )

        if not normalized:
            continue

        if is_blocked_social(
            normalized
        ):
            continue

        results.append(
            normalized
        )

    return unique_urls(
        results
    )


# ============================================================
# URL HELPERS
# ============================================================

def unique_urls(
    values: List[str],
) -> List[str]:

    output = []

    seen = set()

    for value in values:

        value = normalize_url(
            value
        )

        if not value:
            continue

        if is_blocked_social(
            value
        ):
            continue

        if value in seen:
            continue

        seen.add(value)

        output.append(value)

    return output


# ============================================================
# VALIDATION
# ============================================================

def validate_company_name(
    name: str,
) -> bool:

    name = clean_text(
        name
    )

    if not name:
        return False

    if is_jwiz_slogan(
        name
    ):
        return False

    if is_ui_text(
        name
    ):
        return False

    # Company names should not contain obvious card UI.
    forbidden = (
        "write a review",
        "view business card",
        "view ad",
        "featured",
    )

    normalized = normalize_key(
        name
    )

    for word in forbidden:

        if normalize_key(word) in normalized:
            return False

    return True


def validate_lead(
    lead: Lead,
) -> bool:

    if not validate_company_name(
        lead.company_name
    ):
        return False

    if not lead.state:
        return False

    if not lead.city:
        lead.city = NOT_FOUND

    if not lead.email:
        lead.email = NOT_FOUND

    if not lead.phone:
        lead.phone = NOT_FOUND

    if not lead.social:
        lead.social = []

    if not lead.profile_url:
        lead.profile_url = NOT_FOUND

    return True


# ============================================================
# MARKET CLASSIFICATION
# ============================================================

def classify_market(
    category: Category,
) -> str:

    return category.market


# ============================================================
# PRIORITY
# ============================================================

def calculate_priority(
    lead: Lead,
) -> str:

    score = 0

    if lead.email != NOT_FOUND:
        score += 2

    if lead.phone != NOT_FOUND:
        score += 2

    if lead.city != NOT_FOUND:
        score += 1

    if lead.profile_url != NOT_FOUND:
        score += 1

    if score >= 5:
        return "High"

    if score >= 3:
        return "Medium"

    return "Low"


# ============================================================
# OUTPUT
# ============================================================

def lead_to_record(
    lead: Lead,
    category: Category,
) -> dict:

    return {
        "Company Name":
            lead.company_name or NOT_FOUND,

        "City":
            lead.city or NOT_FOUND,

        "State":
            lead.state or NOT_FOUND,

        "Email":
            lead.email or NOT_FOUND,

        "Phone":
            lead.phone or NOT_FOUND,

        "LinkedIn/Social":
            " | ".join(
                unique_urls(
                    lead.social
                )
            )
            or NOT_FOUND,

        "Residential/Commercial/Both":
            classify_market(
                category
            ),

        "Lead Priority":
            calculate_priority(
                lead
            ),

        "Profile URL":
            lead.profile_url or NOT_FOUND,
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def make_profile_key(
    url: str,
) -> str:

    url = normalize_url(
        url
    )

    if not url:
        return ""

    return f"profile::{url}"


def make_fallback_key(
    company: str,
    phone: str,
) -> str:

    company = normalize_key(
        company
    )

    phone = normalize_phone(
        phone
    )

    if not company:
        return ""

    if phone:
        return (
            f"name_phone::{company}::{phone}"
        )

    return (
        f"name::{company}"
    )


class MasterStore:

    def __init__(
        self,
        path: Path,
    ):

        self.path = path

        self.profile_keys = set()

        self.fallback_keys = set()

        self.create_file()

        self.load()


    def create_file(self):

        if self.path.exists():
            return

        with self.path.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=OUTPUT_FIELDS,
            )

            writer.writeheader()


    def load(self):

        if not self.path.exists():
            return

        with self.path.open(
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            reader = csv.DictReader(
                file
            )

            for row in reader:

                profile = row.get(
                    "Profile URL",
                    "",
                )

                if profile:
                    key = make_profile_key(
                        profile
                    )

                    if key:
                        self.profile_keys.add(
                            key
                        )

                fallback = make_fallback_key(
                    row.get(
                        "Company Name",
                        "",
                    ),
                    row.get(
                        "Phone",
                        "",
                    ),
                )

                if fallback:
                    self.fallback_keys.add(
                        fallback
                    )


    def exists(
        self,
        lead: Lead,
    ) -> bool:

        if lead.profile_url:

            key = make_profile_key(
                lead.profile_url
            )

            if key in self.profile_keys:
                return True

        fallback = make_fallback_key(
            lead.company_name,
            lead.phone,
        )

        if fallback in self.fallback_keys:
            return True

        return False


    def append(
        self,
        records: List[dict],
    ):

        if not records:
            return

        with self.path.open(
            "a",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=OUTPUT_FIELDS,
            )

            for record in records:
                writer.writerow(record)

        for record in records:

            profile = record.get(
                "Profile URL",
                "",
            )

            if profile:
                key = make_profile_key(
                    profile
                )

                if key:
                    self.profile_keys.add(
                        key
                    )

            fallback = make_fallback_key(
                record.get(
                    "Company Name",
                    "",
                ),
                record.get(
                    "Phone",
                    "",
                ),
            )

            if fallback:
                self.fallback_keys.add(
                    fallback
                )


# ============================================================
# SCRAPER
# ============================================================

class JWizScraper:

    def __init__(
        self,
        client: HTTPClient,
        store: MasterStore,
        target: int,
        locations: List[str],
        categories: List[Category],
    ):

        self.client = client

        self.store = store

        self.target = target

        self.locations = locations

        self.categories = categories

        self.records = []

        self.seen_profiles = set()

        self.seen_fallback = set()

        self.raw_results = 0

        self.duplicates = 0

        self.rejected = 0

        self.pages = 0

        self.profile_pages = 0


    def target_reached(self):

        return (
            len(self.records)
            >= self.target
        )


    def run(self):

        for location in self.locations:

            if self.target_reached():
                break

            for category in self.categories:

                if self.target_reached():
                    break

                for keyword in category.keywords:

                    if self.target_reached():
                        break

                    self.scrape_search(
                        location,
                        category,
                        keyword,
                    )


    def scrape_search(
        self,
        location: str,
        category: Category,
        keyword: str,
    ):

        offset = 0

        url = build_search_url(
            location,
            keyword,
            offset,
        )

        response = self.client.get(
            url
        )

        if response is None:
            return

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        total = get_result_count(
            soup
        )

        if total is None:
            total_pages = 1
        else:
            total_pages = max(
                1,
                math.ceil(
                    total
                    / RESULTS_PER_PAGE
                ),
            )

        self.process_page(
            soup,
            location,
            category,
            keyword,
            offset,
            url,
        )

        if self.target_reached():
            return

        for page in range(
            1,
            total_pages,
        ):

            if self.target_reached():
                return

            time.sleep(
                SEARCH_DELAY
            )

            offset = (
                page
                * RESULTS_PER_PAGE
            )

            url = build_search_url(
                location,
                keyword,
                offset,
            )

            response = self.client.get(
                url
            )

            if response is None:
                continue

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            self.process_page(
                soup,
                location,
                category,
                keyword,
                offset,
                url,
            )


    def process_page(
        self,
        soup: BeautifulSoup,
        location: str,
        category: Category,
        keyword: str,
        offset: int,
        source_url: str,
    ):

        cards = find_result_cards(
            soup
        )

        self.pages += 1

        self.raw_results += len(
            cards
        )

        logging.info(
            "PAGE | location=%s | "
            "keyword=%s | offset=%s | "
            "cards=%s",
            location,
            keyword,
            offset,
            len(cards),
        )

        for card in cards:

            if self.target_reached():
                return

            lead = self.parse_card(
                card,
                location,
                category,
                keyword,
                source_url,
            )

            if lead is None:
                continue

            self.process_lead(
                lead,
                category,
            )


    def parse_card(
        self,
        card: Tag,
        location: str,
        category: Category,
        keyword: str,
        source_url: str,
    ) -> Optional[Lead]:

        # ========================================================
        # COMPANY NAME
        # ========================================================

        company = extract_company_name(
            card
        )

        if not company:

            self.rejected += 1

            logging.warning(
                "REJECTED | "
                "No company name | %s",
                source_url,
            )

            return None

        # ========================================================
        # LOCATION
        # ========================================================

        location_line = (
            extract_location_line(
                card
            )
        )

        city, state = (
            extract_city_state(
                location_line
            )
        )

        # ========================================================
        # PHONE
        # ========================================================

        phone = extract_phone(
            card
        )

        # ========================================================
        # EMAIL
        # ========================================================

        email = extract_email(
            card
        )

        # ========================================================
        # SOCIAL
        # ========================================================

        social = extract_social(
            card
        )

        # ========================================================
        # PROFILE
        # ========================================================

        profile_url = (
            extract_profile_url(
                card
            )
        )

        return Lead(
            company_name=company,
            city=city,
            state=state,
            email=email,
            phone=phone,
            social=social,
            profile_url=profile_url,
            source_url=source_url,
            source_category=category.name,
            source_keyword=keyword,
            source_location=location,
        )


    def process_lead(
        self,
        lead: Lead,
        category: Category,
    ):

        # ========================================================
        # VALIDATE BEFORE PROFILE
        # ========================================================

        if not validate_lead(
            lead
        ):
            self.rejected += 1
            return

        # ========================================================
        # CURRENT RUN DUPLICATE
        # ========================================================

        if lead.profile_url:

            profile_key = (
                make_profile_key(
                    lead.profile_url
                )
            )

            if profile_key in (
                self.seen_profiles
            ):

                self.duplicates += 1
                return

        fallback_key = (
            make_fallback_key(
                lead.company_name,
                lead.phone,
            )
        )

        if (
            fallback_key
            and fallback_key in (
                self.seen_fallback
            )
        ):

            self.duplicates += 1
            return

        # ========================================================
        # MASTER FILE DUPLICATE
        # ========================================================

        if self.store.exists(
            lead
        ):

            self.duplicates += 1
            return

        # ========================================================
        # MARK SEEN
        # ========================================================

        if lead.profile_url:

            profile_key = (
                make_profile_key(
                    lead.profile_url
                )
            )

            if profile_key:
                self.seen_profiles.add(
                    profile_key
                )

        if fallback_key:
            self.seen_fallback.add(
                fallback_key
            )

        # ========================================================
        # PROFILE ENRICHMENT
        # ========================================================
        #
        # IMPORTANT:
        #
        # This function is NOT allowed to modify company_name.
        #
        # It may enrich email/phone/social only.
        # ========================================================

        if lead.profile_url:

            self.profile_pages += 1

            enrich_profile(
                self.client,
                lead,
            )

        # ========================================================
        # FINAL VALIDATION
        # ========================================================

        if not validate_lead(
            lead
        ):
            self.rejected += 1
            return

        # ========================================================
        # OUTPUT
        # ========================================================

        record = lead_to_record(
            lead,
            category,
        )

        self.records.append(
            record
        )

        logging.info(
            "NEW LEAD %s/%s | %s | %s | %s",
            len(self.records),
            self.target,
            record["Company Name"],
            record["City"],
            record["State"],
        )


# ============================================================
# LOGGING
# ============================================================

def setup_logging():

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = (
        LOG_DIR
        / "jwiz_scraper.log"
    )

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(
                log_file,
                encoding="utf-8",
            ),
            logging.StreamHandler(
                sys.stdout
            ),
        ],
    )


# ============================================================
# CSV RUN OUTPUT
# ============================================================

def write_run_file(
    records: List[dict],
) -> Optional[Path]:

    if not records:
        return None

    path = (
        LOG_DIR
        / (
            "run_"
            f"{time.strftime('%Y%m%d_%H%M%S')}.csv"
        )
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=OUTPUT_FIELDS,
        )

        writer.writeheader()

        writer.writerows(
            records
        )

    return path


# ============================================================
# CLI
# ============================================================

def choose_target() -> int:

    print()
    print("1. 100 leads")
    print("2. 250 leads")
    print("3. 1000 leads")
    print()

    while True:

        value = input(
            "Select target: "
        ).strip()

        if value == "1":
            return 100

        if value == "2":
            return 250

        if value == "3":
            return 1000

        print(
            "Invalid selection."
        )


def choose_locations() -> List[str]:

    print()
    print(
        "Enter location(s), separated by comma."
    )
    print(
        "Example: Newyork, New Jersey"
    )
    print()

    while True:

        raw = input(
            "Location: "
        ).strip()

        values = [
            clean_text(x)
            for x in raw.split(",")
            if clean_text(x)
        ]

        if values:
            return values

        print(
            "Please enter at least one location."
        )


def choose_categories() -> List[Category]:

    print()

    for category in CATEGORIES:

        print(
            f"{category.number:02d}. "
            f"{category.name}"
        )

    print(
        "00. All Categories"
    )

    print()

    while True:

        raw = input(
            "Category(s): "
        ).strip()

        if raw == "0":
            return CATEGORIES

        try:

            numbers = [
                int(x.strip())
                for x in raw.split(",")
                if x.strip()
            ]

        except ValueError:

            print(
                "Invalid category."
            )

            continue

        selected = [
            category
            for category in CATEGORIES
            if category.number in numbers
        ]

        if selected:
            return selected

        print(
            "Invalid category."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    setup_logging()

    print()
    print("=" * 72)
    print(
        "JWIZ PRODUCTION DATA SCRAPER"
    )
    print("=" * 72)
    print()

    target = choose_target()

    locations = choose_locations()

    categories = choose_categories()

    print()
    print(
        "Starting production scraper..."
    )
    print()

    store = MasterStore(
        MASTER_FILE
    )

    client = HTTPClient()

    try:

        scraper = JWizScraper(
            client=client,
            store=store,
            target=target,
            locations=locations,
            categories=categories,
        )

        scraper.run()

    finally:

        client.close()

    # ========================================================
    # SAVE
    # ========================================================

    if scraper.records:

        store.append(
            scraper.records
        )

    run_file = write_run_file(
        scraper.records
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 72)
    print("SCRAPING COMPLETE")
    print("=" * 72)

    print(
        f"Target:                 {target}"
    )

    print(
        f"New leads:              "
        f"{len(scraper.records)}"
    )

    print(
        f"Raw cards inspected:    "
        f"{scraper.raw_results}"
    )

    print(
        f"Duplicates skipped:     "
        f"{scraper.duplicates}"
    )

    print(
        f"Rejected records:       "
        f"{scraper.rejected}"
    )

    print(
        f"Pages processed:        "
        f"{scraper.pages}"
    )

    print(
        f"Profile pages visited:  "
        f"{scraper.profile_pages}"
    )

    print()

    print(
        f"Master file: {MASTER_FILE}"
    )

    if run_file:
        print(
            f"Run file:    {run_file}"
        )

    print("=" * 72)


class JWizAdapter(BaseScraper):
    source_code = "JWIZ"

    def run(self, params: ScrapeParams) -> Iterator[RawRecord]:
        location = params.location or "new-york"
        keyword = params.keyword or "contractor"
        limit = params.limit or 25

        client = HTTPClient()
        try:
            found_names = set()
            page = 0
            max_pages = max(1, (limit + 99) // 100)
            yielded = 0

            while yielded < limit and page < max_pages:
                offset = page * 100
                url = build_search_url(location, keyword, offset)
                res = client.get(url)
                if res is None or res.status_code != 200:
                    status_code = res.status_code if res else "Connection Error"
                    if page == 0:
                        raise RuntimeError(f"JWiz search request failed with status {status_code}")
                    break

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(res.text, "html.parser")
                cards = find_result_cards(soup)
                if not cards:
                    break

                for card in cards:
                    if yielded >= limit:
                        break

                    name = extract_company_name(card)
                    if not name or len(name) < 3 or name in found_names:
                        continue

                    found_names.add(name)
                    phone = extract_phone(card)
                    email = extract_email(card)
                    loc_line = extract_location_line(card)
                    city, state = extract_city_state(loc_line)
                    profile_link = extract_profile_url(card)

                    # P4.2 Stable ID: profile_url
                    external_id = profile_link if profile_link else f"JWIZ-{name}-{phone}"
                    if not profile_link:
                        print(f"Warning: No profile_url found for {name}, generating fallback ID.")

                    yield RawRecord(
                        external_id=external_id,
                        source_url=profile_link or url,
                        organization_name=name,
                        email=email,
                        phone=phone,
                        location=f"{city}, {state}" if city and state else (city or state),
                        title=f"{keyword.title()} in {location.title()}",
                        lead_metadata={
                            "status": "OPEN",
                            "priority": extract_lead_priority(card)
                        }
                    )
                    yielded += 1

                page += 1
                time.sleep(1)
        finally:
            client.close()


if __name__ == "__main__":
    main()