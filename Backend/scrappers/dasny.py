from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scrappers.base import BaseScraper, ScrapeContext, ScrapeParams, ScraperMeta, StandardRecord
from scrappers.driver import make_driver, retry_driver_call

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dasny.org"
LISTING_URL = "https://www.dasny.org/opportunities/rfps-bids"


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    cleaned = _clean(raw)
    try:
        from dateutil import parser
        return parser.parse(cleaned)
    except Exception:
        pass
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", cleaned)
    if m:
        mo, dy, yr = m.groups()
        try:
            return datetime(int(yr), int(mo), int(dy))
        except ValueError:
            return None
    return None


class DasnyScraper(BaseScraper):
    """Modular scraper for DASNY RFP & Bid Opportunities."""

    meta = ScraperMeta(
        id="dasny",
        name="DASNY RFP & Bid Opportunities",
        description="Extracts public works RFPs, construction bids, and solicitations from the Dormitory Authority of the State of New York.",
        record_kind="opportunity",
        category="State Authority RFPs",
        version="1.0.0",
        coverage={"state": "NY"},
        supports=["limit", "keyword", "location"],
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
            logger.error("Failed to initialize Chrome driver for DASNY: %s", e)
            return False

    def _extract_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape opportunity details from a specific RFP page."""
        if not self.driver:
            return None

        logger.debug("Scraping DASNY opportunity: %s", url)
        try:
            retry_driver_call(lambda: self.driver.get(url), action_name=f"get {url}")
            time.sleep(1.5)
        except Exception as e:
            logger.warning("Failed to load DASNY detail page %s: %s", url, e)
            return None

        html = self.driver.page_source

        title = self._get_title()
        header_fields = self._get_header_fields()
        description = self._get_description()
        contacts = self._get_contacts(html)

        solicitation_number = (
            header_fields.get("Solicitation #")
            or header_fields.get("Solicitation Number")
            or header_fields.get("Bid Number")
            or header_fields.get("RFP Number")
            or header_fields.get("Contract #")
        )

        # Strict requirement: external_id = solicitation number (missing -> skip + report)
        if not solicitation_number:
            logger.warning("Skipping DASNY opportunity missing solicitation number at %s", url)
            return None

        due_date_raw = (
            header_fields.get("Due Date")
            or header_fields.get("Proposal Due")
            or header_fields.get("Bid Due Date")
        )
        location_raw = (
            header_fields.get("Location")
            or header_fields.get("Location Where Goods to be Delivered or Service Performed")
        )
        loc_address, loc_city, loc_state, loc_zip = self._parse_location(location_raw)

        return {
            "solicitation_number": solicitation_number,
            "source_url": url,
            "title": title,
            "description": description or None,
            "due_date_raw": due_date_raw,
            "due_at": _parse_date(due_date_raw),
            "issuing_organization": "Dormitory Authority of the State of New York (DASNY)",
            "location_raw": location_raw,
            "location_address": loc_address,
            "location_city": loc_city,
            "location_state": loc_state or "NY",
            "location_zip": loc_zip,
            "contacts": contacts,
            "header_fields": header_fields,
        }

    def _get_title(self) -> str:
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, "div.rfp-bid-title h2 a")
            return _clean(el.text)
        except Exception:
            pass
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, "h1")
            return _clean(el.text)
        except Exception:
            return "DASNY RFP Opportunity"

    def _get_description(self) -> str:
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, "#rfp-bid-notice .panel-body")
            return _clean(el.text)
        except Exception:
            return ""

    def _get_header_fields(self) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "div.rfp-bid-info table tbody tr")
            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        label = _clean(cells[0].text).rstrip(":")
                        val = _clean(cells[1].text)
                        if label:
                            fields[label] = val
                except Exception:
                    continue
        except Exception:
            pass

        try:
            wrappers = self.driver.find_elements(By.CSS_SELECTOR, "div.rfp-detail-item-wrapper")
            for w in wrappers:
                try:
                    label_el = w.find_element(By.CSS_SELECTOR, ".rfp-detail-text-label")
                    val_el = w.find_element(By.CSS_SELECTOR, ".rfp-detail-field-value")
                    label = _clean(label_el.text).rstrip(":")
                    val = _clean(val_el.text)
                    if label:
                        fields[label] = val
                except Exception:
                    continue
        except Exception:
            pass

        return fields

    def _get_contacts(self, html: str) -> List[Dict[str, Optional[str]]]:
        contacts: List[Dict[str, Optional[str]]] = []
        js = r"""
        var out = [];
        var container = document.querySelector('#rfp-contacts .panel-body');
        if (!container) return out;
        var currentRole = null, currentLines = [];
        var children = container.children;
        function flush(){
            if(currentRole !== null){
                out.push({role: currentRole, lines: currentLines});
            }
        }
        for (var i=0; i<children.length; i++){
            var el = children[i];
            var tag = el.tagName.toLowerCase();
            if (tag === 'h2'){
                flush();
                currentRole = (el.innerText||'').trim();
                currentLines = [];
            } else {
                var t = (el.innerText||'').trim();
                if (t) currentLines.push(t);
                var a = el.querySelector('a[href^="mailto:"]');
                if (a){
                    currentLines.push('__MAILTO__:' + a.getAttribute('href'));
                }
            }
        }
        flush();
        return out;
        """
        try:
            raw_blocks = self.driver.execute_script(js) or []
        except Exception:
            raw_blocks = []

        for block in raw_blocks:
            role = _clean(block.get("role"))
            lines = [l for l in block.get("lines", []) if l]
            if not lines:
                continue

            contact: Dict[str, Optional[str]] = {
                "role": role,
                "name": None,
                "title": None,
                "email": None,
                "phone": None,
            }

            for raw_line in lines:
                if raw_line.startswith("__MAILTO__:"):
                    mailto = raw_line.replace("__MAILTO__:", "")
                    email = mailto.replace("mailto:", "").strip()
                    if email and "@" in email:
                        contact["email"] = email
                    continue

                line = _clean(raw_line)
                low = line.lower()
                if low.startswith("phone"):
                    contact["phone"] = _clean(re.sub(r"^phone:?\s*", "", line, flags=re.IGNORECASE))
                    continue
                if low.startswith("email"):
                    em = re.search(r"[\w.\-]+@[\w.\-]+\.\w+", line)
                    if em:
                        contact["email"] = em.group(0)
                    continue
                if not contact["name"] and len(line) > 2 and "dasny" not in low:
                    contact["name"] = line

            if contact["name"] or contact["email"] or contact["phone"]:
                contacts.append(contact)

        return contacts

    def _parse_location(self, loc_str: Optional[str]) -> tuple[Optional[str], Optional[str], str, Optional[str]]:
        if not loc_str:
            return None, None, "NY", None
        loc_clean = _clean(loc_str)
        m_zip = re.search(r"\b(\d{5}(?:-\d{4})?)\b", loc_clean)
        loc_zip = m_zip.group(1) if m_zip else None

        loc_city = None
        m_city = re.search(r"([A-Za-z\s]+),\s*(?:NY|New York)", loc_clean)
        if m_city:
            loc_city = _clean(m_city.group(1))

        return loc_clean, loc_city, "NY", loc_zip

    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        """
        Paginates listing pages and collects opportunities.
        Applies keyword filter before limit, paginating until limit is met or max_pages reached.
        Filters by location after extraction.
        """
        if not self.setup_chrome():
            raise RuntimeError("Failed to initialize Chrome driver for DASNY.")

        try:
            seen_urls = set()
            matched_records: List[Dict[str, Any]] = []
            page = 0
            max_pages = 10
            kw = (params.keyword or "").strip().lower()

            target_city = (params.city or "").strip().lower()
            target_state = (params.us_state or "").strip().upper()
            target_loc = (params.location or "").strip().lower()

            while len(matched_records) < params.limit and page < max_pages:
                if self.ctx.should_cancel():
                    break

                page_url = f"{LISTING_URL}?page={page}"
                logger.info("Loading DASNY listing page %d: %s", page, page_url)
                retry_driver_call(lambda: self.driver.get(page_url), action_name=f"get {page_url}")
                time.sleep(2)

                cards = self.driver.find_elements(By.CSS_SELECTOR, "div.rfp-bid-wrapper")
                if not cards:
                    logger.info("No more opportunity cards on page %d. Stopping.", page)
                    break

                page_urls = []
                for card in cards:
                    try:
                        link_el = card.find_element(
                            By.XPATH,
                            ".//div[contains(@class,'rfp-bid-links')]//a[normalize-space(text())='View the full details for this opportunity']",
                        )
                        href = (link_el.get_attribute("href") or "").split("#")[0].rstrip("/")
                        if href and href not in seen_urls:
                            seen_urls.add(href)
                            page_urls.append(href)
                    except Exception:
                        continue

                for detail_url in page_urls:
                    if self.ctx.should_cancel():
                        break
                    record = self._extract_detail(detail_url)
                    if not record:
                        continue

                    # Apply keyword filter
                    if kw:
                        text_corpus = f"{record.get('title', '')} {record.get('description', '')} {record.get('solicitation_number', '')}".lower()
                        if kw not in text_corpus:
                            continue

                    # Apply location filter
                    if target_city and target_city not in (record.get("location_city") or "").lower():
                        continue
                    if target_state and target_state != (record.get("location_state") or "NY").upper():
                        continue
                    if target_loc and target_loc not in (record.get("location_raw") or "").lower():
                        continue

                    matched_records.append(record)
                    yield record

                    if len(matched_records) >= params.limit:
                        logger.info("Reached target limit of %d records. Stopping.", params.limit)
                        break

                page += 1

        finally:
            self.close()

    def to_standard(self, raw: Dict[str, Any]) -> StandardRecord:
        """Map raw DASNY dict to StandardRecord."""
        solicitation_number = raw.get("solicitation_number")
        contacts = raw.get("contacts") or []
        first_contact = contacts[0] if contacts else {}

        return StandardRecord(
            source_code=self.meta.id,
            record_kind=self.meta.record_kind,
            external_id=solicitation_number,
            source_url=raw.get("source_url"),
            title=raw.get("title"),
            description=raw.get("description"),
            organization_name="Dormitory Authority of the State of New York (DASNY)",
            contact_name=first_contact.get("name"),
            contact_title=first_contact.get("title") or first_contact.get("role"),
            email=first_contact.get("email"),
            phone=first_contact.get("phone"),
            website=raw.get("source_url"),
            city=raw.get("location_city"),
            us_state=raw.get("location_state") or "NY",
            postal_code=raw.get("location_zip"),
            category="Public Construction",
            due_at=raw.get("due_at"),
            extra={
                "solicitation_number": solicitation_number,
                "location_raw": raw.get("location_raw"),
                "due_date_raw": raw.get("due_date_raw"),
                "all_contacts": contacts,
            },
        )

    def close(self) -> None:
        """Safely close driver instance."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.debug("Error closing DASNY driver: %s", e)
            self.driver = None
        super().close()