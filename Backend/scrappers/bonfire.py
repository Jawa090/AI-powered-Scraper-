from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urljoin

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scrappers.base import BaseScraper, ScrapeContext, ScrapeParams, ScraperMeta, StandardRecord
from scrappers.driver import make_driver, retry_driver_call

logger = logging.getLogger(__name__)

BASE_URL = "https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities"


def _parse_due_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.lower() in ("open", "none", "n/a", "tbd", "ongoing"):
        return None
    try:
        from dateutil import parser
        return parser.parse(cleaned)
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

    def __init__(self, ctx: Optional[ScrapeContext] = None, headless: bool = True) -> None:
        super().__init__(ctx)
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

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr, table tr"))
            )
        except Exception:
            logger.warning("Timed out waiting for table elements. Checking DOM anyway...")

        rows = self.driver.find_elements(By.CSS_SELECTOR, "tbody tr")
        if not rows:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tr")
            if rows and len(rows) > 1:
                rows = rows[1:]

        results: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            try:
                text = row.text.strip()
                if not text or "Ref. #" in text:
                    continue

                cells = row.find_elements(By.TAG_NAME, "td")
                link_el = None
                links = row.find_elements(By.TAG_NAME, "a")
                for a in links:
                    href = a.get_attribute("href") or ""
                    if "opportunity" in href or "portal" in href:
                        link_el = a
                        break
                if not link_el and links:
                    link_el = links[0]

                url = link_el.get_attribute("href") if link_el else ""
                if not url or url.rstrip("/") == BASE_URL.rstrip("/"):
                    logger.debug("Skipping row %d due to missing specific opportunity URL.", idx)
                    continue

                status = "OPEN"
                ref_num = ""
                project_title = ""
                close_date = ""

                if cells and len(cells) >= 4:
                    status = cells[0].text.strip() or "OPEN"
                    ref_num = cells[1].text.strip()
                    project_title = cells[2].text.strip()
                    close_date = cells[3].text.strip()
                else:
                    parts = text.split("\n")
                    if len(parts) >= 2:
                        ref_num = parts[0]
                        project_title = parts[1]
                    else:
                        project_title = text[:100]

                # Strict requirement: external_id = ref_number. Missing ref_number -> skip.
                if not ref_num:
                    logger.warning("Skipping Bonfire row %d missing reference number.", idx)
                    continue

                results.append({
                    "ref_number": ref_num,
                    "title": project_title,
                    "status": status,
                    "close_date": close_date,
                    "issuing_organization": "City of Dallas",
                    "location": "Dallas, TX, USA",
                    "url": url,
                })
            except Exception as row_err:
                logger.warning("Error parsing Bonfire row %d: %s", idx, row_err)
                continue

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

            desc_elements = self.driver.find_elements(
                By.CSS_SELECTOR, ".opportunity-description, .description, [class*='description'], .panel-body, p"
            )
            desc_text = ""
            bot_patterns = ["cloudflare", "security service", "verifies you are not a bot", "ray id"]
            for el in desc_elements[:5]:
                txt = el.text.strip()
                if len(txt) > 20 and "cookie" not in txt.lower():
                    if any(pat in txt.lower() for pat in bot_patterns):
                        continue
                    desc_text = txt
                    break

            opportunity["description"] = desc_text or None

            # Look for contact / buyer in page body text
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            buyer_match = re.search(r"(?:Buyer|Contact|Specialist)[:\s]+([^\n\r]+)", body_text, re.IGNORECASE)
            if buyer_match and not any(pat in buyer_match.group(1).lower() for pat in bot_patterns):
                opportunity["contact_person"] = buyer_match.group(1).strip()
            else:
                opportunity["contact_person"] = None

            email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", body_text)
            if email_match and "cloudflare" not in email_match.group(0).lower():
                opportunity["contact_email"] = email_match.group(0).strip()
            else:
                opportunity["contact_email"] = None

        except Exception as e:
            logger.debug("Detail extraction notice for %s: %s", opportunity.get("ref_number"), e)

        return opportunity

    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """
        Execute scrape with keyword filter applied BEFORE taking limit.
        Yields raw opportunity records.
        """
        if not self.setup_chrome():
            raise RuntimeError("Failed to initialize Chrome driver for Bonfire.")

        try:
            all_opps = self.discover_opportunities()

            # Apply keyword filter BEFORE limit
            kw = (params.keyword or "").strip().lower()
            filtered: List[Dict[str, Any]] = []
            for opp in all_opps:
                if kw:
                    searchable = f"{opp.get('title', '')} {opp.get('ref_number', '')} {opp.get('status', '')}".lower()
                    if kw not in searchable:
                        continue
                filtered.append(opp)
                if len(filtered) >= params.limit:
                    break

            for opp in filtered:
                if self.ctx.should_cancel():
                    break
                enriched = self.extract_details(opp)
                yield enriched
                time.sleep(0.3)
        finally:
            self.close()

    def to_standard(self, raw: Dict[str, Any]) -> StandardRecord:
        """Transform raw Bonfire record into StandardRecord."""
        ref_num = raw.get("ref_number") or raw.get("source_id")
        title = raw.get("title")
        close_date = raw.get("close_date")
        due_at = _parse_due_date(close_date)

        return StandardRecord(
            source_code=self.meta.id,
            record_kind=self.meta.record_kind,
            external_id=ref_num,
            source_url=raw.get("url"),
            title=title,
            description=raw.get("description"),
            organization_name="City of Dallas",
            contact_name=raw.get("contact_person"),
            contact_title=raw.get("contact_title"),
            email=raw.get("contact_email") or raw.get("email"),
            phone=raw.get("contact_phone") or raw.get("phone"),
            website=raw.get("url"),
            city="Dallas",
            us_state="TX",
            postal_code="75201",
            category="Municipal Procurement",
            due_at=due_at,
            extra={
                "ref_number": ref_num,
                "status": raw.get("status"),
                "close_date": close_date,
            },
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
