from __future__ import annotations
import re
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from scrappers.base import BaseScraper, ScrapeParams, ScrapeContext, ScraperMeta, StandardRecord, LoginFailed, SourceBlocked, JobCancelled
from scrappers.driver import make_driver
from scrappers.utils import clean, to_json_safe, parse_local_dt, state_code
from settings import settings

logger = logging.getLogger(__name__)


def parse_detail_content(html):
    """Read the current portal's structured ad fields and individual contacts."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.select_one('.page-content')
    if root is None:
        return {}
    fields = {}
    for label in root.select('.line-label'):
        value = label.find_next_sibling(class_='line-value')
        if value:
            fields[clean(label.get_text(' ', strip=True)).rstrip(':').casefold()] = clean(value.get_text(' ', strip=True))
    title = root.select_one('h2')
    description = root.select_one('#ad-section-description')
    contacts = []
    for card in root.select('#ad-section-contact-info .card'):
        name = card.select_one('.card-title .me-2')
        role = card.select_one('.card-subtitle')
        organization = card.select_one('.card-text strong')
        email = card.select_one('a[href^="mailto:"]')
        phone = card.select_one('a[href^="tel:"]')
        contacts.append({'name': clean(name.get_text(' ', strip=True)) if name else None,
            'title': clean(role.get_text(' ', strip=True)) if role else None,
            'organization': clean(organization.get_text(' ', strip=True)) if organization else None,
            'email': email['href'][7:].split('?')[0].strip() if email else None,
            'phone': phone['href'][4:] if phone else None})
    return {'fields': fields, 'title': clean(title.get_text(' ', strip=True)) if title else None,
        'description': clean(description.get_text(' ', strip=True)) if description else None, 'contacts': contacts}

# Skip language words
_LANGUAGE_SAMPLE = {
    'abkhaz', 'acehnese', 'acholi', 'afrikaans', 'albanian', 'amharic',
    'arabic', 'armenian', 'assamese', 'awadhi', 'aymara', 'azerbaijani',
    'balinese', 'baluchi', 'bambara', 'bashkir', 'basque', 'belarusian',
    'bengali', 'betawi', 'bhojpuri', 'bosnian', 'breton', 'bulgarian',
    'buryat', 'cantonese', 'catalan', 'cebuano', 'chechen', 'chichewa',
    'corsican', 'croatian', 'danish', 'dhivehi', 'esperanto', 'faroese',
    'fijian', 'filipino', 'finnish', 'french', 'frisian', 'friulian',
    'fulani', 'galician', 'georgian', 'german', 'guarani', 'gujarati',
    'hawaiian', 'hebrew', 'hiligaynon', 'hungarian', 'icelandic', 'ilocano',
    'indonesian', 'italian', 'japanese', 'javanese', 'kalaallisut', 'kannada',
    'kanuri', 'kapampangan', 'kazakh', 'kikongo', 'kituba', 'konkani',
    'korean', 'kyrgyz', 'latvian', 'lingala', 'lithuanian', 'luganda',
    'luxembourgish', 'macedonian', 'malagasy', 'malayalam', 'maltese',
    'marathi', 'marshallese', 'mongolian', 'nepali', 'norwegian', 'occitan',
    'pangasinan', 'papiamento', 'pashto', 'persian', 'polish', 'quechua',
    'romani', 'romanian', 'russian', 'samoan', 'sanskrit', 'sepedi',
    'serbian', 'sesotho', 'sindhi', 'sinhala', 'slovak', 'slovenian',
    'somali', 'spanish', 'sundanese', 'swahili', 'swedish', 'tahitian',
    'tibetan', 'tongan', 'tswana', 'tumbuka', 'turkish', 'turkmen',
    'ukrainian', 'uyghur', 'venetian', 'vietnamese', 'yiddish', 'yoruba',
    'zapotec', 'telugu', 'tamil',
}

def _is_language_word(word: str) -> bool:
    return word.lower().strip('.,;:') in _LANGUAGE_SAMPLE

def _looks_like_language_blob(text: str) -> bool:
    if not text:
        return False
    words = text.split()
    if len(words) < 5:
        return False
    lang_count = sum(1 for w in words if _is_language_word(w))
    return lang_count / len(words) > 0.35

class NyscrScraper(BaseScraper):
    meta = ScraperMeta(
        id="nyscr",
        name="New York State Contract Reporter",
        description="Extracts state procurement contracts, RFPs, and bid opportunities from the New York State Contract Reporter portal.",
        record_kind="opportunity",
        category="Statewide Contracts",
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
        required_env=["NYSCR_USERNAME", "NYSCR_PASSWORD"],
        default_limit=20,
        max_limit=100,
    )

    headless_default = False

    def __init__(self, ctx: Optional[ScrapeContext] = None, headless: Optional[bool] = None) -> None:
        if headless is None:
            headless = getattr(settings, 'NYSCR_HEADLESS', False)
        super().__init__(ctx, headless)
        self.driver = None
        self.username = getattr(settings, "NYSCR_USERNAME", None)
        self.password = getattr(settings, "NYSCR_PASSWORD", None)
        self.max_pages = getattr(settings, "NYSCR_MAX_PAGES", 20)
        self.wait = None
        self._login_failures = 0

    def check_credentials(self) -> tuple[bool, Optional[str]]:
        if not self.username or not self.password:
            return False, "NYSCR_USERNAME and NYSCR_PASSWORD must be set in environment variables."
        return True, None

    def setup_chrome(self) -> bool:
        if self.driver:
            return True
        logger.info("Setting up Chrome for NYSCR...")
        try:
            debugger_addr = getattr(settings, 'NYSCR_DEBUGGER_ADDRESS', '') or None
            if debugger_addr:
                import socket
                try:
                    host, port = debugger_addr.split(":")
                    with socket.create_connection((host, int(port)), timeout=0.5):
                        pass
                except Exception:
                    logger.warning("Configured NYSCR debugger address %s is unreachable; launching fresh browser instance.", debugger_addr)
                    debugger_addr = None

            self.driver = make_driver(headless=self.headless,
                debugger_address=debugger_addr)
            self.wait = WebDriverWait(self.driver, 15)
            logger.info("Chrome ready for NYSCR.")
            return True
        except Exception as e:
            logger.error("Chrome setup failed for NYSCR: %s", e)
            return False

    def close(self):
        if self.driver:
            try:
                if getattr(settings, 'NYSCR_DEBUGGER_ADDRESS', ''):
                    try:
                        self.driver.service.stop()
                    except Exception:
                        self.driver.quit()
                else:
                    self.driver.quit()
            except Exception:
                pass
            self.driver = None
        super().close()

    def _detect_recaptcha(self) -> bool:
        body = ' '.join(self.driver.find_element(By.TAG_NAME, 'body').text.casefold().split())
        if 'unable to verify' in body and 'robot' in body:
            return True
        return any(frame.is_displayed() for frame in self.driver.find_elements(By.CSS_SELECTOR,
            'iframe[src*="recaptcha"][title*="challenge"]'))

    def _wait_for_user_captcha(self):
        self.ctx.log("info", "Waiting for user to solve CAPTCHA...")
        if not self.ctx.wait_for_user("NYSCR sign-in: complete robot verification in the browser window, click Sign In, then press Resume."):
            raise SourceBlocked('NYSCR requires interactive robot verification before sign-in can complete.')

    def login(self) -> bool:
        try:
            if self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Log off') or contains(text(), 'Logout')]"):
                self.ctx.log('info', 'Reusing the signed-in NYSCR browser session.')
                return True
            self.ctx.log("info", "Opening NYSCR login page...")
            self.driver.get("https://www.nyscr.ny.gov/Account/Login")
            time.sleep(2)

            user_field = self.wait.until(EC.presence_of_element_located((By.ID, "Username")))
            pass_field = self.wait.until(EC.presence_of_element_located((By.ID, "Password")))

            user_field.clear()
            user_field.send_keys(self.username)
            pass_field.clear()
            pass_field.send_keys(self.password)

            if self._detect_recaptcha():
                self._wait_for_user_captcha()

            # After continue (or if no captcha), if login form still showing, click submit once and wait up to 15s
            # After continue (or if no captcha), if login form still showing, click submit once and wait up to 15s
            if "login" in self.driver.current_url.lower():
                try:
                    submit = self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
                    if submit.is_displayed():
                        submit.click()
                        time.sleep(2)
                    else:
                        logger.debug('Login submit control is not displayed.')
                except Exception as e:
                    logger.debug('Login submit control unavailable: %s', type(e).__name__)
                    pass

                # wait up to 15s
                for _ in range(5):
                    if "login" not in self.driver.current_url.lower():
                        break
                    time.sleep(3)

            if self._detect_recaptcha():
                self._wait_for_user_captcha()

            # Confirm login worked
            # Authentication redirects before the portal finishes rendering its
            # robot-verification error. Wait for an actual authenticated marker.
            try:
                WebDriverWait(self.driver, 15).until(lambda driver: self._detect_recaptcha() or
                    bool(driver.find_elements(By.XPATH, "//a[contains(text(), 'Log off') or contains(text(), 'Logout')]")))
            except TimeoutException:
                pass
            if self._detect_recaptcha():
                self._wait_for_user_captcha()
            if "login" in self.driver.current_url.lower():
                raise LoginFailed("Login failed: Still on login page after attempt.")

            logout = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Log off') or contains(text(), 'Logout')]")
            if not logout:
                username_field_still_there = self.driver.find_elements(By.ID, "Username")
                if any(field.is_displayed() for field in username_field_still_there):
                    raise LoginFailed("Login failed: Username field is still visible.")

            self.ctx.log("info", "NYSCR login successful.")
            return True
        except TimeoutException:
            raise LoginFailed("Login failed: Elements not found on login page.")
        except Exception as e:
            if isinstance(e, (LoginFailed, SourceBlocked, JobCancelled)):
                raise
            raise LoginFailed(f"Login error: {e}")

    def iter_opportunity_ids(self) -> Iterator[str]:
        self.driver.get("https://www.nyscr.ny.gov/Ads/Search?BidFilter=Open")
        time.sleep(3)

        seen = set()
        page = 1

        while page <= self.max_pages:
            self.check_cancel()
            self.ctx.log("info", f"Harvesting opportunity links from page {page}...")

            # Capture href strings before yielding: detail extraction opens/closes
            # tabs and the portal can replace the listing DOM in the meantime.
            hrefs = self.driver.execute_script("return Array.from(document.querySelectorAll('a[href*=\"/Ads/Details/\"]'), a => a.href)")
            for href in hrefs:
                opp_id = href.rstrip('/').split('/')[-1].split('?')[0]
                if opp_id.isdigit() and opp_id not in seen:
                    seen.add(opp_id)
                    yield opp_id

            if not self._go_to_next_page(page):
                break
            page += 1

    def _go_to_next_page(self, current_page: int) -> bool:
        next_page_num = current_page + 1

        candidate = None
        try:
            for el in self.driver.find_elements(By.XPATH, f"//button[normalize-space(text())='{next_page_num}'] | //a[normalize-space(text())='{next_page_num}']"):
                if el.is_displayed() and el.is_enabled():
                    candidate = el
                    break
        except Exception:
            pass

        if not candidate:
            try:
                for el in self.driver.find_elements(By.XPATH, "//button[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'NEXT')] | //a[contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'NEXT')]"):
                    if el.is_displayed() and el.is_enabled():
                        candidate = el
                        break
            except Exception:
                pass

        if not candidate:
            return False

        first_id_before = None
        sentinel = None
        try:
            sentinel = self.driver.find_element(By.XPATH, "//a[contains(@href,'/Ads/Details/')]")
            href_before = sentinel.get_attribute('href') or ''
            first_id_before = href_before.rstrip('/').split('/')[-1].split('?')[0]
        except Exception:
            pass

        try:
            href = candidate.get_attribute('href') or ''
            onclick = candidate.get_attribute('onclick') or ''
            pb_match = re.search(r"__doPostBack\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]", href + onclick, re.IGNORECASE)

            if pb_match:
                self.driver.execute_script(f"__doPostBack('{pb_match.group(1)}', '{pb_match.group(2)}');")
            else:
                self.driver.execute_script("arguments[0].click();", candidate)
        except Exception:
            return False

        try:
            if sentinel:
                WebDriverWait(self.driver, 15).until(EC.staleness_of(sentinel))
            else:
                time.sleep(3)
        except TimeoutException:
            return False

        try:
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/Ads/Details/')]")))
        except TimeoutException:
            return False

        if first_id_before:
            try:
                first_link_after = self.driver.find_element(By.XPATH, "//a[contains(@href,'/Ads/Details/')]")
                href_after = first_link_after.get_attribute('href') or ''
                first_id_after = href_after.rstrip('/').split('/')[-1].split('?')[0]
                if first_id_after == first_id_before:
                    return False
            except Exception:
                pass

        return True

    def _expand_all(self):
        selectors = ["button[aria-expanded='false']"]
        for sel in selectors:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    try:
                        if el.is_displayed() and el.is_enabled():
                            self.driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.3)
                    except Exception:
                        pass
            except Exception:
                pass

    def _get_title(self, body_text: str) -> Optional[str]:
        # Title sits between "Ad details" and the first header field line
        m = re.search(r'Ad details\s*\n+\s*(.+?)\s*\n', body_text, re.IGNORECASE)
        if m:
            candidate = clean(m.group(1))
            if candidate and not re.match(r'^[\d\s/:\-]+$', candidate):
                if not re.match(r'^\d{5,}$', candidate):
                    # Match skip words as whole words
                    low = candidate.lower()
                    bad = [r'\bcontract reporter\b', r'\blogin\b', r'\bsearch\b', r'\bdashboard\b',
                           r'\ball open\b', r'\bad details\b', r'\bhome \|\b', r'\bcontracting opportunities\b',
                           r"\bhere's how\b", r'\bnew york state contract reporter\b']
                    if not any(re.search(b, low) for b in bad):
                        return candidate
        return None

    def _field(self, container_text: str, label: str) -> Optional[str]:
        pattern = re.compile(r'\b' + re.escape(label) + r'\s*:?\s*\n?\s*(.+?)(?:\n|$)', re.IGNORECASE)
        m = pattern.search(container_text)
        if m:
            val = clean(m.group(1))
            if val and not val.endswith(':'):
                return val
        return None

    def extract_clean_data(self, opp_id: str) -> Optional[Dict[str, Any]]:
        url = f"https://www.nyscr.ny.gov/Ads/Details/{opp_id}"

        original_window = self.driver.current_window_handle
        self.driver.execute_script("window.open('');")
        self.driver.switch_to.window(self.driver.window_handles[-1])

        try:
            self.driver.get(url)
            time.sleep(2)

            if "login" in self.driver.current_url.lower():
                self._login_failures += 1
                if self._login_failures >= 2:
                    raise LoginFailed("Session expired twice in a row.")

                # The current tab is redirected to login. Close it.
                self.driver.close()
                self.driver.switch_to.window(original_window)

                # Open a temporary tab just for logging in again so we don't ruin the search page
                self.driver.execute_script("window.open('');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                try:
                    self.login()
                finally:
                    self.driver.close()
                    self.driver.switch_to.window(original_window)

                return self.extract_clean_data(opp_id)

            self._login_failures = 0
            self._expand_all()
            time.sleep(1)

            try:
                container = self.driver.find_element(By.CSS_SELECTOR, '.page-content')
                body_text = container.text
            except Exception:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text

            parsed = parse_detail_content(self.driver.page_source)
            title = parsed.get('title') or self._get_title(body_text)
            if not title:
                # Fallback 1: Page title
                page_title = self.driver.title
                if page_title and " - " in page_title:
                    title = page_title.split(" - ")[0].strip()
                elif page_title and "Contract Reporter" not in page_title and "Contracting Opportunities" not in page_title:
                    title = page_title.strip()

                # Fallback 2: h1/h2 tags
                if not title:
                    try:
                        headings = self.driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4")
                        for h in headings:
                            txt = clean(h.text)
                            if txt and len(txt) > 5 and not any(skip in txt.lower() for skip in ['login', 'search', 'contract reporter', 'contracting opportunities', 'ad details']):
                                title = txt
                                break
                    except Exception:
                        pass

            fields = parsed.get('fields', {})
            cr_number = fields.get('cr#') or self._field(body_text, 'CR#')
            agency = fields.get('agency') or self._field(body_text, 'Agency')
            due_date_raw = fields.get('due date') or self._field(body_text, 'Due date')
            location_raw = fields.get('location') or self._field(body_text, 'Location')
            category_raw = fields.get('category') or self._field(body_text, 'Category')
            description = parsed.get('description') or self._get_description(body_text)
            contact_details = parsed.get('contacts') or self._get_contact()

            # Documents inside Documents section
            documents = self._get_documents(body_text)
            updates, bid_results, awards = self._get_updates_results(body_text)

            budget = self._parse_budget(description or '')

            loc_address, loc_city, loc_state, loc_zip = self._parse_location(location_raw)

            due_dt = parse_local_dt(due_date_raw, 'America/New_York')

            return {
                "id": opp_id,
                "url": url,
                "title": title,
                "cr_number": cr_number,
                "agency": agency,
                "due_date_raw": due_date_raw,
                "due_dt": due_dt,
                "location_raw": location_raw,
                "loc_city": loc_city,
                "loc_state": loc_state,
                "loc_zip": loc_zip,
                "category": category_raw,
                "description": description,
                "contacts": contact_details,
                "documents": documents,
                "updates": updates,
                "bid_results": bid_results,
                "awards": awards,
                "budget": budget,
            }
        finally:
            if self.driver.current_window_handle != original_window:
                try:
                    self.driver.close()
                except Exception:
                    pass
            self.driver.switch_to.window(original_window)

    def _get_description(self, text: str) -> Optional[str]:
        # Simple extraction
        m = re.search(r'\b(?:General\s+)?Description\b(.*)', text, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        rest = m.group(1).lstrip(':').strip()
        lines = []
        for line in rest.split('\n'):
            line = clean(line)
            if not line:
                continue
            low = line.lower()
            if low in {'contact info', 'contact information', 'documents', 'updates', 'bid results', 'awards'}:
                break
            lines.append(line)
        desc = ' '.join(lines)
        return desc if len(desc) > 20 else None

    def _get_contact(self) -> List[Dict[str, str]]:
        contacts = []
        try:
            # find the contact section
            # For simplicity, extract from the page
            contact_headers = self.driver.find_elements(By.XPATH, "//*[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = 'contact info' or translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = 'contact information']")
            if contact_headers:
                contact_section = contact_headers[0].find_element(By.XPATH, "./following-sibling::div")
                lines = [clean(line) for line in contact_section.text.split('\n') if clean(line)]
                # VERY simplified contact extraction
                current_contact = {}
                for line in lines:
                    if 'ext. n/a' in line.lower():
                        line = line.lower().replace('ext. n/a', '').strip()
                    if '@' in line:
                        current_contact['email'] = line
                    elif re.search(r'\d{3}[\s.-]?\d{3}[\s.-]?\d{4}', line):
                        current_contact['phone'] = line
                    elif not current_contact.get('name') and len(line) < 40 and not any(k in line.lower() for k in ['contact', 'agency', 'department']):
                        current_contact['name'] = line
                    elif not current_contact.get('organization') and any(k in line.lower() for k in ['agency', 'department', 'division', 'office']):
                        current_contact['organization'] = line

                if current_contact:
                    contacts.append(current_contact)
        except Exception:
            pass
        return contacts

    def _get_documents(self, body_text: str) -> List[str]:
        docs = []
        try:
            doc_headers = self.driver.find_elements(By.XPATH, "//*[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = 'documents']")
            if doc_headers:
                doc_section = doc_headers[0].find_element(By.XPATH, "./following-sibling::div")
                links = doc_section.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href")
                    if href and 'DownloadDailyIssue' not in href and 'Search' not in href:
                        docs.append(href)
        except Exception:
            pass
        return docs

    def _get_updates_results(self, text: str) -> tuple[List[str], List[str], List[str]]:
        updates = []
        results = []
        awards = []

        def extract_section(name: str) -> List[str]:
            m = re.search(r'^' + name + r'\s*\n(.*?)(?=\n(?:Documents|Contact Info|Updates|Bid Results|Awards|Accessibility|$))', text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if m:
                lines = [clean(l) for l in m.group(1).split('\n') if clean(l) and l.lower() not in ('no updates found', 'bid results have not been entered', 'awards have not been entered')]
                return lines
            return []

        updates = extract_section('Updates')
        results = extract_section('Bid Results')
        awards = extract_section('Awards')

        # Awardee split
        parsed_awards = []
        for line in awards:
            parts = re.split(r':|\b(?:is|to)\b', line, maxsplit=1)
            parsed_awards.append(parts[0].strip() if len(parts) == 1 else parts[1].strip())

        return updates, results, parsed_awards

    def _parse_budget(self, text: str) -> str:
        # Require \b after million|m|k|thousand
        m = re.search(r'\$[\d,]+(?:\.\d+)?\s*(?:million\b|m\b|k\b|thousand\b)?', text, re.IGNORECASE)
        return m.group(0) if m else None

    def _parse_location(self, raw: str) -> tuple[str, str, str, str]:
        if not raw:
            return None, None, None, None
        zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', raw)
        z = zip_match.group(1) if zip_match else None

        # State just before zip
        state = None
        if zip_match:
            before_zip = raw[:zip_match.start()].strip().rstrip(',')
            words = before_zip.split()
            if words:
                st = state_code(words[-1])
                if st:
                    state = st

        return raw, None, state, z

    def _parse_public_card(self, item) -> Optional[Dict[str, Any]]:
        opp_id = item.get("data-ad-id")
        if not opp_id:
            return None

        title_el = item.select_one(".bg-primary.text-light")
        title = clean(title_el.get_text(" ", strip=True)) if title_el else None
        if not title:
            title = item.get("title")

        fields = {}
        for row in item.select(".d-flex"):
            lbl_el = row.select_one(".w-exact-8")
            if lbl_el:
                lbl = clean(lbl_el.get_text(" ", strip=True)).rstrip(":").casefold()
                val_el = lbl_el.find_next_sibling("div")
                if val_el:
                    fields[lbl] = clean(val_el.get_text(" ", strip=True))

        cr_number = fields.get("cr#") or opp_id
        company = fields.get("company")
        agency = fields.get("agency") or company
        division = fields.get("division")
        issue_date = fields.get("issue date")
        due_date_raw = fields.get("ad end date") or fields.get("due date")
        category = fields.get("category")
        ad_type = fields.get("ad type")
        location_raw = fields.get("location") or "NY"
        _, loc_city, loc_state, loc_zip = self._parse_location(location_raw)

        due_dt = parse_local_dt(due_date_raw, 'America/New_York') if due_date_raw else None

        desc_parts = []
        if agency:
            desc_parts.append(f"Agency/Company: {agency}")
        if division:
            desc_parts.append(f"Division: {division}")
        if location_raw and location_raw != "NY":
            desc_parts.append(f"Location: {location_raw}")
        if category:
            desc_parts.append(f"Category: {category}")
        if ad_type:
            desc_parts.append(f"Type: {ad_type}")
        description = f"{title}. " + "; ".join(desc_parts) if title else None

        return {
            "id": opp_id,
            "url": f"https://www.nyscr.ny.gov/Ads/Details/{opp_id}",
            "title": title,
            "cr_number": cr_number,
            "agency": agency,
            "division": division,
            "issue_date": issue_date,
            "due_date_raw": due_date_raw,
            "due_dt": due_dt,
            "location_raw": location_raw,
            "loc_city": loc_city,
            "loc_state": loc_state or "NY",
            "loc_zip": loc_zip,
            "category": category,
            "description": description,
            "contacts": [],
            "documents": [],
            "updates": [],
            "bid_results": [],
            "awards": [],
            "budget": None,
        }

    def iter_public_opportunities(self) -> Iterator[Dict[str, Any]]:
        from bs4 import BeautifulSoup
        search_url = "https://www.nyscr.ny.gov/Ads/Search?BidFilter=Open"
        logger.info("Harvesting public NYSCR opportunities from %s", search_url)
        self.driver.get(search_url)
        time.sleep(3)

        seen_ids = set()
        page = 1
        while page <= self.max_pages:
            self.check_cancel()
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            items = soup.select(".opp-list-item")
            if not items:
                logger.warning("No .opp-list-item elements found on page %d", page)
                break

            for item in items:
                self.check_cancel()
                opp_id = item.get("data-ad-id")
                if not opp_id or opp_id in seen_ids:
                    continue
                seen_ids.add(opp_id)
                data = self._parse_public_card(item)
                if data:
                    yield data

            if not self._go_to_next_page(page):
                break
            page += 1

    def scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]:
        if not self.setup_chrome():
            return

        logged_in = False
        try:
            logged_in = self.login()
        except (LoginFailed, SourceBlocked, Exception) as e:
            self.ctx.log("warning", f"NYSCR login was not completed ({e}); proceeding with public open opportunities.")

        try:
            if logged_in:
                n = 0
                for opp_id in self.iter_opportunity_ids():
                    if n >= params.limit:
                        break
                    data = self.extract_clean_data(opp_id)
                    if data:
                        n += 1
                        self.ctx.progress(100.0 * n / params.limit, f"{n}/{params.limit}")
                        yield data
            else:
                n = 0
                for data in self.iter_public_opportunities():
                    if n >= params.limit:
                        break
                    n += 1
                    self.ctx.progress(100.0 * n / params.limit, f"{n}/{params.limit}")
                    yield data

        finally:
            pass # closed in run()

    def to_standard(self, raw: Dict[str, Any]) -> StandardRecord:
        agency = (
            raw.get('agency')
            or raw.get('issuing_organization')
            or raw.get('organization_name')
        )
        contacts = raw.get('contacts')
        if not contacts and raw.get('contact_details'):
            cd = raw.get('contact_details')
            contacts = [cd] if isinstance(cd, dict) else cd
        contacts = contacts or []
        contact = contacts[0] if contacts else {}
        org = agency or contact.get('organization') or "State of New York"

        url = raw.get('url') or raw.get('source_url')
        ext_id = raw.get('cr_number') or raw.get('opp_id') or raw.get('id') or raw.get('source_id')
        if not ext_id and url:
            m = re.search(r'/Details/(\d+)', url)
            if m:
                ext_id = m.group(1)

        city = raw.get('loc_city') or raw.get('location_city') or raw.get('city')
        category = raw.get('category') or raw.get('categories')

        due_at = raw.get('due_dt') or raw.get('due_at')
        if not due_at:
            due_raw = raw.get('due_date_raw') or raw.get('due_date') or raw.get('bid_deadline')
            if due_raw:
                due_at = parse_local_dt(due_raw, 'America/New_York')

        return StandardRecord(
            source_code=self.meta.id.lower(),
            record_kind=self.meta.record_kind,
            external_id=str(ext_id) if ext_id is not None else None,
            source_url=url,
            title=raw.get('title'),
            description=raw.get('description'),
            organization_name=org,
            contact_name=contact.get('name') or raw.get('contact_name'),
            contact_title=contact.get('title') or raw.get('contact_title'),
            email=contact.get('email') or raw.get('email'),
            phone=contact.get('phone') or raw.get('phone'),
            website=raw.get('website'),
            city=city,
            us_state=raw.get('loc_state') or raw.get('us_state') or 'NY',
            postal_code=raw.get('loc_zip') or raw.get('location_zip') or raw.get('postal_code'),
            category=category,
            due_at=due_at,
            extra=to_json_safe({
                **raw,
                "all_contacts": contacts
            })
        )
