"""
Backend/scrappers/Blue Book scrapper/scraper.py
────────────────────────────────────────────────
Modular Blue Book Construction & Contractor Directory Scraper.
Conforms strictly to the BaseScraper standard (matching GoogleMaps_Allcategories.py).

Features:
- Subclasses BaseScraper with complete ScraperMeta metadata
- Resolves trades and keywords to Blue Book class codes via keywords.py
- Maps user geographies (states/cities) to Blue Book regions (1-27) via geo.py
- Dual-layer extraction: card listings + locations-contacts subpages
- Human-in-the-loop and masked-element handling (View Phone button reveal)
- Streams raw dictionary records with source_code="bluebook" and record_kind="company"
- Implements resilient to_standard() with Normalization layer + direct fallback
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin

# Ensure Backend directory is on sys.path
_current_dir = Path(__file__).resolve().parent
_scrappers_dir = _current_dir.parent
_backend_dir = _scrappers_dir.parent
for _p in [str(_backend_dir), str(_scrappers_dir), str(_current_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from scrappers.base import (
    BaseScraper,
    InvalidScrapeParams,
    JobCancelled,
    NullScrapeContext,
    ScrapeContext,
    ScrapeParams,
    ScraperMeta,
    StandardRecord,
)

# Package-relative imports for Blue Book parsing and taxonomy
from . import geo
from . import keywords
from . import parsers
from . import phones
from . import urls

logger = logging.getLogger("scrappers.bluebook")

SCRAPPER_CODE = "bluebook"
SOURCE_CODE = "bluebook"
RECORD_KIND = "company"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class BlueBookScraper(BaseScraper):
    """
    Modular scraper for The Blue Book Building & Construction Network.
    Yields company records enriched with physical locations, key contacts,
    phones, and verified contractor trade metadata.
    """

    scrapper_code = SCRAPPER_CODE
    source_code = SOURCE_CODE

    meta = ScraperMeta(
        id=SCRAPPER_CODE,
        name="The Blue Book Network Scraper",
        description=(
            "Extracts verified commercial construction contractors, subcontractors, suppliers, and building professionals "
            "from The Blue Book Network across all US states and regions. Enriches business listings with company name, "
            "profile URL, website, street address, city, state, ZIP code, trade category, direct phone numbers, and "
            "key decision-maker contacts (Estimators, Principals, Project Managers)."
        ),
        record_kind=RECORD_KIND,
        category="Commercial Construction Directory",
        version="1.0.0",
        coverage={"country": "USA"},
        requires_location=True,
        requires_city=False,
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
            "contact_name",
            "contact_title",
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
        self.scrapper_code = SCRAPPER_CODE
        self.source_code = SOURCE_CODE
        self._active_browser: Optional[Browser] = None
        self._active_context: Optional[BrowserContext] = None

    @classmethod
    def get_scrapper_code(cls) -> str:
        return SCRAPPER_CODE

    @classmethod
    def get_source_code(cls) -> str:
        return SOURCE_CODE

    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """
        Execute Blue Book extraction yielding raw dictionary records.
        Streams records directly into BaseScraper.run() -> to_standard().
        """
        # 1. Parse quantity / limit
        if isinstance(params, dict):
            raw_limit = params.get("quantity") if params.get("quantity") is not None else params.get("limit")
            keyword_input = params.get("keyword") or params.get("category")
            city_input = params.get("city")
            state_input = params.get("us_state")
            location_input = params.get("location")
        else:
            raw_limit = getattr(params, "quantity", None) if getattr(params, "quantity", None) is not None else getattr(params, "limit", None)
            keyword_input = getattr(params, "keyword", None)
            city_input = getattr(params, "city", None)
            state_input = getattr(params, "us_state", None)
            location_input = getattr(params, "location", None)

        if raw_limit is None:
            raw_limit = getattr(self.meta, "default_limit", 25)
        try:
            limit = int(raw_limit)
        except (ValueError, TypeError):
            limit = 25
        limit = max(1, limit)

        # 2. Resolve geography
        parsed_state = ""
        parsed_city = ""
        if state_input and str(state_input).strip():
            parsed_state = geo.parse_state(str(state_input).strip())
        if city_input and str(city_input).strip():
            parsed_city = str(city_input).strip()

        if not parsed_state and location_input and str(location_input).strip():
            loc_dict = geo.parse_location(str(location_input).strip())
            parsed_state = loc_dict.get("state") or ""
            if not parsed_city:
                parsed_city = loc_dict.get("city") or ""

        # Blue Book requires at least a state or region to target
        if not parsed_state and not parsed_city:
            err_msg = f"{self.meta.name} requires a state or location before it can run. Ask the user for a state."
            if hasattr(self, "ctx") and self.ctx:
                self.ctx.log("error", err_msg)
            raise InvalidScrapeParams(err_msg)

        # 3. Resolve trade keyword
        trade_keyword = str(keyword_input).strip() if keyword_input else "General Contractors"

        # 4. Build search plan using keywords.py
        states_arg = [parsed_state] if parsed_state else []
        cities_arg = [parsed_city] if parsed_city else []

        plan = keywords.build_plan(
            keywords=[trade_keyword],
            states=states_arg,
            cities=cities_arg,
            expansion="balanced",
        )

        search_specs = list(plan.specs)
        if not search_specs:
            # Fallback direct URL if build_plan yielded no spec
            region_candidates = geo.regions_for_state(parsed_state) if parsed_state else [1]
            region_num = region_candidates[0] if region_candidates else 1
            fallback_url = f"https://www.thebluebook.com/search.html?region={region_num}&searchTerm={trade_keyword.replace(' ', '+')}"
            if parsed_city and parsed_state:
                fallback_url += f"&companylocatedin={parsed_city.replace(' ', '+')}_{parsed_state}"
            search_specs = [
                keywords.SearchSpec(
                    url=fallback_url,
                    keyword=trade_keyword,
                    state=parsed_state,
                    city=parsed_city,
                    trade=trade_keyword,
                )
            ]

        # Prioritize primary searches
        search_specs.sort(key=lambda s: (s.depth, s.priority))

        logger.info(
            "Blue Book search plan prepared: %d query spec(s) for keyword '%s' in %s, %s",
            len(search_specs),
            trade_keyword,
            parsed_city or "Statewide",
            parsed_state,
        )

        yielded = 0
        seen_company_ids = set()

        # 5. Launch Playwright browser session
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            self._active_browser = browser
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            self._active_context = context
            page = context.new_page()
            page.set_default_timeout(35000)

            try:
                for spec_idx, spec in enumerate(search_specs, start=1):
                    if yielded >= limit:
                        break

                    self.check_cancel()
                    current_search_url = spec.url
                    logger.info("🔍 [%d/%d] Executing search: %s", spec_idx, len(search_specs), current_search_url)

                    # Handle search page with possible pagination
                    pending_listing_urls = [current_search_url]
                    visited_listing_urls = set()

                    while pending_listing_urls and yielded < limit:
                        search_url = pending_listing_urls.pop(0)
                        if search_url in visited_listing_urls:
                            continue
                        visited_listing_urls.add(search_url)

                        self.check_cancel()
                        try:
                            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                        except Exception as e:
                            logger.warning("Failed navigating to search page %s: %s", search_url, e)
                            continue

                        listing_html = page.content()
                        access_state = parsers.detect_access(listing_html)
                        if access_state == "challenge":
                            logger.warning("Blue Book verification challenge detected on %s", search_url)
                            if hasattr(self, "ctx") and self.ctx:
                                self.ctx.log("warning", f"Blue Book verification challenge encountered on {search_url}. Pausing for user...")
                                if self.ctx.wait_for_user(f"Please solve verification on Blue Book: {search_url}"):
                                    listing_html = page.content()
                        elif access_state == "blocked":
                            logger.error("Blue Book access blocked by server (403 / Access Denied).")
                            if hasattr(self, "ctx") and self.ctx:
                                self.ctx.log("error", "Blue Book access blocked by server.")
                            break

                        listing_data = parsers.parse_listing(listing_html, page.url, category=spec.trade)
                        companies = listing_data.get("companies", [])


                        # Collect any pagination URLs for this search
                        for page_url in listing_data.get("pagination", []):
                            if page_url and page_url not in visited_listing_urls and page_url not in pending_listing_urls:
                                pending_listing_urls.append(page_url)

                        logger.info("   📋 Discovered %d companies on search page", len(companies))

                        # Visit and enrich each discovered company
                        for card in companies:
                            if yielded >= limit:
                                break

                            self.check_cancel()
                            comp_id = card.get("company_id")
                            if comp_id and comp_id in seen_company_ids:
                                continue
                            if comp_id:
                                seen_company_ids.add(comp_id)

                            company_name = card.get("name")
                            if not company_name or len(company_name.strip()) < 2:
                                continue

                            profile_url = card.get("profile_url") or card.get("pretty_url") or ""
                            contacts_url = urls.contacts_url(profile_url) if profile_url else ""

                            # Default values from listing card
                            website = card.get("website") or ""
                            phone = card.get("phone") or card.get("phone_e164") or ""
                            email = card.get("email") or ""
                            street = card.get("street") or card.get("address_raw") or ""
                            city = card.get("city") or spec.city
                            state = card.get("state") or spec.state
                            zip_code = card.get("zip") or ""
                            contact_name = ""
                            contact_title = ""
                            all_contacts = []
                            all_locations = []

                            # Enrich by visiting locations-contacts subpage
                            if contacts_url:
                                try:
                                    page.goto(contacts_url, wait_until="domcontentloaded", timeout=25000)

                                    # Reveal phone numbers if masked by "View Phone"
                                    try:
                                        view_btn = page.get_by_text("View Phone", exact=False)
                                        btn_count = view_btn.count()
                                        if btn_count > 0:
                                            for b_idx in range(min(btn_count, 10)):
                                                try:
                                                    view_btn.nth(b_idx).click(timeout=1000)
                                                except Exception:
                                                    pass
                                            page.wait_for_timeout(400)
                                    except Exception:
                                        pass

                                    c_html = page.content()
                                    c_data = parsers.parse_contacts(c_html, page.url, expected_name=company_name)

                                    all_locations = c_data.get("locations", [])
                                    all_contacts = c_data.get("contacts", [])

                                    # Extract address from primary location
                                    if all_locations:
                                        main_loc = next((l for l in all_locations if l.get("is_main")), all_locations[0])
                                        street = main_loc.get("street") or main_loc.get("address_raw") or street
                                        city = main_loc.get("city") or city
                                        state = main_loc.get("state") or state
                                        zip_code = main_loc.get("zip") or zip_code
                                        website = main_loc.get("website") or website
                                        if not phone:
                                            phone = main_loc.get("phone") or main_loc.get("phone_e164") or ""

                                    # Extract primary decision maker
                                    if all_contacts:
                                        first_c = all_contacts[0]
                                        contact_name = first_c.get("name") or ""
                                        contact_title = first_c.get("title") or ""
                                        if not phone:
                                            phone = first_c.get("phone") or first_c.get("phone_e164") or ""
                                        if not email:
                                            email = first_c.get("email") or ""

                                except Exception as c_exc:
                                    logger.debug("Contacts enrichment exception for %s: %s", company_name, c_exc)

                            # If still on profile root or contacts didn't provide website
                            if not website and card.get("website"):
                                website = card.get("website")

                            trade_name = spec.trade or card.get("category") or (card.get("listing_trades", [""])[0] if card.get("listing_trades") else trade_keyword)

                            record = {
                                "id": f"bluebook-{comp_id or yielded + 1}",
                                "record_kind": RECORD_KIND,
                                "source_code": SOURCE_CODE,
                                "scrapper_code": SCRAPPER_CODE,
                                "external_id": str(comp_id or ""),
                                "profile_url": profile_url,
                                "source_url": profile_url,
                                "company_name": company_name,
                                "rating": card.get("rating", ""),
                                "phone": phone,
                                "email": email,
                                "website": website,
                                "address": street,
                                "city": city,
                                "state": state,
                                "Zip_Code": zip_code,
                                "category": trade_name,
                                "professional_category": trade_name,
                                "contact_name": contact_name,
                                "contact_title": contact_title,

                                "extra": {
                                    "trades": card.get("listing_trades", []),
                                    "certifications": card.get("certifications", []),
                                    "contacts": all_contacts,
                                    "locations": all_locations,
                                },
                            }

                            yielded += 1
                            logger.info(
                                "   ✅ [%d/%d] %s | %s, %s | Phone: %s | Contact: %s",
                                yielded,
                                limit,
                                company_name,
                                city,
                                state,
                                phone or "N/A",
                                contact_name or "N/A",
                            )

                            if hasattr(self, "ctx") and self.ctx:
                                pct = min(99.0, (yielded / limit) * 100.0)
                                self.ctx.progress(pct, f"Scraped {yielded}/{limit}: {company_name}")

                            yield record

                            if yielded >= limit:
                                logger.info("🎯 Blue Book extraction reached requested target count (%d).", limit)
                                break

                            time.sleep(0.3)

            except JobCancelled:
                logger.info("Blue Book extraction cancelled by context.")
                raise
            except Exception as run_exc:
                logger.error("Unhandled error in Blue Book scraper: %s", run_exc, exc_info=True)
                raise
            finally:
                self.close()

    def close(self) -> None:
        """Clean up active Playwright context and browser."""
        try:
            if self._active_context:
                self._active_context.close()
                self._active_context = None
        except Exception:
            pass
        try:
            if self._active_browser:
                self._active_browser.close()
                self._active_browser = None
        except Exception:
            pass
        super().close()


# Canonical aliases matching system naming conventions
BlueBookScrapper = BlueBookScraper
BluebookScraper = BlueBookScraper

# Register package aliases in sys.modules so any loader pattern succeeds
_mod = sys.modules[__name__]
for _alias in [
    "scrappers.Blue Book scrapper",
    "Backend.scrappers.Blue Book scrapper",
    "scrappers.bluebook",
    "Backend.scrappers.bluebook",
    "scrappers.BlueBook",
    "Backend.scrappers.BlueBook",
]:
    sys.modules.setdefault(_alias, _mod)
