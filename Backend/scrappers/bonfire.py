from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scrappers.base import BaseScraper, ScrapeContext, ScrapeParams, ScraperMeta, StandardRecord
from scrappers.driver import make_driver, retry_driver_call
from scrappers.utils import to_json_safe

logger = logging.getLogger(__name__)

BASE_URL = "https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities"


def _parse_due_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.lower() in ("open", "none", "n/a", "tbd", "ongoing"):
        return None
    from scrappers.utils import parse_local_dt
    parsed = parse_local_dt(cleaned, "America/Chicago")
    if parsed:
        return parsed
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Chicago")
    try:
        from dateutil import parser
        tzinfos = {"CST": -21600, "CDT": -18000, "EST": -18000, "EDT": -14400}
        dt = parser.parse(cleaned, tzinfos=tzinfos)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    except Exception:
        return None


class BonfireScraper(BaseScraper):
    """Modular scraper for City of Dallas Bonfire Hub."""

    meta = ScraperMeta(
        id="bonfire",
        name="Dallas City Hall Bonfire Portal",
        description="Extracts open municipal procurement bids, RFPs, and solicitation notices from the City of Dallas Bonfire portal.",
        record_kind="opportunity",
        category="Government & Municipal Bids",
        version="1.0.0",
        coverage={"city": "Dallas", "state": "TX"},
        supports=["limit", "keyword"],
        fields=[
            "source_code",
            "record_kind",
            "external_id",
            "source_url",
            "title",
            "description",
            "organization_name",
            "contact_name",
            "contact_title",
            "email",
            "phone",
            "website",
            "city",
            "us_state",
            "postal_code",
            "category",
            "due_at",
        ],
        required_env=[],
        default_limit=20,
        max_limit=100,
    )

    def __init__(self, ctx: Optional[ScrapeContext] = None, headless: Optional[bool] = None) -> None:
        from settings import settings
        if headless is None:
            headless = getattr(settings, "SCRAPER_HEADLESS", True)
        super().__init__(ctx, headless=headless)
        self.headless = headless
        self.driver = None

    def setup_chrome(self) -> bool:
        """Initialize browser session using standard driver factory."""
        if self.driver:
            return True
        try:
            self.driver = make_driver(headless=self.headless)
            return True
        except Exception as e:
            logger.error("Failed to initialize Chrome driver for Bonfire: %s", e)
            return False

    def discover_opportunities(self) -> List[Dict[str, Any]]:
        """Load portal table and parse open opportunity listings."""
        if not self.driver:
            raise RuntimeError("Browser not initialized. Call setup_chrome() first.")

        logger.info("Navigating to Bonfire portal: %s", BASE_URL)
        retry_driver_call(lambda: self.driver.get(BASE_URL), action_name="get Bonfire portal")
        time.sleep(3)

        from scrappers.base import SourceBlocked
        bot_patterns = ["cloudflare", "security service", "verifies you are not a bot", "ray id"]
        page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
        if any(pat in page_text for pat in bot_patterns):
            raise SourceBlocked("Bonfire portal blocked access with a bot challenge.")

        try:
            # Wait until at least one row in the table contains a link, which indicates data has been populated
            WebDriverWait(self.driver, 15).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tbody tr td a")) > 0
            )
        except Exception:
            logger.warning("Timed out waiting for populated table rows. Checking DOM anyway...")

        from scrappers.bonfire_parser import parse_listings
        results = parse_listings(self.driver.page_source, BASE_URL)
        if not results:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if not any(marker in page_text for marker in ("no opportunities", "no open", "no matching", "no data", "0 entries")):
                raise RuntimeError("Bonfire listing parser found no rows and no explicit empty-list indication.")
        logger.info("Discovered %d opportunities from City of Dallas Bonfire.", len(results))
        return results

    def extract_details(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Extract detail page fields (description, contact person, email)."""
        if not self.driver or not opportunity.get("url"):
            return opportunity

        url = opportunity["url"]
        try:
            self.driver.get(url)
            time.sleep(2)

            bot_patterns = ["cloudflare", "security service", "verifies you are not a bot", "ray id"]
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(pat in page_text for pat in bot_patterns):
                opportunity["detail_blocked"] = True
                return opportunity

            desc_elements = self.driver.find_elements(
                By.CSS_SELECTOR, ".opportunity-description, .description, [class*='description'], .panel-body, p"
            )
            desc_text = ""
            for el in desc_elements[:5]:
                txt = el.text.strip()
                if len(txt) > 20 and "cookie" not in txt.lower():
                    desc_text = txt
                    break

            opportunity["description"] = desc_text or None

            # Look for contact / buyer in page body text
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            buyer_match = re.search(r"(?:Buyer|Contact|Specialist)[:\s]+([^\n\r]+)", body_text, re.IGNORECASE)
            if buyer_match:
                opportunity["contact_person"] = buyer_match.group(1).strip()
            else:
                opportunity["contact_person"] = None

            email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", body_text)
            if email_match:
                opportunity["contact_email"] = email_match.group(0).strip()
            else:
                opportunity["contact_email"] = None

        except Exception as e:
            logger.debug("Detail extraction notice for %s: %s", opportunity.get("ref_number"), e)

        return opportunity

    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """
        Collect source records within the run limit; match requests at delivery.
        Yields raw opportunity records.
        """
        if not self.setup_chrome():
            raise RuntimeError("Failed to initialize Chrome driver for Bonfire.")

        try:
            all_opps = self.discover_opportunities()
            filtered = all_opps[:params.limit]

            for opp in filtered:
                self.check_cancel()
                enriched = self.extract_details(opp)
                yield enriched
                time.sleep(0.3)
        finally:
            self.close()

    def to_standard(self, raw: Dict[str, Any]) -> StandardRecord:
        """Transform raw Bonfire record into StandardRecord."""
        ref_num = raw.get("ref_number") or raw.get("source_id") or raw.get("external_id")
        url = raw.get("url") or raw.get("source_url")
        if not ref_num and url:
            m = re.search(r"/opportunities/(\d+)", url)
            if m:
                ref_num = m.group(1)

        title = raw.get("title")
        close_date = raw.get("close_date") or raw.get("due_date") or raw.get("due_date_raw")
        due_at = raw.get("due_at") or _parse_due_date(close_date)

        org_name = raw.get("organization_name") or raw.get("issuing_organization") or "City of Dallas"

        return StandardRecord(
            source_code=self.meta.id,
            record_kind=self.meta.record_kind,
            external_id=str(ref_num) if ref_num is not None else None,
            source_url=url,
            title=title,
            description=raw.get("description"),
            organization_name=org_name,
            contact_name=raw.get("contact_person") or raw.get("contact_name"),
            contact_title=raw.get("contact_title"),
            email=raw.get("contact_email") or raw.get("email"),
            phone=raw.get("contact_phone") or raw.get("phone"),
            website=raw.get("website"),
            city=raw.get("city") or "Dallas",
            us_state=raw.get("us_state") or "TX",
            postal_code=raw.get("postal_code"),
            category=raw.get("category"),
            due_at=due_at,
            extra=to_json_safe({
                "ref_number": ref_num,
                "status": raw.get("status"),
                "close_date": close_date,
                "detail_blocked": raw.get("detail_blocked", False),
            }),
        )

    def close(self) -> None:
        """Safely close driver instance."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.debug("Error closing Bonfire driver: %s", e)
            self.driver = None
        super().close()


# Backwards compatibility alias
DallasBonfireScraper = BonfireScraper
