#!/usr/bin/env python3
"""
DASNY Scraper - RFP/Bid Opportunities
Target: https://www.dasny.org/opportunities/rfps-bids

No login/captcha required - listings and detail pages are public.

SELECTORS CONFIRMED FROM REAL LIVE HTML (2026-07):
- Listing card:        div.rfp-bid-wrapper
- Title:               div.rfp-bid-title h2 a
- Header fields:       div.rfp-bid-info table tbody tr  (td label, td.fieldValue value)
- Real detail link:    div.rfp-bid-links a with text "View the full details for this opportunity"
                       (NOT the Interested Subs / plan holders / login links in the same div)
- Pagination:          ?page=N ; stop via "Displaying X - Y of Z" in div.view-footer
- Description:         #rfp-bid-notice .panel-body   (plain <p> tags, no sub-headings)
- Contacts:            #rfp-contacts .panel-body      (<h2> = role, following <p> = data lines)
- Planholders list:    element near/at #rfp-planholders-list
- Interested Subs:     element near/at #rfp-interestedsubssuppliers-list
- Emails on this site are plain "mailto:" links, NOT Cloudflare-obfuscated.
  (CF-decode kept only as a defensive fallback in case another page differs.)

Remaining unconfirmed (still best-effort, marked with "# RECON:"):
- Documents/attachments section container (not seen yet in samples)
- issuing_organization derivation
"""

import sys
import re
import os
import json
import time

# Ensure Python311 site-packages is in sys.path
_PYTHON311_PKG = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python311\Lib\site-packages"
if os.path.exists(_PYTHON311_PKG) and _PYTHON311_PKG not in sys.path:
    sys.path.insert(0, _PYTHON311_PKG)

from datetime import datetime

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

BASE_URL = "https://www.dasny.org"
LISTING_URL = "https://www.dasny.org/opportunities/rfps-bids"
OUTPUT_FILE = "dasny_scraped_data.json"


# ---------------------------------------------------------------------------
# Utility: text cleaning / dates
# ---------------------------------------------------------------------------
def _clean(text):
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _parse_date(raw):
    if not raw:
        return None
    raw = _clean(raw)
    # strip time part e.g. "08/19/2026 - 2:00 PM"
    raw = re.sub(r'\s*-?\s*\d{1,2}:\d{2}\s*(?:AM|PM)?', '', raw, flags=re.IGNORECASE).strip()
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
# Utility: Cloudflare email deobfuscation (defensive fallback only —
# DASNY's own contact emails are plain mailto: links, not obfuscated)
# ---------------------------------------------------------------------------
def decode_cf_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join(
            chr(int(cf_hex[i:i + 2], 16) ^ r)
            for i in range(2, len(cf_hex), 2)
        )
    except Exception:
        return None


def find_cf_emails_in_html(html):
    found = []
    for m in re.finditer(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)', html):
        decoded = decode_cf_email(m.group(1))
        if decoded and '@' in decoded:
            found.append(decoded)
    return found


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------
class DasnyScraper:
    def __init__(self):
        self.driver = None
        self.wait = None

    # ------------------------------------------------------------ setup
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
            self.wait = WebDriverWait(self.driver, 20)
            print("Chrome ready.")
            return True
        except Exception as e:
            print(f"Chrome setup failed: {e}")
            return False

    # ------------------------------------------------- listing / pagination
    def get_open_opportunities(self, max_count=None):
        """
        Collect opportunity detail URLs from the listing pages.
        Confirmed structure: each opportunity is a div.rfp-bid-wrapper;
        the real detail link is the anchor with exact text
        "View the full details for this opportunity" inside div.rfp-bid-links.
        """
        limit_str = str(max_count) if max_count is not None else 'ALL'
        print(f"\nCollecting {limit_str} open opportunities...")

        seen = set()
        results = []
        page = 0

        while True:
            url = f"{LISTING_URL}?page={page}"
            print(f"\n  [Page {page}] {url}")
            self.driver.get(url)
            time.sleep(2)

            cards = self.driver.find_elements(By.CSS_SELECTOR, "div.rfp-bid-wrapper")
            added = 0
            for card in cards:
                try:
                    link_el = card.find_element(
                        By.XPATH,
                        ".//div[contains(@class,'rfp-bid-links')]"
                        "//a[normalize-space(text())='View the full details for this opportunity']"
                    )
                    href = (link_el.get_attribute('href') or '').split('#')[0].rstrip('/')
                except Exception:
                    href = None

                if not href or href in seen:
                    continue
                seen.add(href)
                results.append({'url': href})
                added += 1
                if max_count is not None and len(results) >= max_count:
                    break

            print(f"  [Page {page}] Added {added}. Total: {len(results)}")

            if max_count is not None and len(results) >= max_count:
                print(f"  Reached cap of {max_count}. Stopping.")
                break

            # Confirmed stop condition: "Displaying X - Y of Z" in div.view-footer
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            total_match = re.search(
                r'Displaying\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)', body_text, re.IGNORECASE
            )
            if total_match:
                _, end_idx, total = (int(g) for g in total_match.groups())
                if end_idx >= total or added == 0:
                    print(f"  Reached end of listing ({end_idx} of {total}).")
                    break
            elif added == 0:
                print("  No results/no total-count marker found. Stopping.")
                break

            page += 1
            time.sleep(1)

        print(f"\nCollection complete. {len(results)} unique opportunities found.\n")
        return results

    # ------------------------------------------------- detail page extraction
    def extract_opportunity(self, url):
        print(f"  Scraping {url}")
        self.driver.get(url)
        time.sleep(2)

        html = self.driver.page_source

        title = self._get_title()
        header_fields = self._get_header_fields()
        description = self._get_description()
        contacts = self._get_contacts(html)
        documents = self._get_documents()
        bid_metadata = self._get_bid_metadata()

        solicitation_number = header_fields.get('Solicitation #')
        issue_date_raw = header_fields.get('Issue Date')
        due_date_raw = header_fields.get('Due Date') or header_fields.get('Proposal Due') or header_fields.get('Bid Due Date')
        classification = header_fields.get('Classification')
        sol_type = header_fields.get('Type')
        location_raw = header_fields.get('Location') or header_fields.get('Location Where Goods to be Delivered or Service Performed')
        goals_raw = header_fields.get('Goals (%)')
        status_raw = header_fields.get('Status')

        bid_deadline = _parse_date(due_date_raw)
        publication_date = _parse_date(issue_date_raw)

        status = "open"
        if status_raw:
            status = "closed" if "closed" in status_raw.lower() else "open"
        if bid_deadline:
            try:
                if datetime.strptime(bid_deadline, "%Y-%m-%d").date() < datetime.today().date():
                    status = "closed"
            except ValueError:
                pass

        loc_address, loc_city, loc_state, loc_zip = self._parse_location(location_raw)
        budget_min, budget_max = self._parse_budget(description or '')
        project_type = self._project_type(title, classification or '', description or '')
        trades = [t.strip() for t in re.split(r'[;\n,]', classification or '') if t.strip()]
        issuing_org = self._guess_issuing_org(title)
        add_link = self._first_url(description or '')

        if goals_raw:
            bid_metadata['goals'] = goals_raw

        source_id = "dasny_" + (solicitation_number or url.rstrip('/').split('/')[-1])
        source_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', source_id)

        return {
            "source_id": source_id,
            "source_url": url,
            "title": title,
            "description": description or None,
            "project_type": project_type,
            "status": status,
            "project_category": None,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "location_address": loc_address,
            "location_city": loc_city,
            "location_state": loc_state or "NY",
            "location_zip": loc_zip,
            "bid_deadline": bid_deadline,
            "publication_date": publication_date,
            "question_deadline": None,
            "issuing_organization": issuing_org,
            "solicitation_number": solicitation_number,
            "solicitation_type": sol_type,
            "contact_details": contacts,
            "trades": trades,
            "sqft": self._parse_sqft(description or ''),
            "duration": None,
            "cgac": None,
            "sub_tier": None,
            "fpds_code": None,
            "office": None,
            "aac_code": None,
            "base_type": None,
            "archive_type": None,
            "archive_date": None,
            "set_aside_code": None,
            "set_aside": None,
            "classification_code": None,
            "pop_country": "US" if (loc_address or loc_city or loc_zip) else None,
            "active_status": None,
            "award_number": None,
            "award_date": None,
            "awardee": None,
            "organization_type": None,
            "additional_info_link": add_link,
            "bid_metadata": bid_metadata,
            "documents": documents,
        }

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _get_title(self):
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, "div.rfp-bid-title h2 a")
            return _clean(el.text)
        except Exception:
            pass
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, "h1")
            return _clean(el.text)
        except Exception:
            return "Title not found"

    def _get_header_fields(self):
        """
        Extract header fields. Supports listing-style table (div.rfp-bid-info table)
        and detail-style wrappers (div.rfp-detail-item-wrapper).
        """
        fields = {}
        # Try table style first
        try:
            rows = self.driver.find_elements(
                By.CSS_SELECTOR, "div.rfp-bid-info table tbody tr"
            )
            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 2:
                        continue
                    label = _clean(cells[0].text).rstrip(':')
                    value = _clean(cells[1].text)
                    if label:
                        fields[label] = value
                except Exception:
                    continue
        except Exception:
            pass

        # Try wrapper style (used on many detail pages)
        try:
            wrappers = self.driver.find_elements(By.CSS_SELECTOR, "div.rfp-detail-item-wrapper")
            for w in wrappers:
                try:
                    label_el = w.find_element(By.CSS_SELECTOR, ".rfp-detail-text-label")
                    val_el = w.find_element(By.CSS_SELECTOR, ".rfp-detail-field-value")
                    label = _clean(label_el.text).rstrip(':')
                    value = _clean(val_el.text)
                    if label:
                        fields[label] = value
                except Exception:
                    continue
        except Exception:
            pass
            
        return fields

    def _get_description(self):
        """Confirmed: #rfp-bid-notice or #rfp-ad-notice .panel-body — plain <p> tags."""
        for selector in ["#rfp-bid-notice .panel-body", "#rfp-ad-notice .panel-body"]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = _clean(self.driver.execute_script("return arguments[0].textContent;", el))
                if text:
                    return text
            except Exception:
                pass
        return None

    def _get_contacts(self, html):
        """
        Confirmed: #rfp-contacts .panel-body -> each <h2> starts a new
        contact (role = heading text); following <p> lines (until next <h2>)
        are: name, title, org line(s), address line(s), country (skip),
        "Phone: X", "Email: <a>".
        """
        cf_emails = find_cf_emails_in_html(html)  # defensive fallback only
        cf_idx = 0

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
                // capture mailto href separately in case link text differs
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

        contacts = []
        for block in raw_blocks:
            role = _clean(block.get('role'))
            lines = [l for l in block.get('lines', []) if l]
            if not lines:
                continue

            contact = {
                "role": role, "name": None, "title": None,
                "email": None, "phone": None,
                "organization": None, "address": None,
            }

            org_lines, addr_lines = [], []
            name_set = False

            for raw_line in lines:
                if raw_line.startswith('__MAILTO__:'):
                    mailto = raw_line.replace('__MAILTO__:', '')
                    email = mailto.replace('mailto:', '').strip()
                    if email and '@' in email:
                        contact['email'] = email
                    continue

                line = _clean(raw_line)
                low = line.lower()

                if low.startswith('phone'):
                    contact['phone'] = _clean(re.sub(r'^phone:?\s*', '', line, flags=re.IGNORECASE))
                    continue
                if low.startswith('email'):
                    if not contact['email']:
                        em = re.search(r'[\w.\-]+@[\w.\-]+\.\w+', line)
                        if em:
                            contact['email'] = em.group(0)
                        elif cf_idx < len(cf_emails):
                            contact['email'] = cf_emails[cf_idx]
                            cf_idx += 1
                    continue
                if low in ('united states', 'usa'):
                    continue
                if re.match(r'^\d{5}(-\d{4})?$', line) or re.search(r',\s*(new york|ny)\b', low):
                    addr_lines.append(line)
                    continue
                if re.match(r'^\d+\s+\w+', line):  # street address
                    addr_lines.append(line)
                    continue

                if not name_set:
                    contact['name'] = line
                    name_set = True
                elif not contact['title']:
                    contact['title'] = line
                else:
                    org_lines.append(line)

            if org_lines:
                contact['organization'] = ' - '.join(org_lines)
            if addr_lines:
                contact['address'] = ', '.join(addr_lines)

            if contact.get('name') and (contact.get('email') or contact.get('phone')):
                contacts.append(contact)

        return contacts

    def _get_documents(self):
        """
        # RECON: attachments container not yet confirmed from a live sample.
        Best-effort: scan all <a> tags for document-like extensions,
        excluding known nav/login/plan-room noise.
        """
        docs = []
        seen_urls = set()
        try:
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for lnk in links:
                href = lnk.get_attribute('href') or ''
                name = _clean(lnk.text) or ''
                if not href or href.startswith('mailto:') or href.startswith('#'):
                    continue
                if '/user/login' in href:
                    continue
                is_doc = any(ext in href.lower() for ext in [
                    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.dwg'
                ])
                if not is_doc or href in seen_urls:
                    continue
                seen_urls.add(href)
                ext_match = re.search(r'\.([a-zA-Z]{2,5})(?:\?|$)', href)
                file_type = ext_match.group(1).lower() if ext_match else 'unknown'
                docs.append({
                    "name": name if name else f"Document_{len(docs)+1}",
                    "url": href,
                    "file_type": file_type,
                    "file_size": None,
                })
        except Exception as e:
            print(f"  Warning: document extraction error: {e}")
        return docs

    def _get_bid_metadata(self):
        """
        Catch-all: Planholders table (#rfp-planholders-list) and
        Interested Subs/Suppliers table (#rfp-interestedsubssuppliers-list).
        IDs confirmed from link fragments on the listing page.
        """
        meta = {}
        for anchor_id, out_key in [
            ('rfp-planholders-list', 'planholders'),
            ('rfp-interestedsubssuppliers-list', 'interested_subs_suppliers'),
        ]:
            try:
                js = f"""
                var el = document.getElementById('{anchor_id}');
                if (!el) return null;
                // the table may be the element itself or a descendant/ancestor
                var table = el.tagName.toLowerCase() === 'table' ? el : el.querySelector('table');
                if (!table) {{
                    var parent = el.closest('.panel, .panel-body, div');
                    table = parent ? parent.querySelector('table') : null;
                }}
                if (!table) return null;
                var rows = [];
                var trs = table.querySelectorAll('tr');
                for (var r=0; r<trs.length; r++){{
                    if (trs[r].querySelectorAll('td').length === 0) continue;
                    var cells = trs[r].querySelectorAll('td,th');
                    var rowVals = [];
                    for (var c=0; c<cells.length; c++){{
                        rowVals.push((cells[c].innerText||'').trim());
                    }}
                    if (rowVals.length) rows.push(rowVals);
                }}
                return rows;
                """
                rows = self.driver.execute_script(js)
                if rows:
                    meta[out_key] = rows
            except Exception:
                pass
        return meta

    # ------------------------------------------------------------------
    def _parse_location(self, raw):
        address = city = state = zip_code = None
        if not raw:
            return address, city, state, zip_code
        raw = _clean(raw)
        z = re.search(r'\b(\d{5}(?:-\d{4})?)\b', raw)
        if z:
            zip_code = z.group(1)
            raw = raw.replace(zip_code, '').strip(' ,-')
        s = re.search(r'\b([A-Z]{2})\b', raw)
        if s:
            state = s.group(1)
            raw = re.sub(r'\b' + re.escape(state) + r'\b', '', raw, count=1).strip(' ,-')
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        if len(parts) >= 2:
            address = ', '.join(parts[:-1])
            city = parts[-1]
        elif len(parts) == 1:
            if any(c.isdigit() for c in parts[0]):
                address = parts[0]
            else:
                city = parts[0]
        return address, city, state or 'NY', zip_code

    def _parse_budget(self, text):
        """Note: many DASNY notices have no stated cost range at all — null is expected/common."""
        pattern = re.compile(
            r'(?:estimated\s+cost|est\.?\s+cost|budget|value|contract\s+value)'
            r'\D{0,30}\$\s*([0-9,]+(?:\.\d+)?)\s*(million|m|k|thousand)?'
            r'(?:.{0,20}\$\s*([0-9,]+(?:\.\d+)?)\s*(million|m|k|thousand)?)?',
            re.IGNORECASE
        )
        m = pattern.search(text or '')
        if not m:
            return None, None

        def to_val(num, suf):
            if not num:
                return None
            v = float(num.replace(',', ''))
            suf = (suf or '').lower()
            if suf in ('million', 'm'):
                v *= 1_000_000
            elif suf in ('k', 'thousand'):
                v *= 1_000
            return v

        v1 = to_val(m.group(1), m.group(2))
        v2 = to_val(m.group(3), m.group(4))
        if v1 is not None and v2 is not None:
            return min(v1, v2), max(v1, v2)
        return None, v1

    def _parse_sqft(self, text):
        m = re.search(r'\b([0-9,]+)\s*(?:sq\.?\s*ft\.?|sf|square\s+feet)\b', text or '', re.IGNORECASE)
        if m:
            return int(m.group(1).replace(',', ''))
        return None

    def _project_type(self, title, category, description):
        combined = f"{title} {category} {description}".lower()
        construction_kw = [
            'construction', 'rehabilitation', 'renovation', 'hvac', 'electrical',
            'plumbing', 'roofing', 'facade', 'façade', 'masonry', 'demolition',
            'building', 'fisp', 'elevator', 'roof', 'abatement',
        ]
        if any(k in combined for k in construction_kw):
            return "construction_bid"
        return "rfp"

    def _guess_issuing_org(self, title):
        """
        # RECON: best-effort only. DASNY titles usually start with the client
        agency (CUNY, OASAS, OPWDD, OMH, etc.) as the first word/phrase.
        """
        if not title:
            return None
        m = re.match(r'^([A-Z]{2,6})\b', title)
        if m:
            return m.group(1)
        return None

    def _first_url(self, text):
        m = re.search(r'https?://[^\s\)]+', text or '')
        return m.group(0).rstrip('.,;)') if m else None

    # ------------------------------------------------------------------
    # Resume + save
    # ------------------------------------------------------------------
    def load_existing(self, filename=OUTPUT_FILE):
        if not os.path.exists(filename):
            return [], set()
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                return [], set()
            seen = {rec.get('source_url') for rec in existing if rec.get('source_url')}
            print(f"Resume: loaded {len(existing)} existing records. Skipping those URLs.")
            return existing, seen
        except Exception as e:
            print(f"Warning: could not load existing data ({e}). Starting fresh.")
            return [], set()

    def save(self, data, filename=OUTPUT_FILE):
        tmp = filename + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, filename)
        print(f"Saved {len(data)} records to {filename}")

    def scrape(self, max_opportunities=None, output_file=OUTPUT_FILE):
        existing_records, already_done = self.load_existing(output_file)

        cap = max_opportunities if max_opportunities is not None else 999_999
        fetch_cap = cap if cap == 999_999 else cap + len(already_done)
        opps = self.get_open_opportunities(max_count=fetch_cap)
        if not opps:
            print("No opportunities found.")
            return existing_records

        pending = [o for o in opps if o['url'] not in already_done]
        skipped = len(opps) - len(pending)
        if skipped:
            print(f"Skipping {skipped} already-scraped opportunities. {len(pending)} remain.")
        if not pending:
            print("All opportunities in this batch are already scraped.")
            return existing_records

        new_results = []
        failed = 0
        for i, opp in enumerate(pending):
            print(f"\n[{i+1}/{len(pending)}] {opp['url']}")
            try:
                data = self.extract_opportunity(opp['url'])
                if data:
                    new_results.append(data)
                    print(f"  Title: {data['title']}")
            except Exception as e:
                print(f"  ERROR: {e}")
                failed += 1

            if (i + 1) % 25 == 0 and new_results:
                self.save(existing_records + new_results, filename=output_file)

            time.sleep(0.8)

        all_results = existing_records + new_results
        print(f"\nDone. New: {len(new_results)}, Failed: {failed}, Total: {len(all_results)}")
        return all_results

    def close(self):
        if self.driver:
            self.driver.quit()
            print("Browser closed.")


def main():
    print("=" * 60)
    print("  DASNY Scraper — RFP/Bid Opportunities")
    print("=" * 60)

    scraper = DasnyScraper()
    try:
        if not scraper.setup_chrome():
            return

        print("\n  1. Test run   (first 20 opportunities)")
        print("  2. Medium run (first 100 opportunities)")
        print("  3. Full run   (ALL opportunities)")
        while True:
            choice = input("\n  Enter choice (1/2/3): ").strip()
            if choice == "1":
                max_opps = 20
                break
            elif choice == "2":
                max_opps = 100
                break
            elif choice == "3":
                max_opps = None
                break
            else:
                print("  Invalid choice.")

        data = scraper.scrape(max_opportunities=max_opps, output_file=OUTPUT_FILE)
        if data:
            scraper.save(data, filename=OUTPUT_FILE)
            print(f"\nFinal output: {OUTPUT_FILE} ({len(data)} records)")
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