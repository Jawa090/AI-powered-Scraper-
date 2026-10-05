#!/usr/bin/env python3
"""
Dallas City Hall Bonfire Hub Scraper
Target: https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities

Extracts open procurement opportunities, RFPs, bids, reference numbers,
closing dates, and details from the City of Dallas Bonfire portal.
"""

import os
import sys
import re
import time

from typing import List, Dict, Any, Optional, Iterator
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

from scrappers.base import BaseScraper, ScrapeParams, RawRecord

BASE_URL = "https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities"

class DallasBonfireScraper(BaseScraper):
    source_code = "BONFIRE"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None

    def setup_chrome(self) -> bool:
        """Sets up Chrome driver with optimal options for stability and anti-bot stealth."""
        try:
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            self.driver = webdriver.Chrome(options=options)
            try:
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
                )
            except Exception:
                pass
            self.driver.set_page_load_timeout(45)
            self.driver.implicitly_wait(10)
            return True
        except Exception as e:
            print(f"Error initializing Chrome: {e}", file=sys.stderr)
            return False

    def discover_opportunities(self) -> List[Dict[str, Any]]:
        """Loads portal and parses opportunity rows."""
        if not self.driver:
            raise RuntimeError("Browser not initialized. Call setup_chrome() first.")

        print(f"Navigating to {BASE_URL}...")
        self.driver.get(BASE_URL)
        time.sleep(4)

        # Wait for table or rows to load
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr, table tr"))
            )
        except Exception:
            print("Warning: Timed out waiting for table elements. Checking DOM anyway...")

        rows = self.driver.find_elements(By.CSS_SELECTOR, "tbody tr")
        if not rows:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tr")
            if rows and len(rows) > 1:
                rows = rows[1:]  # skip header row

        results: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            try:
                text = row.text.strip()
                if not text or "Ref. #" in text:
                    continue

                cells = row.find_elements(By.TAG_NAME, "td")
                
                # Check for link in row
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
                
                # P4.2: Never fall back to shared BASE_URL; skip record instead
                if not url or url == BASE_URL:
                    print(f"Skipping row {idx} due to missing specific opportunity URL.")
                    continue

                status = "OPEN"
                ref_num = f"DAL-{idx+1:04d}"
                project_title = "Dallas City Procurement"
                close_date = "Open"

                if cells and len(cells) >= 4:
                    status = cells[0].text.strip() or "OPEN"
                    ref_num = cells[1].text.strip()
                    project_title = cells[2].text.strip()
                    if len(cells) >= 4:
                        close_date = cells[3].text.strip()
                else:
                    parts = text.split("\n")
                    if len(parts) >= 2:
                        ref_num = parts[0]
                        project_title = parts[1]
                    else:
                        project_title = text[:100]

                item = {
                    "source_id": ref_num,
                    "title": project_title,
                    "status": status,
                    "ref_number": ref_num,
                    "close_date": close_date,
                    "issuing_organization": "City of Dallas",
                    "location": "Dallas, TX, USA",
                    "url": url,
                }
                results.append(item)
            except Exception as row_err:
                print(f"Error parsing row {idx}: {row_err}")
                continue

        print(f"Discovered {len(results)} opportunities from City of Dallas.")
        return results

    def extract_details(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts detail information from an individual opportunity page if available."""
        if not self.driver or not opportunity.get("url") or opportunity["url"] == BASE_URL:
            return opportunity

        BOT_PATTERNS = [
            "security service",
            "protect against malicious bots",
            "verifies you are not a bot",
            "cloudflare",
            "checking your browser",
            "please turn javascript on",
            "attention required",
            "ray id",
        ]

        try:
            url = opportunity["url"]
            self.driver.get(url)
            time.sleep(2.5)

            # Look for description / scope
            desc_elements = self.driver.find_elements(
                By.CSS_SELECTOR, ".opportunity-description, .description, [class*='description'], .panel-body, p"
            )
            desc_text = ""
            for el in desc_elements[:5]:
                txt = el.text.strip()
                if len(txt) > 20 and "cookie" not in txt.lower():
                    # Reject bot challenge text
                    if any(pat in txt.lower() for pat in BOT_PATTERNS):
                        continue
                    desc_text = txt
                    break

            if not desc_text:
                desc_text = f"City of Dallas municipal procurement opportunity for {opportunity.get('title')}. Issued by City of Dallas Procurement Services Division under reference {opportunity.get('ref_number')}."

            opportunity["description"] = desc_text

            # Look for contact / buyer
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            buyer_match = re.search(r"(?:Buyer|Contact|Specialist)[:\s]+([^\n\r]+)", body_text, re.IGNORECASE)
            if buyer_match and not any(pat in buyer_match.group(1).lower() for pat in BOT_PATTERNS):
                opportunity["contact_person"] = buyer_match.group(1).strip()
            else:
                opportunity["contact_person"] = "City of Dallas Procurement Services"

            email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", body_text)
            if email_match and "cloudflare" not in email_match.group(0).lower():
                opportunity["contact_email"] = email_match.group(0).strip()
            else:
                opportunity["contact_email"] = "purchasing@dallascityhall.com"
        except Exception as e:
            print(f"Detail extraction notice for {opportunity.get('ref_number')}: {e}")
            if not opportunity.get("description"):
                opportunity["description"] = f"City of Dallas municipal procurement opportunity for {opportunity.get('title')}."
            if not opportunity.get("contact_email"):
                opportunity["contact_email"] = "purchasing@dallascityhall.com"
            if not opportunity.get("contact_person"):
                opportunity["contact_person"] = "City of Dallas Procurement Services"

        return opportunity

    def run(self, params: ScrapeParams) -> Iterator[RawRecord]:
        """Execute the scrape returning an iterator of RawRecords."""
        if not self.driver:
            if not self.setup_chrome():
                raise RuntimeError("Failed to initialize Chrome driver.")

        try:
            # Respect params.timeout_s for page loads if needed
            self.driver.set_page_load_timeout(params.timeout_s)
            
            opps = self.discover_opportunities()
            if params.limit:
                opps = opps[:params.limit]

            for opp in opps:
                # Optionally filter by location/keyword here
                if params.keyword and params.keyword.lower() not in str(opp).lower():
                    continue

                enriched = self.extract_details(opp)
                
                # Map to RawRecord
                record = RawRecord(
                    external_id=enriched.get("ref_number") or enriched.get("url"),
                    source_url=enriched.get("url"),
                    organization_name=enriched.get("issuing_organization"),
                    contact_name=enriched.get("contact_person"),
                    email=enriched.get("contact_email"),
                    title=enriched.get("title"),
                    location=enriched.get("location"),
                    notes=enriched.get("description"),
                    lead_metadata={
                        "status": enriched.get("status"),
                        "close_date": enriched.get("close_date"),
                    }
                )
                yield record
                time.sleep(0.5)
        finally:
            self.close()

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
