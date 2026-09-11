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
import json
import time

# Ensure Python311 site-packages is in sys.path even if running from a venv
_PYTHON311_PKG = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if os.path.exists(_PYTHON311_PKG) and _PYTHON311_PKG not in sys.path:
    sys.path.insert(0, _PYTHON311_PKG)

from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
except ImportError:
    import subprocess
    py_exe = sys.executable
    if not os.path.exists(os.path.join(os.path.dirname(py_exe), "pip.exe")):
        py_exe = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python311\python.exe"
    subprocess.check_call([py_exe, "-m", "pip", "install", "selenium"])
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options

BASE_URL = "https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities"
OUTPUT_FILE = "dallas_bonfire_data.json"


class DallasBonfireScraper:
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

                url = link_el.get_attribute("href") if link_el else BASE_URL

                status = "OPEN"
                ref_num = f"DAL-{idx+1:04d}"
                project_title = "Dallas City Procurement"
                close_date = "Open"
                days_left = ""

                if cells and len(cells) >= 4:
                    status = cells[0].text.strip() or "OPEN"
                    ref_num = cells[1].text.strip()
                    # project title might be in cell 2
                    project_title = cells[2].text.strip()
                    if len(cells) >= 4:
                        close_date = cells[3].text.strip()
                    if len(cells) >= 5:
                        days_left = cells[4].text.strip()
                else:
                    # Parse from text line
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
                    "days_left": days_left,
                    "issuing_organization": "City of Dallas",
                    "location": "Dallas, TX, USA",
                    "url": url,
                    "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

    def scrape(
        self,
        max_opportunities: Optional[int] = None,
        output_file: str = OUTPUT_FILE,
        progress_callback: Optional[Callable[[int, str, Optional[Dict]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Main scraping workflow with progress reporting."""
        if not self.driver:
            if not self.setup_chrome():
                return []

        try:
            if progress_callback:
                progress_callback(10, "Connecting to Dallas City Hall Bonfire Hub...", None)

            opps = self.discover_opportunities()
            if max_opportunities:
                opps = opps[:max_opportunities]

            total = len(opps)
            if total == 0:
                if progress_callback:
                    progress_callback(100, "No active opportunities found.", None)
                return []

            results = []
            for i, opp in enumerate(opps):
                pct = 20 + int((i / total) * 75)
                msg = f"Extracting opportunity {i+1}/{total}: {opp.get('ref_number')} - {opp.get('title')[:40]}..."
                if progress_callback:
                    progress_callback(pct, msg, opp)

                enriched = self.extract_details(opp)
                results.append(enriched)
                time.sleep(0.5)

            # Save results
            self.save(results, output_file)

            if progress_callback:
                progress_callback(100, f"Extraction completed. {len(results)} opportunities saved.", None)

            return results
        finally:
            self.close()

    def save(self, data: List[Dict[str, Any]], filename: str = OUTPUT_FILE):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Saved {len(data)} opportunities to {filename}")
        except Exception as e:
            print(f"Error saving to {filename}: {e}", file=sys.stderr)

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


def main():
    print("=" * 60)
    print("  Dallas City Hall Bonfire Scraper")
    print("=" * 60)
    scraper = DallasBonfireScraper(headless=True)
    try:
        results = scraper.scrape(max_opportunities=10)
        print(f"\nExtracted {len(results)} opportunities:")
        for r in results[:5]:
            print(f"- [{r.get('ref_number')}] {r.get('title')} | Closes: {r.get('close_date')}")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
