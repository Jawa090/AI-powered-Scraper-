#!/usr/bin/env python3
"""
NYSCR Scraper - Accurate data extraction for 25 Open Opportunities
Maps data to the target schema precisely.

Key behaviors:
- Title:   read from the page heading after "Ad details" breadcrumb, NOT link text
- Contact: read name/phone/email/org from the Contact Info section DOM elements only
- Documents: only opportunity-specific attachments (skip DownloadDailyIssue and Search links)
- bid_results: only real bid data, not footer navigation
- Deduplication: seen_ids set prevents same opportunity appearing twice
- BidFilter=Open: only current open bids
"""

import sys
import os
import re
import json
import time
from datetime import datetime

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

# Ensure Python311 site-packages is in sys.path
_PYTHON311_PKG = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if os.path.exists(_PYTHON311_PKG) and _PYTHON311_PKG not in sys.path:
    sys.path.insert(0, _PYTHON311_PKG)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
except ImportError:
    import subprocess
    py_exe = sys.executable
    if not os.path.exists(os.path.join(os.path.dirname(py_exe), "pip.exe")):
        py_exe = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python311\python.exe"
    subprocess.check_call([py_exe, '-m', 'pip', 'install', 'selenium'])
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# Site-wide newsletter PDF token — skip these, they are NOT per-opportunity docs
_DAILY_ISSUE_TOKEN = 'DownloadDailyIssue'

# Footer/nav phrases that pollute bid_results
_FOOTER_PHRASES = {
    'download pdf', 'bookmark this ad', 'notify me if this ad updates',
    'new york state contract reporter', 'site links', 'my opportunities',
    'all open nyscr ads', 'nys business registry', 'edit my profile',
    'public information', 'contact us', 'accessibility',
    'policies and disclaimers', 'state resources', 'vendrep system',
    'empire state development', 'contracts systems', 'statewide financial system',
    'ny small business', 'agencies', 'app directory', 'counties', 'events',
    'programs', 'services',
}

# Language names (from the translate widget) that should never appear in contact
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


def _clean(text):
    """Strip and collapse whitespace."""
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _is_language_word(word):
    return word.lower().strip('.,;:') in _LANGUAGE_SAMPLE


def _looks_like_language_blob(text):
    """Return True if the text is mostly a list of language names."""
    if not text:
        return False
    words = text.split()
    if len(words) < 5:
        return False
    lang_count = sum(1 for w in words if _is_language_word(w))
    return lang_count / len(words) > 0.35


def _strip_language_blob(text):
    """Remove the translate-widget language list from a text block."""
    if not text:
        return text
    # The widget text ends just before "<<" or "Home |"
    cut = re.search(r'<<\s*Home\s*\|', text)
    if cut:
        text = text[cut.start():]
    # Also cut anything that is just a run of capitalised language names
    lines = []
    for line in text.split('\n'):
        if not _looks_like_language_blob(line):
            lines.append(line)
    return '\n'.join(lines).strip()


def _parse_date(raw):
    if not raw:
        return None
    raw = _clean(raw)
    # Strip time portion  e.g. "08/13/2026 02:30 PM"
    raw = re.sub(r'\s+\d{1,2}:\d{2}\s*(?:AM|PM)?', '', raw, flags=re.IGNORECASE).strip()
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', raw)
    if m:
        mo, dy, yr = m.groups()
        return f"{yr}-{int(mo):02d}-{int(dy):02d}"
    for fmt in ('%B %d, %Y', '%b %d, %Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

class NYSCRScraper:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.username = "kody2143"
        self.password = "TTHg6n*C7KuMES*"

    # ------------------------------------------------------------------ setup
    def setup_chrome(self):
        print("Setting up Chrome...")
        opts = Options()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        try:
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                svc = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=svc, options=opts)
            except Exception:
                self.driver = webdriver.Chrome(options=opts)
            self.wait = WebDriverWait(self.driver, 30)
            print("Chrome ready.")
            return True
        except Exception as e:
            print(f"Chrome setup failed: {e}")
            return False

    # ------------------------------------------------------------------ login
    def login(self):
        try:
            print("Opening login page...")
            self.driver.get("https://www.nyscr.ny.gov/Account/Login")
            time.sleep(2)
            self.wait.until(EC.presence_of_element_located((By.ID, "Username"))).send_keys(self.username)
            self.wait.until(EC.presence_of_element_located((By.ID, "Password"))).send_keys(self.password)
            print("\n" + "=" * 60)
            print("SOLVE THE reCAPTCHA in the browser window, then press ENTER.")
            print("=" * 60)
            input("\nPress ENTER after solving reCAPTCHA...")
            self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))).click()
            time.sleep(5)
            if "login" not in self.driver.current_url.lower():
                print("Login successful!")
                return True
            print(f"Login failed. URL: {self.driver.current_url}")
            return False
        except Exception as e:
            print(f"Login error: {e}")
            return False

    # ------------------------------------------------- collect opportunity IDs
    def get_open_opportunities(self, max_count=None):
        """
        Collect up to max_count unique open opportunity IDs.
        If max_count is None, collect ALL available opportunities.
        """
        limit_str = str(max_count) if max_count is not None else 'ALL'
        print(f"\nCollecting {limit_str} open opportunity IDs...")

        # Always start from page 1
        self.driver.get("https://www.nyscr.ny.gov/Ads/Search?BidFilter=Open")
        time.sleep(3)
        if "login" in self.driver.current_url.lower():
            print("Session expired on first load.")
            return []

        seen    = set()
        results = []
        page    = 1

        # Loop runs until: max_count reached (if set) OR no more pages
        while True:
            print(f"\n  [Page {page}] Harvesting opportunity links...")

            # ── Harvest all opportunity links on the current page ──────────
            links = self.driver.find_elements(
                By.XPATH, "//a[contains(@href,'/Ads/Details/')]"
            )
            added = 0
            for lnk in links:
                # Stop collecting if we hit the cap
                if max_count is not None and len(results) >= max_count:
                    break
                href   = lnk.get_attribute('href') or ''
                opp_id = href.rstrip('/').split('/')[-1].split('?')[0]
                if not opp_id.isdigit() or opp_id in seen:
                    continue
                seen.add(opp_id)
                results.append({
                    'id':  opp_id,
                    'url': f"https://www.nyscr.ny.gov/Ads/Details/{opp_id}"
                })
                added += 1

            print(f"  [Page {page}] Scraped {added} records. Total collected: {len(results)}")

            # Stop if cap reached
            if max_count is not None and len(results) >= max_count:
                print(f"  Reached requested cap of {max_count}. Stopping.")
                break

            # ── Navigate to the next page ─────────────────────────────────
            if not self._go_to_next_page(page):
                print(f"  [Page {page}] Last page reached. No more pages.")
                break
            page += 1

        print(f"\nCollection complete. {len(results)} unique opportunities found.\n")
        return results

    # ------------------------------------------------- pagination helper
    def _go_to_next_page(self, current_page):
        """
        Navigate to the next page of search results on NYSCR.

        NYSCR is ASP.NET WebForms. Pagination uses __doPostBack().
        The URL NEVER changes between pages — do NOT check current_url.

        Strategy:
          1. Find the Next (>) link or numbered page link.
          2. Record the first opportunity ID currently visible (pre-click sentinel).
          3. Trigger the click or __doPostBack call.
          4. Wait for the sentinel element to go stale (DOM replaced).
          5. Wait for new results to appear.
          6. Verify the first visible opportunity ID is DIFFERENT from before.

        Returns True  — successfully on the next page.
        Returns False — last page, or navigation failed.
        """
        from selenium.common.exceptions import TimeoutException

        next_page_num = current_page + 1
        print(f"  [Pagination] Current page: {current_page}. Attempting to go to page {next_page_num}...")

        # ── Step 1: Locate the Next / page-number link ────────────────────
        # NYSCR renders pagination links as:
        #   <a href="javascript:__doPostBack('ctl00$CP1$GridView1','Page$2')">2</a>
        #   <a href="javascript:__doPostBack('ctl00$CP1$GridView1','Page$2')">></a>
        candidate = None

        # Priority 1: NEXT button — real DOM shows <button>, not <a>,
        # with text "NEXT >" (uppercase, trailing arrow) — match case-insensitive substring
        try:
            for el in self.driver.find_elements(
                By.XPATH,
                "//button[contains(translate(normalize-space(.), "
                "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'NEXT')] "
                "| //a[contains(translate(normalize-space(.), "
                "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'NEXT')]"
            ):
                if el.is_displayed() and el.is_enabled():
                    candidate = el
                    break
        except Exception:
            pass

        # Priority 2: numbered page button/link (button OR anchor)
        if not candidate:
            try:
                for el in self.driver.find_elements(
                    By.XPATH,
                    f"//button[normalize-space(text())='{next_page_num}'] "
                    f"| //a[normalize-space(text())='{next_page_num}']"
                ):
                    if el.is_displayed() and el.is_enabled():
                        candidate = el
                        break
            except Exception:
                pass

        if not candidate:
            print(f"  [Pagination] No Next button or page-{next_page_num} link found.")
            print(f"  [Pagination] Dumping all visible pagination elements for diagnosis:")
            try:
                raw = self.driver.execute_script("""
                    var out = [];
                    document.querySelectorAll('a, button, span').forEach(function(el) {
                        var txt  = (el.innerText || '').trim();
                        var href = el.getAttribute('href') || '';
                        var oc   = el.getAttribute('onclick') || '';
                        var cls  = el.getAttribute('class') || '';
                        if (/page|next|prev|\\d/.test(txt + href + oc + cls)
                                && el.offsetParent !== null) {
                            out.push('[' + el.tagName + '] '
                                + 'text="' + txt.substring(0,40) + '" '
                                + 'href="' + href.substring(0,80) + '" '
                                + 'onclick="' + oc.substring(0,80) + '"');
                        }
                    });
                    return out.slice(0, 30).join('\\n');
                """)
                print(raw or "  (no elements found)")
            except Exception as de:
                print(f"  Diagnostic error: {de}")
            return False

        # ── Step 2: Record the first opportunity ID visible right now ─────
        # We will use this to verify the page actually changed after the click.
        first_id_before = None
        sentinel        = None
        try:
            sentinel = self.driver.find_element(
                By.XPATH, "//a[contains(@href,'/Ads/Details/')]"
            )
            href_before  = sentinel.get_attribute('href') or ''
            first_id_before = href_before.rstrip('/').split('/')[-1].split('?')[0]
        except Exception:
            pass

        # ── Step 3: Trigger the navigation ───────────────────────────────
        href    = candidate.get_attribute('href') or ''
        onclick = candidate.get_attribute('onclick') or ''

        pb_match = re.search(
            r"__doPostBack\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]" ,
            href + onclick,
            re.IGNORECASE
        )

        try:
            if pb_match:
                target   = pb_match.group(1)
                argument = pb_match.group(2)
                print(f"  [Pagination] Clicked NEXT via __doPostBack('{target}', '{argument}')")
                self.driver.execute_script(f"__doPostBack('{target}', '{argument}');")
            else:
                print(f"  [Pagination] Clicked NEXT → text='{candidate.text}' href='{href[:60]}'")
                self.driver.execute_script("arguments[0].click();", candidate)
        except Exception as ce:
            print(f"  [Pagination] Click error: {ce}")
            return False

        # ── Step 4: Wait for old content to go stale ─────────────────────
        print(f"  [Pagination] Waiting for page {next_page_num} to load...")
        try:
            if sentinel:
                WebDriverWait(self.driver, 20).until(EC.staleness_of(sentinel))
            else:
                time.sleep(3)
        except TimeoutException:
            print(f"  [Pagination] Timed out waiting for page {next_page_num} to become stale.")
            return False
        except Exception:
            time.sleep(3)   # fallback

        # ── Step 5: Wait for new results to appear ────────────────────────
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//a[contains(@href,'/Ads/Details/')]")
                )
            )
        except TimeoutException:
            print(f"  [Pagination] No results appeared on page {next_page_num}.")
            return False

        # ── Step 6: Verify first opportunity ID changed ───────────────────
        if first_id_before:
            try:
                first_link_after = self.driver.find_element(
                    By.XPATH, "//a[contains(@href,'/Ads/Details/')]"
                )
                href_after    = first_link_after.get_attribute('href') or ''
                first_id_after = href_after.rstrip('/').split('/')[-1].split('?')[0]

                if first_id_after == first_id_before:
                    print(f"  [Pagination] WARNING: First opportunity ID unchanged ({first_id_before}).")
                    print(f"  [Pagination] Page may not have changed — treating as last page.")
                    return False

                print(f"  [Pagination] Page changed confirmed: {first_id_before} → {first_id_after}")
            except Exception:
                pass   # can't verify, continue optimistically

        print(f"  [Pagination] Now on page {next_page_num}.")
        return True

    # ------------------------------------------------- extract one detail page
    def extract_clean_data(self, opp_id):
        url = f"https://www.nyscr.ny.gov/Ads/Details/{opp_id}"
        print(f"  Scraping {url}")
        self.driver.get(url)
        time.sleep(2)
        if "login" in self.driver.current_url.lower():
            print("  Session expired.")
            return None

        # Expand all collapsed sections so contact info / documents are visible
        self._expand_all()
        time.sleep(1.5)

        body_text = self.driver.find_element(By.TAG_NAME, "body").text

        # ---- TITLE  (FIX: read from page, not from search link text) ----
        title = self._get_title(body_text)

        # ---- STRUCTURED HEADER FIELDS ----
        cr_number        = self._field(body_text, 'CR#')
        contract_term    = self._field(body_text, 'Contract Term')
        agency           = self._field(body_text, 'Agency')
        division         = self._field(body_text, 'Division')
        issue_date_raw   = self._field(body_text, 'Issue date')
        due_date_raw     = self._field(body_text, 'Due date')
        location_raw     = self._field(body_text, 'Location')
        category_raw     = self._field(body_text, 'Category')
        ad_type_raw      = self._field(body_text, 'Ad type')
        contract_number  = self._field(body_text, 'Contract Number')

        # ---- DESCRIPTION ----
        description = self._get_description(body_text)

        # ---- CONTACT — returns a LIST of dicts, one per contact person ----
        # Each dict has keys: role, name, email, phone, organization
        contact_details = self._get_contact()
        print(f"  Contacts found: {len(contact_details)}")

        # ---- issuing_organization fallback ----------------------------------
        # Use the Agency field first; if missing, pull from the first contact's
        # organization so the field is never left blank when the info exists.
        issuing_org = agency or None
        if not issuing_org and contact_details:
            issuing_org = contact_details[0].get('organization') or None

        # ---- DOCUMENTS (skip DownloadDailyIssue and Search links) ----------
        documents = self._get_documents()

        # ---- UPDATES / BID RESULTS (skip footer nav) -----------------------
        updates, bid_results, awards_raw = self._get_updates_results(body_text)

        # ---- GOALS ---------------------------------------------------------
        sdvob_goal = self._get_goal(body_text, 'SDVOB Goal')
        mwbe_goal  = self._get_goal(body_text, 'MWBE')

        # ---- DATE PARSING --------------------------------------------------
        bid_deadline      = _parse_date(due_date_raw)
        publication_date  = _parse_date(issue_date_raw)
        question_deadline = self._get_question_deadline(body_text)

        # ---- STATUS --------------------------------------------------------
        status = "open"
        if bid_deadline:
            try:
                if datetime.strptime(bid_deadline, "%Y-%m-%d").date() < datetime.today().date():
                    status = "closed"
            except ValueError:
                pass

        # ---- LOCATION ------------------------------------------------------
        loc_address, loc_city, loc_state, loc_zip = self._parse_location(location_raw)

        # ---- BUDGET --------------------------------------------------------
        # Try description first, then fall back to full body_text
        budget_min, budget_max = self._parse_budget(description or '')
        if budget_min is None and budget_max is None:
            budget_min, budget_max = self._parse_budget(body_text)

        # ---- TRADES --------------------------------------------------------
        trades = self._parse_trades(category_raw)

        # ---- SQFT ----------------------------------------------------------
        sqft = self._parse_sqft(description or '')
        if sqft is None:
            sqft = self._parse_sqft(body_text)

        # ---- AWARDS --------------------------------------------------------
        awardee, award_date, award_number = self._parse_awards(awards_raw)
        if not award_number and contract_number:
            award_number = contract_number

        # ---- PROJECT TYPE --------------------------------------------------
        project_type = self._project_type(title, category_raw or '', description or '')

        # ---- ADDITIONAL INFO LINK ------------------------------------------
        # First URL found in description; fall back to any URL in body_text
        add_link = self._first_url(description or '') or self._first_url(body_text)
        # Never use the NYSCR search page itself as the additional info link
        if add_link and 'nyscr.ny.gov/Ads/Search' in add_link:
            add_link = None

        return {
            "source_id":   f"nyscr_{opp_id}",
            "source_url":  url,
            "title":       title,
            "description": description or None,
            "project_type": project_type,
            "status":      status,
            "project_category": category_raw or None,
            "budget_min":  budget_min,
            "budget_max":  budget_max,
            "location_address": loc_address,
            "location_city":    loc_city,
            "location_state":   loc_state or "NY",
            "location_zip":     loc_zip,
            "bid_deadline":      bid_deadline,
            "publication_date":  publication_date,
            "question_deadline": question_deadline,
            "issuing_organization": issuing_org,
            "solicitation_number":  cr_number or None,
            "solicitation_type":    ad_type_raw or None,
            # contact_details is a LIST — one dict per contact person found.
            # Each dict: { role, name, email, phone, organization }
            "contact_details": contact_details,
            "trades":   trades,
            "sqft":     sqft,
            "duration": contract_term or None,
            "cgac": None,
            "sub_tier": division or None,
            "fpds_code": None,
            "office":  division or None,
            "aac_code": None,
            "base_type": None,
            "archive_type": None,
            "archive_date": None,
            "set_aside_code": None,
            "set_aside": None,
            "classification_code": None,
            "pop_country": "US" if (loc_address or loc_city or loc_zip) else None,
            "active_status": None,
            "award_number": award_number,
            "award_date":   award_date,
            "awardee":      awardee,
            "organization_type": None,
            "additional_info_link": add_link,
            "bid_metadata": {
                "sdvob_goal":  sdvob_goal,
                "mwbe_goal":   mwbe_goal,
                "updates":     updates,
                "bid_results": bid_results,
                "awards_raw":  awards_raw,
                "scraped_at":  datetime.now().isoformat(),
            },
            "documents": documents,
        }

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _expand_all(self):
        """Click all collapsed accordions/toggles so hidden sections load."""
        selectors = [
            "button[aria-expanded='false']",
            ".collapsed",
            "[data-toggle='collapse']",
            "[data-bs-toggle='collapse']",
        ]
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

    # ------------------------------------------------------------------
    # TITLE — read from page heading, not the search-link text
    # The NYSCR detail page layout:
    #   << Home | All Open Opportunities | Ad details
    #   <Title Line>
    #   CR#    <number>    Contract Number  ...
    # ------------------------------------------------------------------
    def _get_title(self, body_text):
        # Strategy 1: look for element with class containing 'title' or the h1
        for css in ['h1', '.ad-title', '.page-title', 'h2']:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, css):
                    txt = _clean(el.text)
                    low = txt.lower()
                    if not txt:
                        continue
                    # Skip site navigation headings
                    bad = ['contract reporter', 'login', 'search', 'dashboard',
                           'all open', 'ad details', 'home |', 'contracting opportunities',
                           "here's how", 'new york state contract reporter']
                    if any(b in low for b in bad):
                        continue
                    # Skip pure numbers or "view this ad"
                    if re.match(r'^[\d\s]+$', txt) or low in ('view this ad', 'details'):
                        continue
                    if len(txt) > 5:
                        return txt
            except Exception:
                pass

        # Strategy 2: regex on body text — title sits between "Ad details\n" and
        # the first header field line (CR# or a date)
        m = re.search(r'Ad details\s*\n+\s*(.+?)\s*\n', body_text, re.IGNORECASE)
        if m:
            candidate = _clean(m.group(1))
            # Reject if it looks like a CR# line or a date
            if candidate and not re.match(r'^[\d\s/:\-]+$', candidate):
                if not re.match(r'^\d{5,}$', candidate):
                    return candidate

        return "Title not found"

    # ------------------------------------------------------------------
    # FIELD extraction from body text  (label: value pattern)
    # ------------------------------------------------------------------
    def _field(self, body_text, label):
        """Extract the value after a labelled field."""
        pattern = re.compile(
            r'\b' + re.escape(label) + r'\s*:?\s*\n?\s*(.+?)(?:\n|$)',
            re.IGNORECASE
        )
        m = pattern.search(body_text)
        if m:
            val = _clean(m.group(1))
            # Don't return another label name as the value
            if val and not val.endswith(':'):
                return val
        return None

    # ------------------------------------------------------------------
    # DESCRIPTION — 3-strategy extraction
    #
    # Problem with previous approach:
    #  - STOP words like 'contact', 'document', 'minority' appear INSIDE
    #    long descriptions themselves, causing early truncation → null
    #  - The label:value guard was too aggressive, cutting real sentences
    #
    # New approach:
    #  Strategy 1: JavaScript — grab innerText of the section container
    #              that immediately follows the "General Description" heading
    #  Strategy 2: DOM parent-walk (conservative stop conditions)
    #  Strategy 3: Body-text slice with ONLY truly unambiguous stop markers
    # ------------------------------------------------------------------
    def _get_description(self, body_text):

        # ── Strategy 1: JS innerText of the description section ──────────
        try:
            desc = self._js_description()
            if desc and len(desc) > 40:
                return desc
        except Exception:
            pass

        # ── Strategy 2: DOM parent/sibling walk ───────────────────────────
        try:
            desc = self._dom_description()
            if desc and len(desc) > 40:
                return desc
        except Exception:
            pass

        # ── Strategy 3: Body-text slice with tight, unambiguous stops ─────
        # Only stop at section-header lines that are SHORT and standalone —
        # NOT at keywords that can appear mid-description.
        #
        # A "section header" on NYSCR is a SHORT standalone line, typically
        # 1–4 words, that introduces the next page section.
        # The description itself can be hundreds of words with colons, URLs,
        # bullet points, goal percentages — everything.
        #
        # Unambiguous stop lines (exact / near-exact matches only):
        STOP_EXACT = {
            'contact info', 'contact information', 'primary contact',
            'technical contact', 'submit to contact', 'ad contact',
            'agency contact', 'documents', 'updates', 'bid results',
            'awards', 'notify me if this ad updates',
            'download pdf', 'bookmark this ad', 'accessibility',
        }

        # Find description start — must be AFTER the breadcrumb
        bc = body_text.find('Ad details')
        search_from = bc if bc != -1 else 0

        m = re.search(r'\b(?:General\s+)?Description\b', body_text[search_from:], re.IGNORECASE)
        if not m:
            return None

        rest = body_text[search_from + m.end():]
        rest = re.sub(r'^[:\s]+', '', rest)  # skip trailing colon/space on header line

        lines = []
        blank_count = 0

        for raw_line in rest.split('\n'):
            line = _clean(raw_line)

            if not line:
                blank_count += 1
                # Allow blank lines within text (paragraph breaks)
                # but 3+ consecutive blanks = section boundary
                if blank_count >= 3:
                    break
                continue
            blank_count = 0

            low = line.lower().strip()

            # Exact section-header stop
            if low in STOP_EXACT:
                break

            # Short standalone line that exactly matches a stop header
            # (handles "Contact Info" even without exact match above)
            if len(line) <= 30 and re.match(
                r'^(?:contact|documents?|updates?|bid results?|awards?|'
                r'accessibility|notify me|download)', low
            ):
                break

            # Skip language blob lines
            if _looks_like_language_blob(line):
                continue

            lines.append(line)

        while lines and not lines[-1]:
            lines.pop()

        result = ' '.join(l for l in lines if l).strip()
        return result if len(result) > 30 else None

    def _js_description(self):
        """
        Use JavaScript to find the description section container and extract
        its full innerText. This is the most reliable method because JS has
        direct DOM access without Selenium wrapper overhead.
        """
        js = r"""
        // Walk all elements looking for one whose text is exactly or nearly
        // "Description" or "General Description" and is a heading-type element
        var headingTags = ['H2','H3','H4','H5','STRONG','B','DT','TH','LABEL','SPAN','DIV'];
        var stopWords = ['sdvob goal','mwbe','minority / women','mbe goal','wbe goal',
                         'dbe goal','contact info','contact information','primary contact',
                         'technical contact','submit to contact','documents',
                         'notify me','download pdf','bookmark','accessibility'];

        function isStop(text) {
            var low = text.toLowerCase().trim();
            return stopWords.some(function(w){ return low === w || low.startsWith(w); });
        }

        var allEls = document.querySelectorAll(headingTags.join(','));
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            var t = (el.innerText || el.textContent || '').trim().toLowerCase();
            // Must be exactly "description" or "general description"
            if (t !== 'description' && t !== 'general description') continue;

            // Collect text from all following siblings until a stop
            var texts = [];
            var sib = el.nextElementSibling;
            var count = 0;
            while (sib && count < 60) {
                var sibText = (sib.innerText || sib.textContent || '').trim();
                if (!sibText) { sib = sib.nextElementSibling; count++; continue; }
                if (isStop(sibText)) break;
                var tag = sib.tagName.toUpperCase();
                if (['H2','H3','H4'].indexOf(tag) !== -1) break;
                texts.push(sibText);
                sib = sib.nextElementSibling;
                count++;
            }
            if (texts.length > 0) return texts.join(' ');

            // If no siblings, try the parent's children after this heading
            var parent = el.parentElement;
            if (!parent) continue;
            var kids = parent.children;
            var found = false;
            var parentTexts = [];
            for (var j = 0; j < kids.length; j++) {
                var kid = kids[j];
                if (kid === el) { found = true; continue; }
                if (!found) continue;
                var kidText = (kid.innerText || kid.textContent || '').trim();
                if (!kidText) continue;
                if (isStop(kidText)) break;
                var ktag = kid.tagName.toUpperCase();
                if (['H2','H3','H4'].indexOf(ktag) !== -1) break;
                parentTexts.push(kidText);
            }
            if (parentTexts.length > 0) return parentTexts.join(' ');
        }
        return null;
        """
        try:
            result = self.driver.execute_script(js)
            if result:
                result = _clean(result)
                if not _looks_like_language_blob(result) and len(result) > 40:
                    return result
        except Exception:
            pass
        return None

    def _dom_description(self):
        """DOM walk fallback — find Description heading, collect following text."""
        STOP_EXACT_SET = {
            'sdvob goal', 'mwbe', 'minority / women', 'mbe goal', 'wbe goal',
            'dbe goal', 'contact info', 'contact information', 'primary contact',
            'technical contact', 'submit to contact', 'documents',
            'notify me if this ad updates', 'download pdf', 'bookmark this ad',
            'accessibility', 'updates', 'bid results', 'awards',
        }

        xpath = (
            "//*[self::h2 or self::h3 or self::h4 or self::h5 "
            "    or self::strong or self::b or self::dt or self::th]"
            "[translate(normalize-space(.),"
            " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
            " = 'description' or "
            " translate(normalize-space(.),"
            " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
            " = 'general description']"
        )
        try:
            headings = self.driver.find_elements(By.XPATH, xpath)
            for heading in headings:
                collected = []
                # nextElementSibling walk via JS (faster, avoids stale refs)
                js = """
                var el = arguments[0], texts = [], sib = el.nextElementSibling,
                    n = 0, stops = arguments[1];
                while (sib && n < 60) {
                    var t = (sib.innerText || '').trim();
                    var low = t.toLowerCase().trim();
                    if (stops.indexOf(low) !== -1) break;
                    var tag = sib.tagName.toLowerCase();
                    if (['h2','h3','h4'].indexOf(tag) !== -1) break;
                    if (t.length > 5) texts.push(t);
                    sib = sib.nextElementSibling; n++;
                }
                return texts.join(' ');
                """
                result = self.driver.execute_script(
                    js, heading, list(STOP_EXACT_SET))
                result = _clean(result)
                if result and len(result) > 40 and not _looks_like_language_blob(result):
                    return result
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # CONTACT — returns a LIST of contact dicts, one per person.
    #
    # NYSCR contact block structure (one person):
    #
    #   Primary Contact          ← role label  (marks start of a new person)
    #   Vashisti Kowlessur       ← person name
    #   Office Assistant 2       ← job title   (skip from name/org)
    #   People with Developmental Disabilities, NYS Office for (Brooklyn DDSO)
    #   Business Office          ← org sub-unit
    #   750 Vandalia Avenue      ← address lines (skip)
    #   Brooklyn, New York 11239
    #   United States
    #   (ph) 718-264-3915  ext. n/a  ← phone
    #   brooklyn.cmm.bids@opwdd.ny.gov  ← email
    #
    # Multiple contacts appear sequentially in the same section,
    # each introduced by a role label.
    # ------------------------------------------------------------------

    # Role labels that NYSCR uses to introduce each contact person
    _CONTACT_ROLE_LABELS = re.compile(
        r'^(Primary Contact|Technical Contact|Submit\s+To\s+Contact|'
        r'Ad Contact|Agency Contact|Bid Contact|Contract Contact|'
        r'Contact Person|Secondary Contact|Additional Contact)$',
        re.IGNORECASE
    )

    # Job-title words — lines that are ONLY job titles are skipped as name
    _JOB_TITLE_WORDS = {
        'manager', 'director', 'coordinator', 'officer', 'agent', 'specialist',
        'assistant', 'admin', 'secretary', 'analyst', 'engineer', 'supervisor',
        'president', 'consultant', 'representative', 'clerk', 'inspector',
        'technician', 'accountant', 'attorney', 'counsel', 'administrator',
        'aide', 'associate', 'deputy', 'chief', 'senior', 'junior', 'lead',
        'vice', 'executive', 'procurement', 'purchasing', 'buyer',
    }

    # Org-indicator words — if a line contains any of these it is the org name
    _ORG_WORDS = {
        'inc.', 'corp.', 'llc', 'l.l.c.', 'incorporated', 'corporation',
        'agency', 'department', 'dept.', 'division', 'university', 'office',
        'authority', 'board', 'suny', 'cuny', 'nysdoh', 'opwdd', 'nyserda',
        'ddso', 'housing', 'school', 'college', 'district', 'county',
        'municipality', 'city of', 'village of', 'town of', 'state of',
        'institute', 'foundation', 'association', 'center', 'commission',
        'bureau', 'administration', 'services', 'authority',
    }

    def _get_contact(self):
        """Return a list of contact dicts — one dict per contact person."""
        contact_text = self._isolate_contact_section()
        if not contact_text:
            return []
        blocks = self._split_contact_blocks(contact_text)
        contacts = []
        for role, block_lines in blocks:
            c = self._parse_one_contact(role, block_lines)
            # Only include contacts that have at minimum an email or phone.
            # This prevents ghost contacts (name only, no actual contact info).
            if c.get('email') or c.get('phone'):
                contacts.append(c)
        return contacts

    def _isolate_contact_section(self):
        """
        Return the raw text of the Contact Info section only.
        Uses JavaScript to find the section — most reliable approach.
        """
        # Strategy 1: JavaScript — find the Contact Info accordion/section
        # and return its innerText directly
        js = r"""
        var markers = ['Contact Info', 'Contact Information', 'Contact Details'];
        var body = document.body;
        var allEls = body.querySelectorAll('*');

        // Find a heading/label element whose text is exactly a contact marker
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            var tag = el.tagName.toLowerCase();
            if (['h2','h3','h4','h5','h6','button','strong','b',
                 'span','div','dt','th','label'].indexOf(tag) === -1) continue;
            var t = (el.innerText || el.textContent || '').trim();
            var found = false;
            for (var m = 0; m < markers.length; m++) {
                if (t.toLowerCase() === markers[m].toLowerCase()) {
                    found = true; break;
                }
            }
            if (!found) continue;

            // Found the heading — now collect the section container text.
            // Try: parent element's innerText (most reliable)
            var parent = el.parentElement;
            if (parent) {
                var parentText = (parent.innerText || '').trim();
                // Must be longer than just the heading itself
                if (parentText.length > t.length + 20) {
                    return parentText;
                }
            }
            // Try: next sibling container
            var sib = el.nextElementSibling;
            if (sib) {
                var sibText = (sib.innerText || '').trim();
                if (sibText.length > 20) return sibText;
            }
            // Try: grandparent
            if (parent && parent.parentElement) {
                var gp = parent.parentElement;
                var gpText = (gp.innerText || '').trim();
                if (gpText.length > t.length + 20) return gpText;
            }
        }
        return null;
        """
        try:
            result = self.driver.execute_script(js)
            if result and len(result.strip()) > 20:
                return result.strip()
        except Exception:
            pass

        # Strategy 2: Body text slice — find "Contact Info" in the body text
        # and extract the section between it and the next major section header.
        try:
            body = self.driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            return None

        # Look for the Contact Info section header line
        m = re.search(
            r'(?:^|\n)\s*(Contact\s+Info(?:rmation)?)\s*\n',
            body, re.IGNORECASE
        )
        if not m:
            # Some ads just start with "Primary Contact" directly
            m = re.search(
                r'(?:^|\n)\s*(Primary\s+Contact|Submit\s+To\s+Contact|'
                r'Technical\s+Contact|Agency\s+Contact)\s*\n',
                body, re.IGNORECASE
            )
        if not m:
            return None

        section = body[m.start():]

        # Cut at the next major section boundary
        end = re.search(
            r'\n\s*(?:Documents?|Updates?|Bid\s+Results?|Awards?|'
            r'Notify\s+me\s+if|Download\s+PDF|Bookmark\s+this)\s*\n',
            section, re.IGNORECASE
        )
        if end:
            section = section[:end.start()]

        # Strip out language blob lines individually (NOT the whole block)
        clean_lines = []
        for line in section.split('\n'):
            line = _clean(line)
            if not line:
                continue
            if _looks_like_language_blob(line):
                continue
            if _is_language_word(line):
                continue
            clean_lines.append(line)

        return '\n'.join(clean_lines) if clean_lines else None

    # Regex that finds a role label anywhere in a line (start, end, or standalone)
    # Used by _split_contact_blocks to detect "Spencer Koenig  Primary Contact"
    _ROLE_ANYWHERE = re.compile(
        r'(Primary\s+Contact|Technical\s+Contact|Submit\s+To\s+Contact|'
        r'Ad\s+Contact|Agency\s+Contact|Bid\s+Contact|Contract\s+Contact|'
        r'Contact\s+Person|Secondary\s+Contact|Additional\s+Contact|'
        r'Procurement\s+Contact|Point\s+of\s+Contact)',
        re.IGNORECASE
    )

    def _split_contact_blocks(self, contact_text):
        """
        Split contact_text into blocks, each representing one contact person.
        Returns a list of (role_label, [lines]) tuples.

        NYSCR can render the name and role on the SAME line in two ways:
          Pattern A (role alone on its own line):
              Primary Contact
              Spencer Koenig
              ...

          Pattern B (name + role on one line):
              Spencer Koenig  Primary Contact
              ...

        We handle both.
        """
        raw_lines = [_clean(l) for l in contact_text.split('\n') if _clean(l)]

        # Strip the "Contact Info" section header
        if raw_lines and re.match(r'^Contact\s+Info(?:rmation)?$',
                                   raw_lines[0], re.IGNORECASE):
            raw_lines = raw_lines[1:]

        # ── First pass: parse each raw line into (role, name_part, rest) ──
        # We build a normalised list of events:
        #   {'type': 'role_start', 'role': ..., 'name': ...}
        #   {'type': 'data', 'line': ...}

        events = []
        for line in raw_lines:
            m = self._ROLE_ANYWHERE.search(line)
            if m:
                role_label = m.group(1)
                # Text before the role label = name (if any)
                before = _clean(line[:m.start()])
                # Text after the role label = extra data (rare)
                after  = _clean(line[m.end():])
                events.append({
                    'type': 'role_start',
                    'role': role_label,
                    'name': before if before else None,
                    'extra': after if after else None,
                })
            else:
                events.append({'type': 'data', 'line': line})

        # ── Second pass: group events into blocks ─────────────────────────
        blocks    = []
        cur_role  = None
        cur_name  = None   # name extracted from the role-label line
        cur_lines = []

        for ev in events:
            if ev['type'] == 'role_start':
                # Save the previous block
                if cur_lines or cur_name:
                    lines_for_block = cur_lines[:]
                    # If name was on the role line, prepend it
                    if cur_name:
                        lines_for_block = [cur_name] + lines_for_block
                    blocks.append((cur_role or 'Contact', lines_for_block))
                cur_role  = ev['role']
                cur_name  = ev['name']
                cur_lines = []
                if ev['extra']:
                    cur_lines.append(ev['extra'])
            else:
                cur_lines.append(ev['line'])

        # Save final block
        if cur_lines or cur_name:
            lines_for_block = cur_lines[:]
            if cur_name:
                lines_for_block = [cur_name] + lines_for_block
            blocks.append((cur_role or 'Contact', lines_for_block))

        # If no role labels found at all, one block with everything
        if not blocks:
            blocks = [('Contact', raw_lines)]

        return blocks

    def _parse_one_contact(self, role, lines):
        """
        Parse a list of text lines into a single contact dict.

        The first line in `lines` is already the person/unit name
        (extracted from the role-label line by _split_contact_blocks).
        Subsequent lines: job title (skip), org, address (skip), phone, email.
        """
        email_re   = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
        phone_re   = re.compile(
            r'(?:\(ph\)|ph\.?|phone\s*:?|tel\.?\s*:?)'
            r'[^\d]{0,5}(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}'
            r'(?:\s*(?:ext\.?|x)\s*[\w/]+)?)',
            re.IGNORECASE
        )
        phone_bare = re.compile(r'\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}')
        address_re = re.compile(
            r'\d+\s+\w+\s+(?:street|st\.?|ave\.?|avenue|road|rd\.?|blvd|'
            r'drive|dr\.?|lane|ln\.?|place|pl\.?|way|court|ct\.?|'
            r'highway|hwy|parkway|pkwy|terrace|ter\.?)\b'
            r'|p\.?o\.?\s*box',
            re.IGNORECASE
        )
        city_state_re = re.compile(
            r',\s*(?:new\s+york|ny)\b|\bnew\s+york\s*,', re.IGNORECASE)

        SKIP_EXACT = {
            'contact info', 'contact information', 'contact details',
            "here's how", 'home |', 'all open opportunities',
            'united states', 'usa',
        }

        def _is_org_line(line):
            """True if line looks like an organization name, not a person name."""
            low = line.lower()
            if '(' in line and ')' in line and len(line) > 15:
                return True
            strong = [
                r'\bdepartment\s+of\b', r'\boffice\s+of\b', r'\bdivision\s+of\b',
                r'\bbureau\s+of\b', r'\bauthority\s+of\b', r'\bboard\s+of\b',
                r'\bnys\s+\w', r'\bnyc\s+\w', r'\bnysdoh\b', r'\bopwdd\b',
                r'\bnyserda\b', r'\bsuny\b', r'\bcuny\b',
                r',\s*inc\.?\b', r',\s*llc\.?\b', r'\bcorp\.\b',
                r'\buniversity\b', r'\bcollege\b', r'\bfoundation\b',
                r'\bassociation\b', r'\bcommission\b', r'\bmunicipality\b',
                r'\bschool\s+district\b', r'\bcounty\s+of\b',
            ]
            if any(re.search(p, low) for p in strong):
                return True
            if len(line) > 40 and any(
                kw in low for kw in [
                    'agency', 'department', 'authority', 'division',
                    'district', 'county', 'housing', 'services',
                ]
            ):
                return True
            return False

        contact = {
            "role":         role,
            "name":         None,
            "email":        None,
            "phone":        None,
            "organization": None,
        }

        # The first non-noise line is the name (already extracted from role line)
        name_assigned  = False
        org_candidates = []

        for i, line in enumerate(lines):
            if not line:
                continue
            low = line.lower().strip()

            # Skip section headers / noise
            if low in SKIP_EXACT:
                continue
            if _is_language_word(line) or _looks_like_language_blob(line):
                continue
            if self._ROLE_ANYWHERE.search(line):
                continue

            # ── Email ──────────────────────────────────────────────────
            em = email_re.search(line)
            if em:
                if not contact['email']:
                    contact['email'] = em.group(0).strip()
                continue

            # ── Phone with label ───────────────────────────────────────
            ph = phone_re.search(line)
            if ph:
                if not contact['phone']:
                    contact['phone'] = _clean(ph.group(1))
                continue

            # ── Bare phone number ──────────────────────────────────────
            bph = phone_bare.search(line)
            if bph and re.search(r'\d{3}[\s.\-]\d{3}[\s.\-]\d{4}|\(\d{3}\)', line):
                if not contact['phone']:
                    contact['phone'] = _clean(line)
                continue

            # ── Skip address / city-state / zip ────────────────────────
            if address_re.search(low):
                continue
            if city_state_re.search(low):
                continue
            if re.match(r'^\d{5}(?:-\d{4})?$', line):
                continue

            # ── Assign first valid line as name ────────────────────────
            # (only if we haven't set name yet)
            if not name_assigned:
                # Must not be an org line, must not be a pure job-title line
                words = line.split()
                pure_job = (
                    len(words) >= 1 and
                    all(w.lower().rstrip('.,') in self._JOB_TITLE_WORDS for w in words)
                )
                if not _is_org_line(line) and not pure_job and len(line) <= 60:
                    contact['name'] = line
                    name_assigned = True
                    continue
                elif _is_org_line(line):
                    org_candidates.append(line)
                    continue
                # pure job title — fall through (skip silently)
                continue

            # ── Subsequent lines: org or skip ──────────────────────────
            if _is_org_line(line):
                org_candidates.append(line)
                continue
            # Any other short line after name is job title — skip it

        if org_candidates:
            contact['organization'] = org_candidates[0]

        return contact

    # ------------------------------------------------------------------
    # DOCUMENTS — only opportunity-specific files
    # Skip: DownloadDailyIssue (site newsletters), Search links, mailto links
    # ------------------------------------------------------------------
    def _get_documents(self):
        docs = []
        seen_urls = set()
        try:
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for lnk in links:
                href = lnk.get_attribute('href') or ''
                name = _clean(lnk.text) or ''

                # Skip empties, mailto, anchors
                if not href or href.startswith('mailto:') or href.startswith('#'):
                    continue
                # Skip site-wide daily issue PDFs
                if _DAILY_ISSUE_TOKEN in href:
                    continue
                # Skip the generic search/home links
                if 'BidFilter' in href or href.endswith('/Ads/Search'):
                    continue
                # Only include if it looks like a real document URL or file extension
                is_doc = any(ext in href.lower() for ext in [
                    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip',
                    '.dwg', '.txt', '.ppt', '.pptx', '.csv',
                ])
                # Or if the link text implies a document
                name_lower = name.lower()
                is_named_doc = any(kw in name_lower for kw in [
                    'download', 'attachment', 'bid document', 'specification',
                    'addendum', 'plan', 'rfp', 'rfq', 'solicitation', 'scope',
                    'form', 'exhibit', 'appendix',
                ])
                # Skip if it's just a page navigation link to a section
                if not is_doc and not is_named_doc:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # Determine file type
                ext_match = re.search(r'\.([a-zA-Z]{2,5})(?:\?|$)', href)
                file_type = ext_match.group(1).lower() if ext_match else 'unknown'

                docs.append({
                    "name":      name if name else f"Document_{len(docs)+1}",
                    "url":       href,
                    "file_type": file_type,
                    "file_size": None,
                })
        except Exception as e:
            print(f"  Warning: document extraction error: {e}")
        return docs

    # ------------------------------------------------------------------
    # UPDATES / BID RESULTS — strip footer nav
    # ------------------------------------------------------------------
    def _get_updates_results(self, body_text):
        updates    = []
        bid_results = []
        awards_raw  = []

        current = None
        for line in body_text.split('\n'):
            line = _clean(line)
            if not line:
                continue
            low = line.lower()

            # Skip language blob lines
            if _looks_like_language_blob(line):
                continue
            # Skip footer phrases
            if low in _FOOTER_PHRASES:
                continue
            if low.startswith('.nys_footer'):
                continue

            # Section headers
            if re.match(r'^Updates?\s*$', line, re.IGNORECASE):
                current = 'updates'
                continue
            if re.match(r'^Bid Results?\s*$', line, re.IGNORECASE):
                current = 'bid_results'
                continue
            if re.match(r'^Awards?\s*$', line, re.IGNORECASE):
                current = 'awards'
                continue
            if re.match(r'^(?:Documents?|Contact Info|Accessibility)\s*$', line, re.IGNORECASE):
                current = None
                continue

            if current == 'updates' and len(line) > 3:
                updates.append(line)
            elif current == 'bid_results' and len(line) > 3:
                bid_results.append(line)
            elif current == 'awards' and len(line) > 3:
                awards_raw.append(line)

        return (
            updates    or ["No updates found"],
            bid_results or ["Bid results have not been entered"],
            awards_raw  or ["Awards have not been entered"],
        )

    # ------------------------------------------------------------------
    # GOALS
    # ------------------------------------------------------------------
    def _get_goal(self, body_text, label):
        m = re.search(re.escape(label) + r'.*?:\s*([\d.]+%)', body_text, re.IGNORECASE)
        return m.group(1) if m else None

    # ------------------------------------------------------------------
    # QUESTION DEADLINE
    # ------------------------------------------------------------------
    def _get_question_deadline(self, body_text):
        for line in body_text.split('\n'):
            if 'question' in line.lower() and any(k in line.lower() for k in ['due', 'deadline', 'by', 'date']):
                d = _parse_date(line)
                if d:
                    return d
        return None

    # ------------------------------------------------------------------
    # LOCATION parser
    # ------------------------------------------------------------------
    def _parse_location(self, raw):
        address = city = state = zip_code = None
        if not raw:
            return address, city, state, zip_code
        raw = _clean(raw)
        # Extract zip
        z = re.search(r'\b(\d{5}(?:-\d{4})?)\b', raw)
        if z:
            zip_code = z.group(1)
            raw = raw.replace(zip_code, '').strip(' ,-')
        # Extract state abbreviation (2 uppercase letters after comma or space)
        s = re.search(r'\b([A-Z]{2})\b', raw)
        if s:
            state = s.group(1)
            raw = re.sub(r'\b' + re.escape(state) + r'\b', '', raw, count=1).strip(' ,-')
        # Strip "- State-wide" suffix
        raw = re.sub(r'\s*-\s*State-?wide', '', raw, flags=re.IGNORECASE).strip(' ,-')
        # Split on comma
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        if len(parts) >= 2:
            address = ', '.join(parts[:-1])
            city    = parts[-1]
        elif len(parts) == 1:
            if any(c.isdigit() for c in parts[0]):
                address = parts[0]
            else:
                city = parts[0]
        return address, city, state or 'NY', zip_code

    # ------------------------------------------------------------------
    # BUDGET
    # ------------------------------------------------------------------
    def _parse_budget(self, text):
        pattern = re.compile(
            r'(?:estimated\s+cost|est\.?\s+cost|budget|value|contract\s+value)'
            r'\D{0,20}\$\s*([0-9,]+(?:\.\d+)?)\s*(million|m|k|thousand)?',
            re.IGNORECASE
        )
        amounts = []
        for m in pattern.finditer(text):
            v = float(m.group(1).replace(',', ''))
            suf = (m.group(2) or '').lower()
            if suf in ('million', 'm'):
                v *= 1_000_000
            elif suf in ('k', 'thousand'):
                v *= 1_000
            if v >= 500:
                amounts.append(v)
        if len(amounts) >= 2:
            return min(amounts), max(amounts)
        if len(amounts) == 1:
            return None, amounts[0]
        return None, None

    # ------------------------------------------------------------------
    # TRADES
    # ------------------------------------------------------------------
    def _parse_trades(self, category):
        if not category:
            return []
        return [t.strip() for t in re.split(r'[;\n]', category) if t.strip()]

    # ------------------------------------------------------------------
    # SQFT
    # ------------------------------------------------------------------
    def _parse_sqft(self, text):
        m = re.search(r'\b([0-9,]+)\s*(?:sq\.?\s*ft\.?|sf|square\s+feet)\b', text, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(',', ''))
        return None

    # ------------------------------------------------------------------
    # AWARDS
    # ------------------------------------------------------------------
    def _parse_awards(self, awards_list):
        awardee = award_date = award_number = None
        for line in awards_list:
            if 'not been entered' in line.lower():
                continue
            if any(k in line.lower() for k in ['awardee', 'contractor', 'awarded to']):
                parts = re.split(r':|is|to', line, maxsplit=1)
                if len(parts) > 1:
                    awardee = _clean(parts[1])
            if any(k in line.lower() for k in ['date', 'awarded on']):
                d = _parse_date(line)
                if d:
                    award_date = d
            if any(k in line.lower() for k in ['number', 'contract #', 'award #']):
                parts = re.split(r'[:#]', line, maxsplit=1)
                if len(parts) > 1:
                    award_number = _clean(parts[1])
        return awardee, award_date, award_number

    # ------------------------------------------------------------------
    # PROJECT TYPE
    # ------------------------------------------------------------------
    def _project_type(self, title, category, description):
        combined = f"{title} {category} {description}".lower()
        construction_kw = [
            'construction', 'rehabilitation', 'renovation', 'hvac', 'electrical',
            'plumbing', 'painting', 'roofing', 'paving', 'demolition', 'building',
            'road', 'highway', 'concrete', 'masonry', 'carpentry', 'excavation',
            'culvert', 'sidewalk', 'curb', 'parking lot', 'elevator', 'roof',
        ]
        if any(k in combined for k in construction_kw):
            return "construction_bid"
        return "rfp"

    # ------------------------------------------------------------------
    # FIRST EXTERNAL URL from text
    # ------------------------------------------------------------------
    def _first_url(self, text):
        m = re.search(r'https?://[^\s\)]+', text)
        return m.group(0).rstrip('.,;)') if m else None

    # ------------------------------------------------------------------
    # Run scrape loop
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Load previously saved records so we can resume interrupted runs
    # ------------------------------------------------------------------
    def load_existing(self, filename="nyscr_scraped_data.json"):
        """Load existing JSON and return (records_list, seen_ids_set)."""
        import os
        if not os.path.exists(filename):
            return [], set()
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                return [], set()
            # source_id format is "nyscr_<numeric_id>"
            seen = {rec['source_id'].split('_')[-1] for rec in existing
                    if rec.get('source_id')}
            print(f"Resume: loaded {len(existing)} existing records "
                  f"({len(seen)} unique IDs). Skipping those.")
            return existing, seen
        except Exception as e:
            print(f"Warning: could not load existing data ({e}). Starting fresh.")
            return [], set()

    def scrape(self, max_opportunities=None, output_file="nyscr_scraped_data.json"):
        """Scrape opportunities, resuming from any previously saved progress."""
        # ── 1. Load what we already have ─────────────────────────────────
        existing_records, already_done = self.load_existing(output_file)

        # ── 2. Collect the full list of open opportunity IDs ─────────────
        # Fetch cap + already_done so we always get cap NEW records after
        # filtering out what was already saved.
        cap = max_opportunities if max_opportunities is not None else 999_999
        fetch_cap = cap if cap == 999_999 else cap + len(already_done)
        opps = self.get_open_opportunities(max_count=fetch_cap)
        if not opps:
            print("No open opportunities found.")
            return existing_records

        # ── 3. Filter out already-scraped IDs ────────────────────────────
        pending = [o for o in opps if o['id'] not in already_done]
        skipped = len(opps) - len(pending)
        if skipped:
            print(f"Skipping {skipped} already-scraped opportunities. "
                  f"{len(pending)} remain.")
        if not pending:
            print("All opportunities in this batch are already scraped.")
            return existing_records

        # ── 4. Scrape the remaining ones, appending to existing_records ──
        new_results = []
        failed = 0
        for i, opp in enumerate(pending):
            print(f"\n[{i+1}/{len(pending)}] Processing ID {opp['id']} "
                  f"(total saved so far: {len(existing_records) + len(new_results)})")
            try:
                data = self.extract_clean_data(opp['id'])
                if data:
                    new_results.append(data)
                    print(f"  Title: {data['title']}")
                else:
                    failed += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                failed += 1

            # ── Save progress every 25 NEW records ───────────────────────
            if (i + 1) % 25 == 0 and new_results:
                self.save(existing_records + new_results, filename=output_file)

            time.sleep(0.8)

        all_results = existing_records + new_results
        print(f"\nDone. New: {len(new_results)}, Failed: {failed}, "
              f"Total in file: {len(all_results)}")
        return all_results

    def save(self, data, filename="nyscr_scraped_data.json"):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(data)} records to {filename}")

    def close(self):
        if self.driver:
            self.driver.quit()
            print("Browser closed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  NYSCR Scraper — Open Opportunities")
    print("=" * 60)

    scraper = NYSCRScraper()
    try:
        if not scraper.setup_chrome():
            return
        if not scraper.login():
            print("Login failed. Exiting.")
            return

        # ── Scope selection (asked AFTER successful login) ──────────────
        print("\n" + "=" * 60)
        print("  Choose scraping scope:")
        print("  1. Test run   (first 50 opportunities)")
        print("  2. Medium run (first 200 opportunities)")
        print("  3. Full run   (ALL opportunities)")
        print("=" * 60)
        while True:
            choice = input("\n  Enter choice (1/2/3): ").strip()
            if choice == "1":
                max_opps = 50
                print("  → Test run: first 50 opportunities")
                break
            elif choice == "2":
                max_opps = 200
                print("  → Medium run: first 200 opportunities")
                break
            elif choice == "3":
                max_opps = None          # None = no limit = ALL
                print("  → Full run: ALL open opportunities")
                break
            else:
                print("  Invalid choice. Please enter 1, 2 or 3.")
        # ────────────────────────────────────────────────────────────────

        output_file = "nyscr_scraped_data.json"
        data = scraper.scrape(max_opportunities=max_opps, output_file=output_file)

        if data:
            scraper.save(data, filename=output_file)
            print(f"\nFinal output: {output_file} ({len(data)} records)")
            print("\nSample (first record):")
            sample = data[0]
            for key in ['source_id', 'title', 'issuing_organization',
                        'bid_deadline', 'location_address', 'location_city',
                        'contact_details']:
                print(f"  {key}: {sample.get(key)}")
        else:
            print("No data scraped.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
