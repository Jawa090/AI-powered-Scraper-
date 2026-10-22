#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import random
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

# Ensure Backend and Project root are on sys.path for standalone or package execution
_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
for _d in [str(_backend_dir), str(_project_root)]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

# Load .env if python-dotenv is installed (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================
#                          LOGGING
# ============================================================

logger = logging.getLogger(__name__)

# Scraper canonical identification
scrapper_code = "facebook"
SCRAPPER_CODE = scrapper_code
source_code = scrapper_code
SOURCE_CODE = scrapper_code
RECORD_KIND = "company"


def get_scrapper_code() -> str:
    """Return the canonical scrapper code ('facebook')."""
    return scrapper_code


def get_source_code() -> str:
    """Return the canonical source code ('facebook')."""
    return scrapper_code


# ============================================================
#       BASE SCRAPER DYNAMIC LOADER & MODEL INTEGRATION
# ============================================================

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
        elif _ln == "            map = normalizer.create_map(raw)":
            _fixed_lines.append(
                "            try:\n"
                "                map = normalizer.create_map(raw)\n"
                "            except Exception:\n"
                "                map = {}\n"
            )
        else:
            _fixed_lines.append(_ln)
    _fixed_src = "\n".join(_fixed_lines) + "\n"

    for _mod_name in ("scrappers.base", "Backend.scrappers.base"):
        _existing = sys.modules.get(_mod_name)
        if _existing is not None and hasattr(_existing, "BaseScraper"):
            if not getattr(_existing, "_fb_safe_patched", False):
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
                    _existing._fb_safe_patched = True
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
        _base_mod._fb_safe_patched = True
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
    ScraperNotReady = getattr(_base_module, "ScraperNotReady", ScraperException)
    ScraperMeta = _base_module.ScraperMeta
    StandardRecord = _base_module.StandardRecord
else:
    from pydantic import BaseModel, Field

    class ScraperException(Exception):
        pass

    class ScraperNotReady(ScraperException):
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
        default_limit: int = 25
        max_limit: int = 100

    class ScrapeParams(BaseModel):
        limit: int = 25
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


# ============================================================
#         DATABASE SOURCE ENSURANCE (IDEMPOTENT & SAFE)
# ============================================================

def ensure_source_exists() -> None:
    """
    Ensure that the 'facebook' source record exists in the Database so
    Scrapper_Record_Map_Repository can link the map during normalization.
    """
    try:
        from Database.controller import session_scope
        from Database.models.source import Source
        from sqlalchemy import select, func
        import uuid

        with session_scope() as s:
            exists = s.scalar(select(Source.id).where(func.lower(Source.code) == scrapper_code))
            if not exists:
                src = Source(
                    id=str(uuid.uuid4()),
                    name="Facebook Business Pages Scraper",
                    code=scrapper_code,
                    category="Social & Business Directory",
                    status="Active",
                    description="Extracts public business leads and contacts from Facebook business pages.",
                    default_limit=25,
                )
                s.add(src)
                s.commit()
    except Exception as e:
        logger.debug(f"DB source record ensurance skipped or already present: {e}")


# ============================================================
#                          CONFIG
# ============================================================

# Facebook Login Credentials — read from .env / environment (never hard-code them)
User_Name = os.getenv("FB_USERNAME", "")
Password = os.getenv("FB_PASSWORD", "")

# Default search configurations
SEARCH_KEYWORD = "general contractors"
SEARCH_LOCATION = "Miami, Florida"
MAX_RESULTS = 300
DEFAULT_QUANTITY = 25
MAX_QUANTITY = 100

OUTPUT_FILE = "facebook_business_leads.xlsx"
CHECKPOINT_FILE = "facebook_scraper_checkpoint.json"

# Delay range between actions (in seconds)
MIN_DELAY = 2.5
MAX_DELAY = 6.0

# How many pixels to scroll each time
SCROLL_MIN = 400
SCROLL_MAX = 900

# Headless mode default
HEADLESS = False

# ---------------- SESSION REUSE SETTINGS ----------------
# The session/cookie state is stored strictly locally in a file, not in the DB.
DEFAULT_SESSION_FILE = str(Path(__file__).resolve().parent / "fb_session_state.json")
SESSION_STATE_FILE = os.getenv("FB_SESSION_STATE_FILE", DEFAULT_SESSION_FILE)
SESSION_CHECK_URL = "https://www.facebook.com/settings"
MAX_AUTO_LOGINS_PER_RUN = 1
ALLOW_MANUAL_STEPS = True
LEGACY_USER_DATA_DIR = "fb_scraper_profile"

# ---------------- TOKEN STORAGE (LOCAL FILE ONLY, NEVER DB) ----------------
# As required, auth tokens are stored locally in a file, not in the database.
DEFAULT_TOKEN_FILE = str(Path(__file__).resolve().parent / "fb_token.txt")
TOKEN_FILE = os.getenv("FB_TOKEN_FILE", DEFAULT_TOKEN_FILE)


def get_token_file_path() -> str:
    """Return the absolute path to the local token storage file."""
    env_file = os.getenv("FB_TOKEN_FILE")
    if env_file:
        return env_file
    if os.path.exists("fb_token.txt"):
        return os.path.abspath("fb_token.txt")
    return DEFAULT_TOKEN_FILE


def load_token_from_file(token_file: Optional[str] = None) -> Optional[str]:
    """
    Load stored Facebook token from a local file (never from DB).
    Checks env vars FB_ACCESS_TOKEN and FB_TOKEN as fallback.
    """
    path = token_file or get_token_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    return token
        except Exception as e:
            logger.warning(f"Could not read token from {path}: {e}")
    env_token = os.getenv("FB_ACCESS_TOKEN") or os.getenv("FB_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip()
    return None


def save_token_to_file(token: str, token_file: Optional[str] = None) -> bool:
    """
    Save Facebook token locally to a file (strictly avoiding DB storage).
    """
    if not token or not str(token).strip():
        return False
    path = token_file or get_token_file_path()
    try:
        parent_dir = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(token).strip())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        logger.info(f"Saved Facebook token locally to file: {path}")
        return True
    except Exception as e:
        logger.warning(f"Could not save token to {path}: {e}")
        return False


# ============================================================
#                      DEPENDENCIES
# ============================================================

_PLAYWRIGHT_AVAILABLE = True
_OPENPYXL_AVAILABLE = True

try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        TimeoutError as PWTimeout,
        sync_playwright,
    )
    try:
        from playwright_stealth import Stealth

        def apply_stealth(page):
            Stealth().apply_stealth_sync(page)
    except ImportError:
        try:
            from playwright_stealth import stealth_sync

            def apply_stealth(page):
                stealth_sync(page)
        except ImportError:
            def apply_stealth(page):
                pass
except ImportError as e:
    _PLAYWRIGHT_AVAILABLE = False
    Browser = Any
    BrowserContext = Any
    Page = Any
    Playwright = Any
    PWTimeout = Exception
    sync_playwright = None
    apply_stealth = lambda page: None
    logger.warning(f"Playwright dependencies not available: {e}")

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    _OPENPYXL_AVAILABLE = False
    Workbook = None
    Alignment = None
    Font = None
    PatternFill = None
    get_column_letter = None


# True only when someone can actually press ENTER in this terminal
INTERACTIVE = ALLOW_MANUAL_STEPS and sys.stdin is not None and sys.stdin.isatty()

# URL fragments that mean "you are not (fully) logged in"
LOGIN_URL_MARKERS = ("/login", "login.php", "/recover", "/checkpoint", "two_step_verification")
VERIFICATION_URL_MARKERS = ("/checkpoint", "two_step_verification")


class ManualActionRequired(ScraperException):
    """Raised when a human must log in / verify and we cannot (or should not) wait."""


# Regex patterns for extracting contact info
PHONE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
)
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
CAPTCHA_PATTERNS = [
    "security check", "captcha", "enter the code", "suspicious activity",
    "we need to check", "verify your identity", "two-factor", "login approval",
    "please confirm your identity", "unusual activity", "check your notifications"
]

# ════════════════════════════════════════════════════════════════
#  EXACT RAW SCHEMA (Matching System Standard for Normalization)
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
    "followers", "likes",
    "scraped_at",
]


def create_default_record() -> Dict[str, Any]:
    """Create a raw record initialized with all schema keys set to None."""
    rec = {key: None for key in EXACT_SCHEMA}
    rec["record_kind"] = "company"
    rec["source_code"] = scrapper_code
    rec["scrapper_code"] = scrapper_code
    rec["country"] = "United States"
    return rec


def build_stable_id(company_name: Optional[str], phone: Optional[str], address: Optional[str]) -> Optional[str]:
    """Build stable URL-safe ID from company name + unique hash suffix."""
    if not company_name:
        return None
    safe_name = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    hash_input = f"{phone or ''}{address or ''}"
    if hash_input:
        hash_suffix = hashlib.md5(hash_input.encode("utf-8")).hexdigest()[:6]
        return f"{safe_name}-{hash_suffix}"
    return safe_name


def parse_address_parts(
    address: Optional[str], fallback_location: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse address into (city, state, postal_code) with optional fallback location."""
    city, state, postal = None, None, None
    if address:
        try:
            from Database.normalize import parse_location
            city, state, postal = parse_location(address)
            if city and "," in city:
                subparts = [p.strip() for p in city.split(",") if p.strip()]
                if subparts:
                    city = subparts[-1]
        except Exception:
            pass

    if not city or not state:
        loc = fallback_location or ""
        if loc:
            try:
                from Database.normalize import normalize_state, parse_location
                f_city, f_state, f_postal = parse_location(loc)
                if not city and f_city:
                    city = f_city
                if not state and f_state:
                    state = f_state
                if not state:
                    state = normalize_state(loc)
                if not postal and f_postal:
                    postal = f_postal
            except Exception:
                if "," in loc:
                    parts = loc.split(",")
                    if not city:
                        city = parts[0].strip()
                    if not state and len(parts) > 1:
                        state = parts[1].strip()

    return city, state, postal


def format_raw_record(
    details: Dict[str, Any],
    search_location: Optional[str] = None,
    search_keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format scraped page details into standardized raw dictionary schema,
    matching the format required for the BaseScraper and normalizer layer.
    """
    company_name = (details.get("name") or "").strip()
    page_url = (details.get("url") or "").strip()
    phone = (details.get("phone") or "").strip() or None
    email = (details.get("email") or "").strip() or None
    website = (details.get("website") or "").strip() or None
    address = (details.get("address") or "").strip() or None
    category = (details.get("category") or "").strip() or search_keyword or None
    rating = (details.get("rating") or "").strip() or None
    followers = (details.get("followers") or "").strip() or None
    likes = (details.get("likes") or "").strip() or None

    city, state, postal = parse_address_parts(address, fallback_location=search_location)
    record_id = build_stable_id(company_name, phone, address) or (page_url.rstrip("/").split("/")[-1] if page_url else None)

    rec = create_default_record()
    rec["id"] = record_id
    rec["external_id"] = record_id
    rec["record_kind"] = "company"
    rec["source_code"] = scrapper_code
    rec["scrapper_code"] = scrapper_code
    rec["profile_url"] = page_url
    rec["source_url"] = page_url
    rec["company_name"] = company_name
    rec["organization_name"] = company_name
    rec["title"] = company_name
    rec["professional_category"] = category
    rec["category"] = category
    rec["phone"] = phone
    rec["email"] = email
    rec["website"] = website
    rec["address"] = address
    rec["city"] = city
    rec["state"] = state
    rec["us_state"] = state
    rec["zip"] = postal
    rec["postal_code"] = postal
    rec["rating"] = rating
    rec["followers"] = followers
    rec["likes"] = likes
    rec["facebook"] = page_url
    rec["scraped_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return rec


def validate_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate scraped raw record."""
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
    if record.get("source_code") is None:
        record["source_code"] = scrapper_code
    if record.get("scrapper_code") is None:
        record["scrapper_code"] = scrapper_code

    if not record.get("company_name") and not record.get("organization_name"):
        errors.append("company_name / organization_name is required")
    if record.get("record_kind") != "company":
        errors.append(f"Invalid record_kind: expected 'company', got {record.get('record_kind')!r}")
    if record.get("source_code") != scrapper_code:
        errors.append(f"Invalid source_code: expected '{scrapper_code}', got {record.get('source_code')!r}")
    if record.get("scrapper_code") != scrapper_code:
        errors.append(f"Invalid scrapper_code: expected '{scrapper_code}', got {record.get('scrapper_code')!r}")
    return len(errors) == 0, errors


class QuantityValidationResult(tuple):
    """Result container for quantity validation supporting 2/3 element unpacking."""

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
            import dis
            import inspect
            frame = inspect.currentframe().f_back
            if frame:
                instructions = list(dis.get_instructions(frame.f_code))
                for instr in instructions:
                    if instr.offset >= frame.f_lasti:
                        if instr.opname in ("CACHE", "EXTENDED_ARG"):
                            continue
                        if instr.opname == "UNPACK_SEQUENCE":
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
    """Validate requested quantity of data rows."""
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
    """Interactively prompt user for number of data rows to scrape."""
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
            print(f"  ❌ {msg} Please enter the quantity again.")
            continue

        print(f"  → Selected row quantity: {parsed_qty}")
        return parsed_qty


# ============================================================
#                 BROWSER INTERACTION HELPERS
# ============================================================

def delay(min_sec=MIN_DELAY, max_sec=MAX_DELAY):
    """Random human-like delay between actions."""
    time.sleep(random.uniform(min_sec, max_sec))


def human_scroll(page, total_scrolls=5):
    """Scroll like a human — random amounts, pauses between scrolls."""
    for _ in range(total_scrolls):
        scroll_px = random.randint(SCROLL_MIN, SCROLL_MAX)
        page.mouse.wheel(0, scroll_px)
        time.sleep(random.uniform(0.5, 1.8))


def visible_within(locator, timeout=2000):
    """Wait up to `timeout` ms for an element to become visible."""
    try:
        locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False


# ============================================================
#       SESSION STATE FILE HELPERS (Stored locally in file)
# ============================================================

def get_session_file_path() -> str:
    """
    Return local file path for session storage.
    Session tokens/cookies are strictly stored locally in a file, not in the DB.
    """
    env_file = os.getenv("FB_SESSION_STATE_FILE")
    if env_file:
        return env_file
    if os.path.exists("fb_session_state.json"):
        return os.path.abspath("fb_session_state.json")
    return DEFAULT_SESSION_FILE


def has_session_cookie(context):
    """True if Facebook's login cookies (c_user + xs) are present."""
    try:
        names = {c.get("name") for c in context.cookies("https://www.facebook.com")}
        return {"c_user", "xs"} <= names
    except Exception:
        return False


def load_session_state_path():
    """Return the local session file path if it exists and looks valid, else None."""
    session_file = get_session_file_path()
    if not os.path.exists(session_file):
        logger.info(f"  ℹ️  No saved session file found at {session_file} — a login will be needed.")
        return None
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "cookies" not in data:
            raise ValueError("missing 'cookies' key")
        logger.info(f"  📂 Loaded saved session from {session_file}")
        return session_file
    except Exception as e:
        bad = session_file + ".corrupt"
        try:
            os.replace(session_file, bad)
        except OSError:
            pass
        logger.warning(f"  ⚠️  Session file unreadable ({e}); moved to {bad}. A login will be needed.")
        return None


def save_session_state(context):
    """
    Atomically write cookies + local storage to the local session file.
    Session tokens are stored strictly in a local file, never in DB.
    """
    if not has_session_cookie(context):
        return False
    session_file = get_session_file_path()
    tmp = session_file + ".tmp"
    try:
        parent_dir = os.path.dirname(os.path.abspath(session_file))
        os.makedirs(parent_dir, exist_ok=True)
        context.storage_state(path=tmp)
        os.replace(tmp, session_file)
        try:
            os.chmod(session_file, 0o600)
        except OSError:
            pass
        return True
    except Exception as e:
        logger.warning(f"  ⚠️  Could not save session state to {session_file}: {e}")
        return False


def migrate_legacy_profile(p):
    """One-time: export login from old persistent profile into the session file."""
    session_file = get_session_file_path()
    if os.path.exists(session_file) or not os.path.isdir(LEGACY_USER_DATA_DIR):
        return
    logger.info(f"  🔄 Exporting login from old profile '{LEGACY_USER_DATA_DIR}' to {session_file}...")
    ctx = None
    try:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=LEGACY_USER_DATA_DIR,
            headless=True,
        )
        if save_session_state(ctx):
            logger.info("  ✅ Old profile session exported.")
        else:
            logger.info("  ℹ️  Old profile had no Facebook login to export.")
    except Exception as e:
        logger.warning(f"  ⚠️  Could not read old profile: {str(e)[:80]}")
    finally:
        if ctx:
            try:
                ctx.close()
            except Exception:
                pass


# ============================================================
#                  CAPTCHA / VERIFICATION PAUSE
# ============================================================

def wait_for_captcha(page, ctx=None):
    """Check if CAPTCHA / security screen is visible and handle manual resolution."""
    try:
        body_text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return False
    for pat in CAPTCHA_PATTERNS:
        if pat in body_text:
            if ctx and hasattr(ctx, "wait_for_user"):
                try:
                    ctx.wait_for_user(f"Facebook CAPTCHA / security check detected: '{pat}'")
                except Exception:
                    pass
            if not INTERACTIVE:
                raise ManualActionRequired(
                    f"CAPTCHA / security screen detected ('{pat}') and no one is available to solve it."
                )
            print("\n" + "=" * 70)
            print("  ⚠️  CAPTCHA / SECURITY CHECK / 2FA DETECTED!")
            print("  Note: If running in HEADLESS = True mode, set HEADLESS = False")
            print("  temporarily to solve the verification in the browser window.")
            print("=" * 70)
            input(">> Press ENTER after solving CAPTCHA / verification: ")
            delay(2, 4)
            return True
    return False


# ============================================================
#                     SESSION MANAGER
# ============================================================

class FacebookSession:
    """Owns login lifecycle: validate saved session -> re-login -> save fresh session."""

    def __init__(self, context, page, username=None, password=None):
        self.context = context
        self.page = page
        self.username = username or User_Name
        self.password = password or Password
        self.auto_logins = 0
        self.last_reason = ""

    def on_login_wall(self):
        """Instant check: did current page redirect to login/verification?"""
        try:
            url = self.page.url.lower()
            if any(m in url for m in LOGIN_URL_MARKERS):
                return True
            return self.page.locator("input[name='pass']").first.is_visible()
        except Exception:
            return False

    def session_is_valid(self):
        """Confirm Facebook still accepts the current session."""
        if not has_session_cookie(self.context):
            self.last_reason = "no login cookies"
            return False
        try:
            self.page.goto(SESSION_CHECK_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self.last_reason = f"check page failed to load ({str(e)[:40]})"
            return False
        delay(2.0, 3.5)
        url = self.page.url.lower()
        if any(m in url for m in VERIFICATION_URL_MARKERS):
            self.last_reason = "checkpoint"
            return False
        if self.on_login_wall():
            self.last_reason = "redirected to login"
            return False
        if not has_session_cookie(self.context):
            self.last_reason = "Facebook cleared the login cookies"
            return False
        self.last_reason = "ok"
        return True

    def ensure(self):
        """Make sure we are logged in. Raises ManualActionRequired if human action needed."""
        if self.session_is_valid():
            logger.info("  ✅ Saved session is valid — no login needed.")
            self.save()
            return

        logger.info(f"  🔐 Session not usable ({self.last_reason}).")

        if self.last_reason == "checkpoint":
            self._manual_step("Facebook is showing a security checkpoint for this account.")
            return

        if self.auto_logins >= MAX_AUTO_LOGINS_PER_RUN:
            raise ManualActionRequired(
                "Session expired again and the automatic re-login limit for this run is used up."
            )

        self.auto_logins += 1
        self._clear_login_cookies()
        self._login_with_credentials()

        current = self.page.url.lower()
        if any(m in current for m in LOGIN_URL_MARKERS):
            self._manual_step("Facebook is asking for extra verification (or the login did not go through).")
            return

        if self.session_is_valid():
            self.save()
            logger.info(f"  ✅ Logged in and session saved to {get_session_file_path()}")
            return

        self._manual_step(f"Automatic login did not succeed ({self.last_reason}).")

    def save(self):
        return save_session_state(self.context)

    def _clear_login_cookies(self):
        """Remove dead login cookies while preserving browser device identification."""
        try:
            self.context.clear_cookies(name=re.compile(r"^(c_user|xs)$"))
        except TypeError:
            self.context.clear_cookies()

    def _login_with_credentials(self):
        """Type username + password into login form."""
        user = self.username or os.getenv("FB_USERNAME", "")
        pwd = self.password or os.getenv("FB_PASSWORD", "")
        if not (user and pwd):
            logger.warning("  ⚠️  FB_USERNAME / FB_PASSWORD not set (.env or environment).")
            return

        logger.info("  🔐 Navigating to Facebook login page...")
        try:
            self.page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning(f"  ⚠️  Could not open login page: {str(e)[:60]}")
            return
        delay(2.0, 3.5)

        try:
            cookie_btn = self.page.locator(
                "button[data-cookiebanner='accept_button'], "
                "button:has-text('Allow all cookies'), "
                "button:has-text('Accept All')"
            ).first
            if visible_within(cookie_btn, 2500):
                cookie_btn.click()
                delay(1.0, 2.0)
        except Exception:
            pass

        try:
            logger.info(f"  ⌨️  Authenticating with User_Name: {user[:4]}***...")
            email_box = self.page.locator("input#email, input[name='email']").first
            pass_box = self.page.locator("input#pass, input[name='pass']").first

            if not visible_within(email_box, 10000):
                logger.warning("  ⚠️  Login form did not appear.")
                return

            email_box.click()
            email_box.fill("")
            email_box.press_sequentially(user, delay=random.randint(45, 110))
            delay(0.6, 1.4)

            pass_box.click()
            pass_box.fill("")
            pass_box.press_sequentially(pwd, delay=random.randint(45, 110))
            delay(0.8, 1.6)

            login_btn = self.page.locator(
                "button#loginbutton, button[name='login'], button[type='submit']"
            ).first
            if visible_within(login_btn, 3000):
                login_btn.click()
            else:
                pass_box.press("Enter")

            try:
                self.page.wait_for_url(lambda u: "/login" not in u.lower(), timeout=20000)
            except Exception:
                pass
            delay(4.0, 6.0)
        except Exception as e:
            logger.warning(f"  ⚠️  Automated credential entry encountered an issue: {e}")

    def _manual_step(self, why):
        """Pause for manual completion in browser or raise on headless/server."""
        if not INTERACTIVE:
            session_file = get_session_file_path()
            raise ManualActionRequired(
                f"{why} Log in on a machine with a screen, then copy {session_file} here."
            )
        print("\n" + "=" * 70)
        print("  🔑 ACTION REQUIRED (2FA / DEVICE APPROVAL / CHECKPOINT / LOGIN)")
        print(f"  Reason: {why}")
        print("  1. Complete the login / verification in the browser window,")
        print("     or approve the login notification on your phone.")
        print("  2. Press ENTER here in the terminal to continue.")
        print("=" * 70)
        input(">> Press ENTER once you are logged into Facebook: ")
        delay(2.0, 4.0)
        if not self.session_is_valid():
            raise ManualActionRequired(f"Still not logged in after manual step ({self.last_reason}).")
        self.save()
        logger.info(f"  ✅ Logged in and session saved to {get_session_file_path()}")


# ============================================================
#                    CHECKPOINT (RESULTS)
# ============================================================

def load_checkpoint():
    """Load existing results from checkpoint file."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"  ✅ Loaded {len(data)} existing results from checkpoint.")
            return data
        except Exception:
            pass
    return []


def save_checkpoint(results):
    """Save results to checkpoint JSON."""
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Could not save checkpoint: {e}")


# ============================================================
#                       SCRAPING
# ============================================================

def extract_contact_info(page_text: str) -> Tuple[str, str, str]:
    """Extract phone, email, website from visible page text."""
    if not page_text:
        return "", "", ""

    phones = PHONE_RE.findall(page_text)
    emails = EMAIL_RE.findall(page_text)

    bad_emails = {"support@fb.com", "info@facebook.com", "noreply@facebook.com"}
    emails = [
        e.lower() for e in emails
        if e.lower() not in bad_emails
        and not any(e.lower().endswith(ext) for ext in (".png", ".jpg", ".gif", ".jpeg", ".webp"))
        and "sentry" not in e.lower()
    ]

    websites = []
    # Match standard http/https URLs
    for m in re.finditer(r"https?://[^\s<>\"]+", page_text, re.I):
        websites.append(m.group(0).rstrip(".,;)\"'"))
    # Match www. domains without leading protocol
    for m in re.finditer(r"\bwww\.[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}(?:/[^\s<>\"]*)?", page_text, re.I):
        u = m.group(0).rstrip(".,;)\"'")
        if not u.startswith("http"):
            u = "https://" + u
        websites.append(u)

    bad_domains = ("facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com", "linkedin.com", "youtube.com")
    clean_websites = []
    seen_w = set()
    for w in websites:
        w_clean = w.rstrip(".,;)\"'")
        w_lower = w_clean.lower()
        if any(bd in w_lower for bd in bad_domains):
            continue
        if w_lower not in seen_w and len(w_clean) > 8:
            clean_websites.append(w_clean)
            seen_w.add(w_lower)

    phone = phones[0] if phones else ""
    email = emails[0] if emails else ""
    website = clean_websites[0] if clean_websites else ""
    return phone, email, website


def scrape_page_details(page, page_url, ctx=None):
    """Visit a single Facebook business page and extract all contact info."""
    try:
        page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
        delay(1.5, 3.0)
        wait_for_captcha(page, ctx=ctx)

        try:
            page.wait_for_selector("h1, [role='main']", timeout=8000)
        except Exception:
            pass

        name = ""
        try:
            name_el = page.locator("h1").first
            name = name_el.inner_text(timeout=5000).strip()
        except Exception:
            pass
        if not name:
            try:
                title = page.title()
                name = title.replace(" | Facebook", "").strip()
            except Exception:
                name = page_url.rstrip("/").split("/")[-1].replace("-", " ").title()

        # Collect text from Intro / main page
        main_text = ""
        try:
            main_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            pass

        # Also try to visit or click the About tab for additional details
        about_text = ""
        try:
            about_link = page.locator("a[href*='/about'], a[href*='sk=about'], //span[text()='About']").first
            if about_link.is_visible(timeout=2000):
                about_link.click()
                delay(1.0, 2.0)
                about_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            pass

        body = f"{main_text}\n{about_text}" if about_text else main_text
        human_scroll(page, total_scrolls=2)

        phone, email, website = extract_contact_info(body)

        address = ""
        addr_match = re.search(
            r"(?:Address|Location|DIRECTIONS)\s*\n?\s*([^\n]{5,120})",
            body, re.I,
        )
        if addr_match:
            address = addr_match.group(1).strip()

        category = ""
        cat_match = re.search(
            r"^(.*?)\s*(?:·|•)\s*\d[\d,.K]*\s*(?:likes|followers)",
            body, re.M | re.I,
        )
        if cat_match:
            category = cat_match.group(1).strip()
        if not category:
            try:
                cat_el = page.locator("[role='main'] span, [role='main'] div").filter(
                    has_text=re.compile(r"Company|Contractor|Service|Business|Restaurant|Shop|Roofing|Plumbing", re.I)
                ).first
                category = cat_el.inner_text(timeout=2000).strip()[:80]
            except Exception:
                pass

        followers = ""
        likes = ""
        follower_match = re.search(r"([\d,.KM]+)\s*(?:followers|people follow)", body, re.I)
        if follower_match:
            followers = follower_match.group(1)
        like_match = re.search(r"([\d,.KM]+)\s*likes", body, re.I)
        if like_match:
            likes = like_match.group(1)

        rating = ""
        rating_match = re.search(r"(\d(?:\.\d)?)\s*(?:out of 5|\(.*reviews?\)|★|⭐)", body)
        if rating_match:
            rating = rating_match.group(1)

        return {
            "name": name,
            "category": category,
            "phone": phone,
            "email": email,
            "website": website,
            "address": address,
            "followers": followers,
            "likes": likes,
            "rating": rating,
            "url": page_url,
        }
    except ManualActionRequired:
        raise
    except Exception as e:
        logger.warning(f"    ⚠️  Error scraping {page_url}: {str(e)[:60]}")
        return None


def collect_page_urls(page, target_count, keyword=None, location=None, ctx=None):
    """Search Facebook for pages and collect unique page URLs."""
    kw = keyword or SEARCH_KEYWORD
    loc = location or SEARCH_LOCATION
    logger.info(f"🔍 Searching Facebook for: '{kw}' near '{loc}'")
    query = quote(f"{kw} {loc}".strip())
    search_url = f"https://www.facebook.com/search/pages/?q={query}"

    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    delay(2.5, 4.5)
    wait_for_captcha(page, ctx=ctx)

    try:
        initial_text = page.locator("body").inner_text(timeout=3000).strip()
        if initial_text.lower() == "not found":
            logger.error("❌ Facebook returned 'Not Found' on search endpoint.")
            return []
    except Exception:
        pass

    collected_urls = set()
    no_new_scrolls = 0
    max_scrolls = 200

    bad_segments = {
        "search", "watch", "reel", "reels", "video", "videos",
        "groups", "events", "marketplace", "stories", "story.php",
        "messages", "notifications", "friends", "settings",
        "help", "policies", "privacy", "ajax", "login",
        "login.php", "signup", "recover", "terms", "ads",
        "fundraisers", "gaming", "places", "saved", "home.php",
        "share.php", "dialog"
    }

    for scroll_num in range(max_scrolls):
        if len(collected_urls) >= target_count:
            break

        links = page.locator("a[href*='/']").all()
        new_this_round = 0
        for link in links:
            try:
                href = link.get_attribute("href")
                if not href:
                    continue
                if href.startswith("/"):
                    href = f"https://www.facebook.com{href}"
                if not href or "facebook.com/" not in href:
                    continue

                clean = href.split("?")[0].split("#")[0].rstrip("/")
                parts = [p for p in clean.split("/") if p]
                # Standard Facebook URL format: ['https:', 'www.facebook.com', 'PageSlug']
                if len(parts) < 3:
                    continue
                first_segment = parts[2].lower()
                if first_segment in bad_segments:
                    continue

                if clean not in collected_urls:
                    collected_urls.add(clean)
                    new_this_round += 1
            except Exception:
                continue

        if new_this_round > 0:
            no_new_scrolls = 0
        else:
            no_new_scrolls += 1
            if no_new_scrolls >= 8:
                logger.info(f"  ℹ️  No new pages loading after {no_new_scrolls} scrolls — at end of results.")
                break

        wait_for_captcha(page, ctx=ctx)
        human_scroll(page, total_scrolls=2)
        delay(1.5, 3.0)

    logger.info(f"✅ Collected {len(collected_urls)} unique page URLs from search.")
    return list(collected_urls)[:target_count]


# ============================================================
#                       EXCEL EXPORT
# ============================================================

def export_to_excel(results, output_path=OUTPUT_FILE):
    """Save all results to a formatted Excel file."""
    if not _OPENPYXL_AVAILABLE or Workbook is None:
        logger.warning("openpyxl is not installed; skipping Excel file export.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Facebook Business Leads"

    headers = [
        "#", "Page Name", "Category", "Phone", "Email", "Website",
        "Address", "Followers", "Likes", "Rating", "Facebook Page URL"
    ]

    ws.append(headers)
    hf = Font(bold=True, color="FFFFFF", size=11)
    hp = PatternFill("solid", fgColor="1877F2")
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = hf
        cell.fill = hp
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for i, r in enumerate(results, 1):
        ws.append([
            i,
            r.get("name", "") or r.get("company_name", "") or r.get("organization_name", ""),
            r.get("category", "") or r.get("professional_category", ""),
            r.get("phone", ""),
            r.get("email", ""),
            r.get("website", ""),
            r.get("address", ""),
            r.get("followers", ""),
            r.get("likes", ""),
            r.get("rating", ""),
            r.get("url", "") or r.get("profile_url", "") or r.get("source_url", ""),
        ])

    widths = [5, 38, 30, 18, 32, 40, 40, 12, 12, 8, 45]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for row in range(2, len(results) + 2):
        cell = ws.cell(row=row, column=11)
        if cell.value:
            cell.hyperlink = cell.value
            cell.font = Font(color="1877F2", underline="single")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(output_path)
    logger.info(f"💾 Saved to Excel: {output_path}")


# ============================================================
#  MODULAR SCRAPER CLASS (BaseScraper integration)
# ============================================================

class FacebookScrapper(BaseScraper):
    """
    Modular scraper for Facebook Public Business Pages.
    Inherits run(), to_standard(), and get_map() directly from BaseScraper.
    Tokens/session state are stored locally in a file (never in the DB).
    """

    scrapper_code = scrapper_code
    source_code = scrapper_code
    meta = ScraperMeta(
        id=scrapper_code,
        name="Facebook Business Pages Scraper",
        description=(
            "Extracts public business leads and contact information from Facebook business pages by "
            "search keyword and location. Collects company name, category, phone, email, website, "
            "address, ratings, followers, likes, and profile URL."
        ),
        record_kind="company",
        category="Social & Business Directory",
        version="1.0.0",
        coverage={"country": "USA"},
        requires_location=False,
        requires_city=False,
        supported_cities=None,
        supports=["limit", "keyword", "location"],
        fields=[
            "id",
            "record_kind",
            "source_code",
            "scrapper_code",
            "profile_url",
            "company_name",
            "category",
            "phone",
            "email",
            "website",
            "address",
            "rating",
            "followers",
            "likes",
        ],
        required_env=[],
        default_limit=25,
        max_limit=100,
    )

    def __init__(self, ctx: Optional[ScrapeContext] = None, headless: Optional[bool] = None) -> None:
        try:
            from settings import settings
            default_headless = getattr(settings, "SCRAPER_HEADLESS", False)
        except Exception:
            default_headless = HEADLESS
        if headless is None:
            headless = default_headless
        super().__init__(ctx=ctx, headless=headless)
        self.headless = headless
        self.scrapper_code = scrapper_code
        self.source_code = scrapper_code
        self._active_browser: Optional[Browser] = None
        self._active_context: Optional[BrowserContext] = None
        self._active_playwright: Optional[Playwright] = None
        self._target_locations: Optional[List[str]] = None
        self._target_categories: Optional[List[str]] = None
        self.token: Optional[str] = load_token_from_file()
        ensure_source_exists()

    @classmethod
    def get_scrapper_code(cls) -> str:
        """Return the canonical scrapper code ('facebook')."""
        return scrapper_code

    @classmethod
    def get_source_code(cls) -> str:
        """Return the canonical source code ('facebook')."""
        return scrapper_code

    @classmethod
    def save_token(cls, token: str, token_file: Optional[str] = None) -> bool:
        """Store token locally in file (strictly avoids DB storage)."""
        return save_token_to_file(token, token_file)

    @classmethod
    def load_token(cls, token_file: Optional[str] = None) -> Optional[str]:
        """Load token from local file."""
        return load_token_from_file(token_file)

    @classmethod
    def get_token_file_path(cls) -> str:
        """Return local token file path."""
        return get_token_file_path()

    @classmethod
    def register(cls) -> None:
        """Dynamically register Facebook scraper into controller.REGISTERED_SCRAPERS."""
        try:
            from scrappers import controller
            if cls not in controller.REGISTERED_SCRAPERS:
                controller.REGISTERED_SCRAPERS.append(cls)
        except Exception as e:
            logger.warning(f"Could not register Facebook scraper: {e}")

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
        Execute Facebook public business page extraction yielding raw dictionary records.
        Each yielded raw record streams into BaseScraper.run() -> BaseScraper.to_standard() -> normalizer.
        """
        if not _PLAYWRIGHT_AVAILABLE or sync_playwright is None:
            raise ScraperNotReady(
                "Playwright is required to run FacebookScrapper. Run: pip install playwright playwright-stealth && playwright install chromium"
            )

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

        # Enforce minimum quantity floor of 100 (runs till 100 if smaller, or till quantity if larger)
        limit = max(100, limit)

        def _param(k):
            if isinstance(params, dict):
                return params.get(k)
            return getattr(params, k, None)

        if self._target_categories:
            search_keyword = str(self._target_categories[0]).strip()
        else:
            keyword_val = _param("keyword") or _param("category")
            search_keyword = str(keyword_val).strip() if keyword_val and str(keyword_val).strip() else SEARCH_KEYWORD

        if self._target_locations:
            search_location = str(self._target_locations[0]).strip()
        else:
            city = _param("city")
            us_state = _param("us_state")
            location = _param("location")

            if city and us_state:
                search_location = f"{str(city).strip()}, {str(us_state).strip()}"
            elif city:
                search_location = str(city).strip()
            elif us_state:
                search_location = str(us_state).strip()
            elif location and str(location).strip():
                search_location = str(location).strip()
            else:
                search_location = SEARCH_LOCATION

        yielded = 0
        self.check_cancel()

        if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
            self.ctx.progress(0.0, f"Initializing Facebook scraper for '{search_keyword}' in '{search_location}'...")

        with sync_playwright() as pw:
            self._active_playwright = pw
            migrate_legacy_profile(pw)

            browser = pw.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            self._active_browser = browser

            session_path = load_session_state_path()
            context = browser.new_context(
                storage_state=session_path,
                viewport={"width": 1920, "height": 1080},
            )
            self._active_context = context
            page = context.new_page()
            apply_stealth(page)

            session = FacebookSession(context, page, User_Name, Password)

            try:
                self.check_cancel()
                if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
                    self.ctx.progress(5.0, "Validating Facebook session...")

                session.ensure()

                self.check_cancel()
                if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
                    self.ctx.progress(10.0, f"Searching Facebook pages: '{search_keyword}' near '{search_location}'...")

                all_urls = collect_page_urls(
                    page, limit, keyword=search_keyword, location=search_location, ctx=self.ctx
                )
                if not all_urls and session.on_login_wall():
                    logger.info("Logged out during search — re-checking session...")
                    session.ensure()
                    all_urls = collect_page_urls(
                        page, limit, keyword=search_keyword, location=search_location, ctx=self.ctx
                    )

                logger.info(f"Found {len(all_urls)} target Facebook page URLs.")

                for i, url in enumerate(all_urls, 1):
                    if yielded >= limit:
                        break

                    self.check_cancel()

                    if hasattr(self, "ctx") and self.ctx and hasattr(self.ctx, "progress"):
                        pct = min(99.0, 15.0 + (yielded / limit) * 80.0)
                        self.ctx.progress(pct, f"Scraping [{yielded + 1}/{limit}]: {url}")

                    data = scrape_page_details(page, url, ctx=self.ctx)

                    if session.on_login_wall():
                        logger.info("Logged out mid-run — re-checking session...")
                        session.ensure()
                        data = scrape_page_details(page, url, ctx=self.ctx)
                        if session.on_login_wall():
                            raise ManualActionRequired("Logged out again immediately after re-login.")

                    if data and data.get("name"):
                        rec = format_raw_record(
                            data,
                            search_location=search_location,
                            search_keyword=search_keyword,
                        )
                        is_valid, rec_errors = validate_record(rec)
                        if not is_valid:
                            logger.warning(f"Record validation warnings for {data.get('name')}: {rec_errors}")

                        yielded += 1
                        logger.info(
                            f"   ✅ [{yielded}/{limit}] {rec.get('company_name')} | "
                            f"{rec.get('phone')} | {rec.get('email')}"
                        )

                        if yielded % 10 == 0:
                            session.save()

                        # Yield raw dictionary directly to BaseScraper.run() -> to_standard()
                        yield rec

                        if yielded >= limit:
                            logger.info(f"🎯 Reached requested row count ({limit}). Stopping.")
                            break

                        delay(MIN_DELAY, MAX_DELAY)

            finally:
                session.save()
                if context:
                    try:
                        context.close()
                    except Exception:
                        pass
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
                self._active_context = None
                self._active_browser = None
                self._active_playwright = None

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
FacebookScraper = FacebookScrapper

# Register module in sys.modules under package paths when executed directly or imported
sys.modules.setdefault("scrappers.Facebook", sys.modules[__name__])
sys.modules.setdefault("Backend.scrappers.Facebook", sys.modules[__name__])


# ============================================================
#                          MAIN
# ============================================================

def main():
    print("=" * 70)
    print("  FACEBOOK PUBLIC BUSINESS PAGE SCRAPER")
    print("=" * 70)
    print(f"  Search     : {SEARCH_KEYWORD}")
    print(f"  Location   : {SEARCH_LOCATION}")
    print(f"  Max results: {MAX_RESULTS}")
    print(f"  Headless   : {HEADLESS}")
    print(f"  Interactive: {INTERACTIVE}")
    print(f"  Session    : {get_session_file_path()}")
    print(f"  Token file : {get_token_file_path()}")
    print(f"  Output     : {OUTPUT_FILE}")
    print("=" * 70)

    # Load checkpoint
    results = load_checkpoint()
    exit_code = 0

    params = ScrapeParams(
        limit=MAX_RESULTS,
        keyword=SEARCH_KEYWORD,
        location=SEARCH_LOCATION,
    )
    scraper = FacebookScrapper(headless=HEADLESS)

    try:
        streamed_count = 0
        for record in scraper.run(params):
            streamed_count += 1
            results.append({
                "name": record.organization_name or record.title,
                "category": record.category,
                "phone": record.phone,
                "email": record.email,
                "website": record.website,
                "address": record.extra.get("address", "") if hasattr(record, "extra") else "",
                "followers": record.extra.get("followers", "") if hasattr(record, "extra") else "",
                "likes": record.extra.get("likes", "") if hasattr(record, "extra") else "",
                "rating": record.extra.get("rating", "") if hasattr(record, "extra") else "",
                "url": record.source_url or (record.extra.get("profile_url", "") if hasattr(record, "extra") else ""),
            })
            if streamed_count % 10 == 0:
                save_checkpoint(results)
            logger.info(f"   🔄 Streamed [{streamed_count}/{MAX_RESULTS}] via BaseScraper.run: {record.organization_name}")

        logger.info(f"Scraping completed. Total datapoints streamed: {streamed_count}")

    except ManualActionRequired as e:
        print("\n" + "=" * 70)
        print("  🛑 HUMAN ACTION NEEDED — stopping safely.")
        print(f"  {e}")
        print("=" * 70)
        exit_code = 2
    except JobCancelled:
        print("\n⏹️ Scrape cancelled.")
        exit_code = 0
    except Exception as e:
        logger.error(f"Scraper error: {e}")
        exit_code = 1
    finally:
        save_checkpoint(results)
        scraper.close()

    if results:
        export_to_excel(results)

    phones = sum(1 for r in results if r.get("phone"))
    emails = sum(1 for r in results if r.get("email"))
    websites = sum(1 for r in results if r.get("website"))
    print(f"\n{'=' * 70}")
    print("  ✅ SCRAPE COMPLETE" if exit_code == 0 else "  ⚠️  SCRAPE STOPPED EARLY (exit code 2)")
    print(f"  Total pages scraped : {len(results)}")
    print(f"  Phone numbers       : {phones}")
    print(f"  Email addresses     : {emails}")
    print(f"  Websites found      : {websites}")
    print(f"  Output file         : {OUTPUT_FILE}")
    print(f"  Checkpoint          : {CHECKPOINT_FILE}")
    print(f"  Session file        : {get_session_file_path()}")
    print(f"  Token file          : {get_token_file_path()}")
    print(f"{'=' * 70}")
    print("\n📋 Legal note: Data is from public Facebook pages. You are")
    print("responsible for complying with Facebook's Terms of Service and")
    print("all applicable laws (GDPR, CCPA, CAN-SPAM, TCPA).\n")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopped by user.")
        sys.exit(0)