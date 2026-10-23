"""
Backend/scrappers/BBB scrapper/bbb.py
─────────────────────────────────────
Modular Better Business Bureau (bbb.org) Scraper.
Conforms to the BaseScraper modular standard on par with GoogleMaps_Allcategories.py and Houzz.py.

Extracts commercial contractor and business leads across all 50 US states and cities:
- Queries BBB's public, unauthenticated search JSON API (no headless browser overhead for listings)
- Dynamically paginates up to requested quantity, seamlessly exiting when reaching site results limit (BBB typically serves up to 15 pages x 15 = 225 records per query)
- Strips <em> search highlighting, decodes HTML entities, normalizes addresses, phone numbers, ratings, accreditation
- Discovers company websites from profile pages and performs direct website crawling for contact emails
- Supports both ScrapeParams objects and dictionary parameter inputs
- Responsive mid-run cancellation and progress telemetry
- Standalone CLI execution support
"""

from __future__ import annotations

import argparse
import html
import logging
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlencode, urljoin

# Ensure Backend and Project root are on sys.path for standalone or package execution
_this_dir = Path(__file__).resolve().parent
_scrappers_dir = _this_dir.parent
_backend_dir = _scrappers_dir.parent
_project_root = _backend_dir.parent

# Clean up any potential shadow of Backend/utils package from sys.path
for _p in [str(_scrappers_dir), str(_this_dir)]:
    while _p in sys.path:
        sys.path.remove(_p)

# Ensure Backend and Project Root are prioritized on sys.path
for _p in [str(_project_root), str(_backend_dir)]:
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

# If 'utils' was previously cached as the single-file scrappers/utils.py module,
# uncache it so that imports of 'utils.pii' resolve to the Backend/utils package.
if "utils" in sys.modules and not hasattr(sys.modules["utils"], "__path__"):
    del sys.modules["utils"]

import requests
from bs4 import BeautifulSoup

try:
    from scrappers.base import (
        BaseScraper,
        InvalidScrapeParams,
        JobCancelled,
        ScrapeContext,
        ScrapeParams,
        ScraperMeta,
        StandardRecord,
    )
    from scrappers.utils import state_code, to_json_safe
except ImportError:
    from Backend.scrappers.base import (
        BaseScraper,
        InvalidScrapeParams,
        JobCancelled,
        ScrapeContext,
        ScrapeParams,
        ScraperMeta,
        StandardRecord,
    )
    from Backend.scrappers.utils import state_code, to_json_safe

logger = logging.getLogger(__name__)

# Constants
CANONICAL_HOST = "www.bbb.org"
API_SEARCH_URL = "https://www.bbb.org/api/search"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
WEBSITE_TIMEOUT = 6
READER_TIMEOUT = 12

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}", re.IGNORECASE)
IGNORED_EMAIL_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    "wixpress.com", "schema.org", "sentry.io", "example.com", "domain.com",
    "email.com", "yourdomain.com", "bbb.org", "ca.gov", "dca.ca.gov",
)
DENIED_DOMAINS = (
    "bbb.org", "bbbmarketplacetrust.org", "give.org", "bbbprograms.org",
    "cslb.ca.gov", ".gov", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "linkedin.com", "yelp.com",
    "pinterest.com", "tiktok.com", "google.com", "mapquest.com",
)


def _make_absolute(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = str(url).strip()
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{CANONICAL_HOST}" + (url if url.startswith("/") else f"/{url}")


def _clean_email(email_str: Optional[str]) -> Optional[str]:
    if not email_str:
        return None
    clean = email_str.strip().lower()
    if any(clean.endswith(ext) for ext in IGNORED_EMAIL_EXTS):
        return None
    if any(deny in clean for deny in ("sentry", "example", "wixpress", "debug")):
        return None
    return clean


def scrape_website_for_email_and_social(website_url: Optional[str]) -> Tuple[Optional[str], Dict[str, Optional[str]]]:
    """
    Crawls business website homepage and contact page to discover emails and social links.
    Conforms to the enrichment standard used across GoogleMaps and Houzz scrapers.
    """
    socials: Dict[str, Optional[str]] = {
        "facebook": None,
        "instagram": None,
        "linkedin": None,
        "twitter": None,
    }
    if not website_url or not str(website_url).startswith("http"):
        return None, socials

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    discovered_email = None
    urls_to_try = [website_url]

    try:
        for u in urls_to_try:
            try:
                resp = requests.get(u, headers=headers, timeout=WEBSITE_TIMEOUT, allow_redirects=True)
                if resp.status_code != 200 or not resp.text:
                    continue

                soup = BeautifulSoup(resp.content, "html.parser")

                # 1. Search mailto links
                for link in soup.find_all("a", href=True):
                    href = link.get("href", "").strip()
                    if href.lower().startswith("mailto:"):
                        cand = href.split("mailto:")[1].split("?")[0].strip()
                        cleaned = _clean_email(cand)
                        if cleaned:
                            discovered_email = cleaned
                            break

                # 2. Regex fallback on HTML text
                if not discovered_email:
                    raw_emails = EMAIL_REGEX.findall(resp.text)
                    for cand in raw_emails:
                        cleaned = _clean_email(cand)
                        if cleaned:
                            discovered_email = cleaned
                            break

                # 3. Social link discovery
                social_patterns = {
                    "facebook": (r"facebook\.com", r"fb\.com"),
                    "instagram": (r"instagram\.com",),
                    "linkedin": (r"linkedin\.com",),
                    "twitter": (r"twitter\.com", r"x\.com"),
                }
                for link in soup.find_all("a", href=True):
                    href = link.get("href", "").strip()
                    href_lower = href.lower()
                    if any(ignored in href_lower for ignored in ["share", "intent", "sharer"]):
                        continue
                    for platform, patterns in social_patterns.items():
                        if not socials[platform] and any(re.search(pat, href_lower) for pat in patterns):
                            socials[platform] = href

                # 4. Check for contact page link if no email found on homepage
                if not discovered_email and u == website_url:
                    for link in soup.find_all("a", href=True):
                        href = link.get("href", "").strip()
                        href_lower = href.lower()
                        if any(k in href_lower for k in ["contact", "about", "reach-us"]):
                            contact_target = urljoin(website_url, href)
                            if contact_target != website_url and contact_target not in urls_to_try:
                                urls_to_try.append(contact_target)
                                break

                if discovered_email:
                    break
            except Exception:
                continue

    except Exception as e:
        logger.debug("Website scrape error for %s: %s", website_url, e)

    return discovered_email, socials


def extract_website_from_profile(profile_url: Optional[str]) -> Optional[str]:
    """
    Extracts the official company website by fetching the profile page via r.jina.ai reader.
    Bypasses Cloudflare Managed Challenge safely without requiring a proxy.
    """
    if not profile_url:
        return None

    try:
        reader_url = f"https://r.jina.ai/{profile_url}"
        headers = {
            "User-Agent": DEFAULT_UA,
            "Accept": "text/plain",
            "X-Return-Format": "markdown",
            "x-timeout": "15",
        }
        resp = requests.get(reader_url, headers=headers, timeout=READER_TIMEOUT)
        if resp.status_code != 200 or not resp.text:
            return None

        text = resp.text

        # 1. Match [Visit Website](https://...) or Visit Website: https://...
        patterns = [
            r"\[Visit Website\]\((https?://[^)\s]+)\)",
            r"Website\s*:?\s*\[?\s*\]?\((https?://[^)\s]+)\)",
            r"Visit Website\s*:?\s*(https?://[^\s\)]+)",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().rstrip("/")
                candidate_lower = candidate.lower()
                if not any(deny in candidate_lower for deny in DENIED_DOMAINS):
                    return candidate

    except Exception as e:
        logger.debug("Profile fetch error for %s: %s", profile_url, e)

    return None


class BBBScraper(BaseScraper):
    """
    Modular Better Business Bureau (bbb.org) business directory scraper.
    Extracts commercial companies, contractor leads, verified phones, ratings,
    and crawls websites for direct email contacts.
    """
    scrapper_code = "bbb"
    source_code = "bbb"
    RECORD_KIND = "company"

    meta = ScraperMeta(
        id="bbb",
        name="Better Business Bureau",
        description=(
            "Collects verified commercial contractor and business listings from the Better Business Bureau (bbb.org) "
            "across all 50 US states and cities. Searches by trade keyword and location (state or city), extracting "
            "company name, phone number, physical address, city, state, postal code, BBB letter rating, rating score, "
            "accreditation status, official website, and crawls company websites for verified contact email addresses."
        ),
        record_kind="company",
        category="Commercial B2B Directory",
        version="1.0.0",
        coverage={"country": "USA"},
        supports=["limit", "keyword", "location"],
        fields=[
            "id",
            "source_code",
            "record_kind",
            "organization_name",
            "company_name",
            "phone",
            "email",
            "website",
            "address",
            "city",
            "us_state",
            "postal_code",
            "category",
            "rating",
            "rating_score",
            "is_accredited",
            "profile_url",
            "source_url",
        ],
        requires_location=True,
        requires_city=False,
        supported_cities=None,
        required_env=[],
        default_limit=20,
        max_limit=100,
    )

    def __init__(self, ctx: Optional[ScrapeContext] = None, headless: Optional[bool] = None) -> None:
        super().__init__(ctx=ctx, headless=headless)
        self.scrapper_code = "bbb"
        self.source_code = "bbb"
        self._session: Optional[requests.Session] = None

    @classmethod
    def get_scrapper_code(cls) -> str:
        return "bbb"

    @classmethod
    def get_source_code(cls) -> str:
        return "bbb"

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": DEFAULT_UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.bbb.org/search",
            })
        return self._session

    def _log(self, level: str, msg: str) -> None:
        """Safely logs to context if available without crashing the scraper."""
        if hasattr(self, "ctx") and self.ctx:
            try:
                self.ctx.log(level, msg)
            except Exception as e:
                logger.debug("ctx.log suppressed: %s", e)

    def _progress(self, percent: float, msg: str) -> None:
        """Safely reports progress to context if available without crashing."""
        if hasattr(self, "ctx") and self.ctx:
            try:
                self.ctx.progress(percent, msg)
            except Exception as e:
                logger.debug("ctx.progress suppressed: %s", e)

    @staticmethod
    def _parse_jina_search(text: str, default_category: str) -> List[Dict[str, Any]]:
        """Parses BBB search markdown retrieved via web reader when direct API is Cloudflare-blocked."""
        blocks = re.split(r"\n(?=###\s+\[)", text)
        results = []
        for block in blocks:
            m = re.match(r"###\s+\[([^\]]+)\]\(([^\)]+)\)", block)
            if not m:
                continue
            raw_name, profile_url = m.group(1), m.group(2)
            clean_name = html.unescape(re.sub(r"</?[a-zA-Z0-9_-]+>|[_*]", "", raw_name)).strip()
            clean_name = re.sub(r"^advertisement:\s*", "", clean_name, flags=re.IGNORECASE).strip()
            if not clean_name:
                continue

            phone_m = re.search(r"\[(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\]\(tel:", block)
            phone = phone_m.group(1) if phone_m else None

            rating_m = re.search(r"BBB Rating:\s*([A-F][+-]?)", block)
            rating = rating_m.group(1) if rating_m else None

            is_accredited = "Accredited Business" in block

            addr_m = re.search(r"(\d+[^,\n]+,\s*(?:\n\s*)?([A-Za-z\s]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?))", block)
            if addr_m:
                full_addr, city, st, zip_code = addr_m.group(1).replace("\n", " ").strip(), addr_m.group(2).strip(), addr_m.group(3), addr_m.group(4)
            else:
                full_addr, city, st, zip_code = None, None, None, None

            sku_m = re.search(r"/([^/]+-\d+-\d+)(?:/|\Z)", profile_url)
            sku = sku_m.group(1).replace("-", "_") if sku_m else re.sub(r"[^a-zA-Z0-9]", "_", clean_name.lower())

            results.append({
                "id": sku,
                "businessName": clean_name,
                "reportUrl": profile_url,
                "phone": phone,
                "address": full_addr,
                "city": city,
                "state": st,
                "postalcode": zip_code,
                "rating": rating,
                "ratingScore": None,
                "bbbMember": is_accredited,
                "tobText": default_category,
            })
        return results

    def to_standard(self, raw: Dict[str, Any]) -> StandardRecord:
        """
        Delegates normalization to BaseScraper.to_standard() and the central
        normalization layer (scrappers.normalize.normalizer).
        The base class generates/retrieves the database field mapping for 'bbb',
        stores it in PostgreSQL, and maps incoming raw datapoints into StandardRecord.
        Provides a safety fallback if the database normalizer is unreachable.
        """
        try:
            rec = super().to_standard(raw)
            if rec is not None:
                return rec
        except Exception as e:
            logger.debug("Base normalizer fallback engaged: %s", e)

        norm_state = state_code(raw.get("us_state") or raw.get("state")) or raw.get("us_state") or raw.get("state")
        company = raw.get("organization_name") or raw.get("company_name") or raw.get("title")

        return StandardRecord(
            source_code=self.meta.id,
            record_kind=self.meta.record_kind,
            external_id=str(raw.get("id") or raw.get("bbb_sku") or ""),
            source_url=raw.get("source_url") or raw.get("profile_url"),
            title=company,
            organization_name=company,
            contact_name=raw.get("contact_name"),
            contact_title=raw.get("contact_title"),
            email=raw.get("email"),
            phone=raw.get("phone"),
            website=raw.get("website"),
            city=raw.get("city"),
            us_state=norm_state,
            postal_code=raw.get("postal_code") or raw.get("postalcode"),
            category=raw.get("category"),
            extra=to_json_safe(raw.get("extra") or {}),
        )

    def scrape(self, params: Any) -> Iterator[Dict[str, Any]]:
        """
        Executes BBB data extraction yielding raw dictionary records.
        Supports both ScrapeParams instances and raw dictionary inputs.
        Paginates BBB's JSON endpoint and enriches each result with website and email contacts.
        """
        def _param(k: str, default: Any = None) -> Any:
            if isinstance(params, dict):
                return params.get(k, default)
            return getattr(params, k, default)

        # Resolve limit and quantity parameters
        raw_limit = _param("quantity") if _param("quantity") is not None else _param("limit")
        if raw_limit is None:
            raw_limit = self.meta.default_limit
        try:
            target_quantity = int(raw_limit)
        except (ValueError, TypeError):
            target_quantity = 20

        # Adjust max_limit dynamically per specification:
        # If given quantity < 100, max limit is set to 100.
        # If given quantity >= 100, max limit is set to that quantity.
        if target_quantity < 100:
            effective_max_limit = 100
        else:
            effective_max_limit = target_quantity

        try:
            self.meta = self.meta.model_copy(update={"max_limit": effective_max_limit})
        except Exception:
            self.meta.max_limit = effective_max_limit

        # Attempt to scrape the full requested quantity
        limit = max(1, target_quantity)

        keyword = (_param("keyword") or "General Contractors").strip()

        # Resolve location: supports city, us_state, or raw location
        city = _param("city")
        us_state = _param("us_state")
        raw_loc = _param("location")

        if city and us_state:
            location_str = f"{city}, {us_state}"
        elif us_state:
            location_str = str(us_state).strip()
        elif city:
            location_str = str(city).strip()
        elif raw_loc:
            location_str = str(raw_loc).strip()
        else:
            err_msg = f"{self.meta.name} requires a city or state before it can run. Ask the user for a search location."
            self._log("error", err_msg)
            raise InvalidScrapeParams(err_msg)

        session = self._get_session()
        yielded = 0
        seen_skus = set()

        self._log("info", f"Starting BBB search: keyword='{keyword}', location='{location_str}', limit={limit}")
        self._progress(5.0, f"Querying BBB directory for {keyword} in {location_str}")

        # BBB search pagination: dynamically compute max pages needed to fulfill requested quantity.
        # BBB typically serves up to 15 pages (15 items/page = 225 max). If the site runs out of
        # listings before reaching limit, the scraper logs the event and exits cleanly with all scraped data.
        max_pages = max(16, (limit + 14) // 15 + 5)
        for page_num in range(1, max_pages + 1):
            if yielded >= limit:
                break

            self.check_cancel()

            query_params = {
                "find_country": "USA",
                "find_text": keyword,
                "find_loc": location_str,
                "page": str(page_num),
                "sort": "AToZ",
            }
            search_url = f"{API_SEARCH_URL}?{urlencode(query_params)}"

            try:
                results = []
                try:
                    resp = session.get(search_url, timeout=20)
                    if resp.status_code == 200 and resp.text:
                        data = resp.json()
                        results = data.get("results") or []
                    elif resp.status_code == 403:
                        logger.info("BBB API 403 challenge, engaging web reader fallback for page %d", page_num)
                except Exception as api_err:
                    logger.debug("BBB direct API request error on page %d: %s", page_num, api_err)

                # Fallback to r.jina.ai web reader if direct JSON API is blocked or empty
                if not results:
                    search_page_url = f"https://www.bbb.org/search?find_country=USA&find_text={urlencode({'q': keyword})[2:]}&find_loc={urlencode({'q': location_str})[2:]}&page={page_num}&sort=AToZ"
                    jina_url = f"https://r.jina.ai/{search_page_url}"
                    try:
                        jina_resp = session.get(
                            jina_url,
                            headers={"User-Agent": DEFAULT_UA, "Accept": "text/plain", "X-Return-Format": "markdown"},
                            timeout=25,
                        )
                        if jina_resp.status_code == 200 and jina_resp.text:
                            results = self._parse_jina_search(jina_resp.text, keyword)
                    except Exception as jina_err:
                        logger.debug("BBB web reader request error on page %d: %s", page_num, jina_err)

                if not results:
                    logger.info("BBB search completed or reached site limit at page %d (collected %d/%d records)", page_num, yielded, limit)
                    self._log("info", f"BBB search completed: reached end of available listings at page {page_num} ({yielded}/{limit} records collected).")
                    break

                for item in results:
                    if yielded >= limit:
                        break

                    self.check_cancel()

                    sku = item.get("id")
                    if sku and sku in seen_skus:
                        continue
                    if sku:
                        seen_skus.add(sku)

                    # Strip highlighting tags and unescape HTML entities in business name
                    raw_name = item.get("businessName") or ""
                    clean_name = html.unescape(re.sub(r"</?em>", "", raw_name)).strip()
                    if not clean_name:
                        continue

                    profile_path = item.get("reportUrl")
                    profile_url = _make_absolute(profile_path)

                    phones = item.get("phone")
                    phone = phones[0] if isinstance(phones, list) and phones else (phones or None)

                    address = item.get("address") or None
                    item_city = item.get("city") or None
                    item_state = item.get("state") or None
                    postalcode = item.get("postalcode") or None

                    # BBB Rating & accreditation
                    rating = item.get("rating") or None
                    rating_score = item.get("ratingScore")
                    try:
                        rating_score = float(rating_score) if rating_score is not None else None
                    except (ValueError, TypeError):
                        rating_score = None
                    if not rating and rating_score == 0.0:
                        rating = None
                        rating_score = None

                    is_accredited = bool(item.get("bbbMember")) if item.get("bbbMember") is not None else None
                    trade_cat = item.get("tobText") or keyword

                    # 1. Discover official website from BBB profile
                    website = None
                    email = None
                    socials = {}

                    if profile_url:
                        self.check_cancel()
                        website = extract_website_from_profile(profile_url)

                    # 2. Enrich with direct website crawl for emails & social channels
                    if website:
                        self.check_cancel()
                        email, socials = scrape_website_for_email_and_social(website)

                    yielded += 1

                    raw_record = {
                        "id": f"bbb_{sku}" if sku else f"bbb_{yielded}",
                        "bbb_sku": sku,
                        "source_code": self.meta.id,
                        "scrapper_code": self.meta.id,
                        "record_kind": self.meta.record_kind,
                        "organization_name": clean_name,
                        "company_name": clean_name,
                        "title": clean_name,
                        "contact_name": None,
                        "contact_title": None,
                        "phone": phone,
                        "email": email,
                        "website": website,
                        "address": address,
                        "city": item_city or city,
                        "us_state": item_state or us_state,
                        "postal_code": postalcode,
                        "category": trade_cat,
                        "source_url": profile_url,
                        "profile_url": profile_url,
                        "extra": {
                            "rating": rating,
                            "rating_score": rating_score,
                            "is_accredited": is_accredited,
                            "bbb_id": item.get("bbbId"),
                            "bbb_office": item.get("bbbName"),
                            "facebook": socials.get("facebook"),
                            "instagram": socials.get("instagram"),
                            "linkedin": socials.get("linkedin"),
                            "twitter": socials.get("twitter"),
                        },
                    }

                    pct = min(99.0, (yielded / limit) * 100.0)
                    self._progress(pct, f"Scraped {yielded}/{limit}: {clean_name}")

                    yield raw_record

                time.sleep(0.5)

            except JobCancelled:
                raise
            except Exception as e:
                logger.error("Error querying BBB API on page %d: %s", page_num, e)
                self._log("warning", f"BBB query warning on page {page_num}: {e}")
                break

        self._progress(100.0, f"BBB scraping complete: {yielded} records collected.")
        self._log("info", f"BBB scraper finished: collected {yielded}/{limit} records.")

    def close(self) -> None:
        """Closes HTTP session."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
        super().close()


# Canonical aliases
BBBScrapper = BBBScraper
meta = BBBScraper.meta


def main() -> None:
    """Standalone CLI test runner for BBB scraper."""
    parser = argparse.ArgumentParser(description="BBB Scraper CLI runner")
    parser.add_argument("--keyword", default="Roofing Contractors", help="Search category or trade")
    parser.add_argument("--location", default="Dallas, TX", help="Location (city and/or state)")
    parser.add_argument("--limit", type=int, default=3, help="Maximum records to extract")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    scraper = BBBScraper()
    params = ScrapeParams(keyword=args.keyword, location=args.location, limit=args.limit)

    print(f"\n🔍 Testing BBB Scraper: {args.keyword} in {args.location} (limit={args.limit})\n")
    count = 0
    for record in scraper.run(params):
        count += 1
        print(f"[{count}] {record.organization_name}")
        print(f"    Phone: {record.phone}")
        print(f"    Email: {record.email}")
        print(f"    Website: {record.website}")
        print(f"    Location: {record.city}, {record.us_state} {record.postal_code}")
        print(f"    Rating: {record.extra.get('rating')} (Score: {record.extra.get('rating_score')})")
        print(f"    URL: {record.source_url}\n")

    print(f"✅ Completed: {count} records extracted.")


if __name__ == "__main__":
    main()
