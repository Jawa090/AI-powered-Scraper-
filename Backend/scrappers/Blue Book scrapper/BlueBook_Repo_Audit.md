# Blue Book Scraper — GitHub Repository Audit & Rebuild Plan

**Date:** 19 October 2026
**Target site:** The Blue Book Network (`thebluebook.com`) — US commercial construction directory (contractors, subcontractors, suppliers, owners/developers)
**Goal:** maximize *completeness* (no missing companies/fields), *accuracy* (no false phones, no duplicates), and *efficiency* (fast, resumable, low failure rate)

---

## 1. Executive summary

There is no single canonical "Blue Book scraper" on GitHub. Search surfaced **three** relevant repositories, and all three were cloned and reviewed file-by-file:

| # | Repository | What it actually is | Verdict |
|---|---|---|---|
| A | [safi025/BlueBook_Scrapper](https://github.com/safi025/BlueBook_Scrapper) (2024, MIT) | Selenium script + Jupyter notebook that **brute-forces numeric profile IDs** (`/iProView/{id}/…/locations-contacts/`) with 15 parallel Chrome browsers via a Tor proxy | Educational prototype. Right *page* (locations-contacts), wrong *discovery method*. Its own notebook output logs thousands of failures. Do not use as a base. |
| B | [AbdulRehmamn/blue-book](https://github.com/AbdulRehmamn/blue-book) (Oct 2026, no license) | Playwright + Tkinter desktop collector: paste a search URL → follow pagination → visit profile pages → SQLite resume → Excel/CSV export. Ships a real 2,012-company database | **Best architecture of the three** (discovery, dedupe, resume, conservative phone parsing, 10 passing tests) — but it never visits the `locations-contacts` sub-page, which is exactly where addresses, phone numbers and key contacts live. Result in its own bundled export: **phone on only 473/2,012 companies (23.5%), address 0%, contact name 0%.** |
| C | [automationbyexperts/thebluebook-scraper](https://github.com/automationbyexperts/thebluebook-scraper) (2026, MIT) | **Not a scraper** — Python/JS client examples that call a paid Apify Actor (`fayoussef/thebluebook-scraper`, currently returning 404 on Apify) | No scraping code to learn from, but its README/sample output is a useful **target data schema**: trades, certifications (MBE/WBE/DBE…), service areas, established/size/volume, contacts[], projects[]. |

**Key insight that drives the rebuild:** Repo A scrapes the *right page* with the *wrong discovery* (ID guessing). Repo B has the *right discovery* (search → pagination → profiles, with resume) but scrapes the *wrong / incomplete page set* (profile root only). The advanced scraper built alongside this report (`bluebook-scraper-v2/`) combines both lessons, plus modern practices neither repo has: HTML-first fetching with browser fallback, coverage accounting against the site's own "N Companies Found" count, dedupe by numeric company ID, relational storage for locations/contacts, layered extractors (JSON-LD → microdata → semantic sections → labelled text), HTML snapshots with offline re-parsing, and a legacy importer that rescues Repo B's records (validated live below: 2,011 imported, 1 bogus row rejected, 1,538 phone-less companies queued first for proper enrichment).

**Live-site verification (19 Oct 2026):** search `region=3&class=2200` (Los Angeles general contractors) now advertises **2,057 companies** (Repo B's snapshot captured 2,012 — the directory changes over time, another reason coverage must be measured per run, not assumed). A sample profile's `locations-contacts` page exposes, in plain server-rendered HTML: street address, `tel:` phone *and* fax links, company website, and key contacts grouped by department (Owners/Principals, Estimating, Finance…) with name, title and phone each. Direct requests from this sandbox IP receive CloudFront **403** — the production scraper must therefore run from the user's own machine/browser session (as Repo B does), pause for any human verification, and stop rather than attempt to evade a hard block. No CAPTCHA solving, proxy rotation or fingerprint evasion is included in the rebuild.

---

## 2. Method

- GitHub search (`Blue Book scraper`, `thebluebook scraper`, topic pages), then `git clone` of all three repos into `research/`.
- Full inventory: every source file, script, config, notebook cell (including saved outputs), test, launcher, bundled SQLite DB and exports.
- Ran Repo B's test suite: **10/10 pass**. Syntax-checked Repo A's script (compiles; its failures are runtime/architectural).
- Statistical audit of Repo B's bundled `progress.sqlite3` + `BlueBook_Leads.csv/.xlsx` (field fill-rates, duplicates, job states, page coverage).
- Notebook forensics on Repo A: 5 near-duplicate code cells = 5 experiment variants; counted their saved error outputs.
- Live spot-checks of a current search page, a profile root page and two `locations-contacts` pages (rendered text) to map the fields the site actually publishes today, and to confirm URL schemes:
  - Search: `/search.html?region={r}&class={c}[&searchTerm=…][&page={n}]` (also `/search-build/search.html`, and newer `/iSearch/results/{state}/{city}/{trade}/sc/{id}/` seen in Repo C's docs)
  - Profile: `/iProView/{company_id}/{slug}/{category}/`
  - Sub-pages: `…/locations-contacts/`, `…/completed-projects/`, `…/reviews-ratings/`

---

## 3. Repo A — safi025/BlueBook_Scrapper (Selenium, ID enumeration)

**Files:** `Scrapper.py` (178 lines), `parallelization.ipynb` (6 cells; cell 5 is byte-identical to `Scrapper.py`), 2-line README, MIT LICENSE, generic `.gitignore`. **No** `requirements.txt`, no tests, no config.

### How it works

```
range(1780000, 1785000)                      # guess 5,000 consecutive IDs
  └─ ThreadPoolExecutor(max_workers=15)
       └─ per ID: launch a NEW headless Chrome (via Tor SOCKS5 127.0.0.1:9050)
            GET /iProView/{id}/crawford-tracey-corp/subcontractors/locations-contacts/
            wait ≤10s for one absolute XPath; extract by absolute XPaths:
              name, address, phone (click "View Phone" if masked), company-info blob,
              website, industry (breadcrumb link #3), up to 7 key contacts (click-to-reveal each)
            quit browser
  └─ append one CSV row per contact (company fields repeated) to a hard-coded Mac path
```

### What it gets right (worth keeping)

1. **Targets `locations-contacts`** — the single richest page for address/phone/contacts. Repo B misses this entirely.
2. Knows phones may be behind a **"View Phone" click-to-reveal** and handles the reveal interaction.
3. **Denormalized CSV** (one row per contact) is genuinely convenient for lead lists — kept as an export option in v2 (`companies.csv` + separate `contacts.csv`).
4. `WebDriverWait` on a landmark element instead of blind sleeps (partially — fixed `sleep(2)`s remain).

### Defects (with evidence)

| Severity | Defect | Consequence |
|---|---|---|
| 🔴 Critical | **Discovery by ID brute-force.** IDs are sparse (Repo B's real LA dataset spans IDs 4,265 → 1,921,697 for just 2,011 companies). Guessing `1780000–1785000` wastes most requests on dead IDs and can never prove coverage of a trade/region | Massive missing-record rate; no notion of "all plumbers in Texas" |
| 🔴 Critical | **One full Chrome per ID × 15 threads.** Notebook outputs: 1,928× `ERR_CONNECTION_REFUSED` in one cell, renderer timeouts of ~294 s, `no such window` storms, Tor `ERR_SOCKS_CONNECTION_FAILED` | Slow, RAM-hungry, flaky; failures are *printed and lost* — no retry queue |
| 🔴 Critical | **No resume/checkpoint.** CSV opened with `'w'` (truncates), progress lives only in stdout | Any crash = restart from zero, with no record of which IDs succeeded |
| 🟠 High | **Hard-coded wrong slug** `crawford-tracey-corp/subcontractors` for every company; works only insofar as the server keys off the numeric ID and redirects | Fragile; breaks canonical URLs, breadcrumbs, category |
| 🟠 High | **Absolute XPaths** (`//*[@id="locationsPage-1"]/div/div[1]/div/div[1]/h3`, contacts capped at exactly 7, only `locationsPage-1`) | Any layout tweak, 2nd location, or 8th contact = silent data loss (whole company discarded if the "FaceTime modal" check trips — `return None`) |
| 🟠 High | `company_info` stored as one raw text blob; industry = breadcrumb link #3 | Established/size/volume not usable as fields |
| 🟡 Medium | Hard-coded output path `/Users/safi.uddin/Desktop/…`; `webdriver_manager` imported but unused in final version (an earlier cell passes it as positional arg → *every* task fails with `multiple values for argument 'options'`); Tor required but undocumented/unmanaged | Not runnable by anyone else as shipped |
| 🟡 Medium | No rate limiting, backoff, dedupe, logging, or block detection | Gets throttled/blocked; Tor usage reads as evasion tooling |

**Lesson:** *Separate discovery from enrichment, and never guess IDs when the site's own search enumerates exactly the companies you want.*

---

## 4. Repo B — AbdulRehmamn/blue-book (Playwright collector) ⭐ best base

**Files:** `core.py` (parser + SQLite store, 180 dense lines), `app.py` (Tkinter GUI + Playwright runner, 129 lines), `requirements.txt` (playwright, openpyxl), `START.bat` (Windows venv launcher), `test_core.py` / `test_repair.py` / `test_restart.py` (10 tests, all pass), `README.md`, `COVERAGE.md`, bundled `progress.sqlite3` (2,096 jobs / 2,012 leads) + `exports/BlueBook_Leads.{csv,xlsx}`. No license file.

### How it works

```
Tkinter GUI: paste /search.html URL(s) + pick a category label
  └─ Playwright persistent Chromium (headed, dedicated browser_session/), ONE page, sequential, 4 s between jobs
       ├─ kind=listing: parse cards (.single_result_wrapper, data-proview-url, itemprop=name)
       │     → save leads, enqueue profile jobs + same-search pagination jobs
       └─ kind=profile: parse profile root page only
             phones: tel:/itemprop → labelled blocks → name-matched JSON-LD (fax + Blue Book support # excluded)
             address: itemprop=address; contact: first schema.org Person only
  └─ SQLite jobs queue (pending/done + error) → resume skips done; restart archives jobs, keeps leads
  └─ Export CSV (utf-8-sig, formula-injection guard) + XLSX (freeze panes, autofilter)
  └─ Human verification: pause, user solves in the open browser, click Continue; hard 403 → stop. No bypass attempts.
```

### What it gets right (kept and extended in v2)

1. **Search-driven discovery with scoped pagination** — only follows `page=` links whose other params match the seed, so the crawl can't wander into unrelated searches.
2. **Resumable SQLite job queue + dedupe by canonical URL**; merges preserve existing non-empty values; "retry missing phones" re-queues only incomplete profiles; restart archives jobs but preserves leads. This is the correct skeleton.
3. **Precision-first phone extraction**: scoped to the matching business's microdata/JSON-LD, strips nav/footer/ads, excludes fax and the site's own support number (888-720-1710), never regex-scans the whole page. High trust per number.
4. **Responsible access pattern**: single headed browser, human-in-the-loop verification, stops on hard blocks, honest README ("extractor repair, not a claim the 1,539 numbers were recovered").
5. **Offline repairs**: "Import saved HTML" and a real (if small) test suite; CSV-injection guard on export.

### Defects (with evidence from its own bundled data)

| Severity | Defect | Evidence / consequence |
|---|---|---|
| 🔴 Critical | **Never visits `locations-contacts`** (or `completed-projects`). Enriches profile root only, and never clicks "View Phone" | Bundled export: **phone 23.5% (473/2,012), address 0%, contact_name 0%, contact_title 0%**; DB shows 473 profile jobs `done`, exactly the 473 with phones; 1,539 pending. The missing data was one click away |
| 🟠 High | **Sequential single page, fixed 2 s render wait + 4 s gap** | ≈6 s+/job → the remaining 1,539 profiles alone ≈ 2.5–4 h; yet pages are server-rendered (phones are in `tel:` hrefs), so most fetches don't need full rendering at all |
| 🟠 High | **Thin schema**: one contact max, no website/trades/certifications/service-area/firmographics/projects/socials; leads stored as JSON blobs in a 2-column table (no indexes, timestamps, attempts) | Can't answer "all DBE electrical subs serving Harris County with an estimator's direct line" |
| 🟠 High | **Any job error breaks the whole run** (`break` in the runner; zero-card page = fatal) | One layout hiccup stops a multi-hour crawl; no transient retry/backoff |
| 🟡 Medium | Dedupe key is the full slug URL, not the numeric ID; `canonical('')` returns the homepage, and the bundled data contains **one bogus lead whose `profile_url` is `https://www.thebluebook.com`** | Same company under `…/general-contractors/` vs `…/subcontractors/` can duplicate; junk rows possible |
| 🟡 Medium | URL/provenance drift: the DB holds **84 listing jobs for 83 pages** (seed without `page` + an explicit `page=1` duplicate), the subset-style same-search rule let the site's stray `searchTerm=Computer Room Construction (DBE,WBE)` into every pagination URL, and each lead's single `source_url` is overwritten on every re-encounter | Wasted re-scrapes; provenance in the export doesn't reliably show where a company was first found. v2: `page=1`≡seed, strict param matching with a benign-extra allowance for that label param, append-only multi-row provenance |
| 🟡 Medium | Only `/search.html` seeds accepted — newer `/iSearch/results/…` URLs and direct profile URLs rejected; category dropdown is just a label (documented, but a footgun) | Users pasting current site URLs may be turned away |
| 🟡 Medium | Hand-rolled `HTMLParser` tree (text propagated to every ancestor; no CSS selectors); phones normalized to digit strings, multiple numbers `;`-joined with label/type lost; no coverage accounting vs the site's "N Companies Found" | Hard to extend; can't distinguish main line vs contact mobile; "queue complete" ≠ "complete data" (2,012 found vs 2,057 advertised today) |
| ⚪ Low | Code is minified-style (one-line methods), GUI and crawl logic intertwined, no CLI → can't schedule/headless-run; bundled DB predates current `core.py` (status strings differ) | Maintainability |

**Lesson:** *Repo B solved reliability of the crawl loop; it did not solve completeness of the page set or richness of the schema. Precision-first extraction needs a recall layer underneath it (more pages, more extractor fallbacks, each value tagged with provenance/confidence).*

---

## 5. Repo C — automationbyexperts/thebluebook-scraper (Apify wrapper)

Three example callers (Python, JavaScript, cURL in README), `input.json {startUrls, maxItems, disableEmailScrape}` and `sample-output.json`. **The scraping itself is a closed, paid Apify Actor** — and that Actor page currently returns 404, so even the paid path is uncertain. Two things are still valuable:

- **Target schema** (adopted in v2): `company_id, name, phone, email, website, city_state, full_address, trade[], certifications[], service_area[], established, company_size, annual_volume, listed_since, contacts[{name, role, phone}], projects[{name, location, type, status, date, gc_name}]`.
- **Confirmed constraints** (also visible on live pages): emails are *not* published on Blue Book (gated behind a contact form) — the Actor enriched email by visiting each company's *own* website, which v2 treats as an optional, off-by-default phase; contacts/projects only exist for companies that maintain those sub-pages.

---

## 6. What the site actually publishes (field map for the rebuild)

Verified on live pages, 19 Oct 2026:

| Data | Search card | Profile root | `locations-contacts` | `completed-projects` |
|---|:-:|:-:|:-:|:-:|
| Company name + profile URL/ID | ✅ | ✅ | ✅ | ✅ |
| Phone (`tel:` href, sometimes behind "View Phone") | sometimes | sometimes | ✅ **+ fax, alt phone** | – |
| Street address / city / state / ZIP | city only | – | ✅ **per location** | – |
| Website (UTM-tagged outbound link) | ✅ | ✅ | ✅ | – |
| Key contacts (name, title, phone, **department group**) | – | – | ✅ **all groups** | – |
| Trades / "What We Do" | partial list | ✅ | breadcrumb | – |
| Regions & counties serviced | – | ✅ | – | – |
| CSI codes (can be hundreds) | – | ✅ | – | – |
| "Listed since", story text | – | ✅ | – | – |
| Company info (established, size, volume…) | – | ✅ (label:value list) | – | – |
| Project experience | thumbnails | summary | – | ✅ |
| Certifications (MBE/WBE/DBE…) | badges/searchTerm | badges/text | – | – |
| Email | ❌ never public on Blue Book (contact-form gated) | | | |
| Expected result count ("2,057 Companies Found") | ✅ heading | | | |

DOM hooks corroborated by both open-source repos: cards `.single_result_wrapper` with `data-proview-url` + `itemprop="name"`; profile sections `#companyInfoSection`, `#keyContactSection`, `#locationsPage-{n}`, `#proViewBreadCrumbs`; microdata `itemprop=telephone/address`, `itemtype=…/Organization|LocalBusiness|Person`; JSON-LD blocks (name-matched before trusting, per Repo B).

---

## 7. Root-cause map: goal → failure in old repos → fix in v2

| Goal | Root cause (A / B) | Fix implemented in `bluebook-scraper-v2` |
|---|---|---|
| **No missing companies** | A guesses IDs; B follows only *linked* pagination (sites show a page window, not all pages) and never checks totals | Parse "N Companies Found"; follow pagination links **and synthesize `page=2..⌈N/per-page⌉`** for `search.html`; per-search coverage report (`discovered / expected`) in `stats` + Coverage sheet |
| **No missing fields** | B reads 1 of 3 relevant pages, first Person only, no click-to-reveal; A caps contacts at 7, one location | Enrich **profile + locations-contacts** (+ optional projects); *all* locations, *all* contact groups; reveal "View Phone" only when the number isn't already in the `tel:` href; layered extractors with fallbacks |
| **No duplicates** | URL-string keys (slug/category variants; bogus homepage row) | Primary key = **numeric `company_id`** parsed from `/iProView/{id}`; slug variants merge, provenance kept in `company_sources`; invalid/no-ID rows rejected with a count |
| **No false phones** | A: whatever the XPath lands on | Repo B's scoping rules retained (tel/microdata/JSON-LD/labelled only, fax + support-number exclusion, strip nav/footer/ads) **+ provenance & confidence per phone** (`tel_link` > `json_ld` > `microdata` > `labelled_text`), E.164 normalization, NANP validation |
| **Fewer errors / resumable** | A: none; B: one error kills the run | Job queue with `attempts`, exponential backoff for *transient* errors only, per-job checkpointing, graceful stop; **403/challenge → pause for human (headed) or stop — never auto-retried**; HTML snapshots + `reparse` so parser fixes don't cost a re-crawl |
| **Speed** | A: 15 browsers thrashing; B: full render + fixed waits for every page | **HTTP-first** via the browser context's request API (shares the user's session cookies; pages are server-rendered) with marker validation, **full-page render only as fallback**; resource blocking (images/media/fonts) in render mode; wait-on-selector instead of fixed sleeps; still sequential + configurable polite delay (default 3 s) |
| **Usable output** | A: one CSV on a Mac desktop; B: single flat sheet | Relational SQLite (companies / locations / contacts / values / sources / jobs / searches) → exports: `companies.csv` (flat, CRM-ready), `contacts.csv`, `locations.csv`, `coverage.csv`, multi-sheet `BlueBook_Leads.xlsx`, nested `companies.jsonl`; completeness score per company |
| **Don't lose existing work** | — | `import-legacy-db` migrates Repo B's `progress.sqlite3`: 2,012 leads in, bogus homepage row rejected, all companies queued for locations-contacts enrichment (phone-less first) |

### Architecture (v2)

```
seeds (search.html | iSearch/results | iProView profile | seeds.txt)
  └─ Discovery ── listing pages ──► companies (dedupe by company_id) ──► coverage vs "N Found"
  └─ Enrichment ─ profile root ──► trades, service area, firmographics, story, socials
                └ locations-contacts ──► locations[], phones/fax, key contacts[] by department
                └ (optional) completed-projects ──► projects[]
  Fetch: HTTP-first (session cookies) → validate markers → fallback: rendered page (+ View-Phone reveal)
  Store: SQLite (WAL) jobs/searches/companies/locations/contacts/values/sources; HTML snapshots on disk
  Export: CSV ×4 + XLSX (4 sheets) + JSONL;  stats: fill-rates, coverage, extractor health
```

---

## 8. Responsible-use boundaries (built into v2)

- Collect **publicly displayed business information only**; respect the site's Terms and `robots.txt`; keep the default rate low and sequential.
- **No anti-bot evasion**: no CAPTCHA solving, proxy/Tor rotation, or fingerprint spoofing. Verification is completed manually by the user in their own browser session; a hard block ends the run (Repo B's model — the right one).
- Emails are not published by Blue Book; v2 leaves `email` empty unless an address is *publicly listed* in page markup. Any future "visit company website for email" enrichment is a separate, opt-in phase.
- Key-contact names/phones are personal data in many jurisdictions even when business-related — store and use them under your own lawful basis/outreach rules (e.g., CAN-SPAM/state privacy laws). This is not legal advice.

---

## 9. Recommended next phases

1. **Live calibration run** (user's machine): 1 search page + ~10 profiles with `--save-html`; send snapshots back if any field fill-rate looks off → tune selectors, `reparse` offline, no re-crawl needed.
2. **GUI wrapper** over the same core (Repo B proved the demand) — the v2 CLI/core split is designed for this.
3. Optional enrichments: company-website email/social discovery (opt-in), Google Places cross-match for address/phone verification, dedupe across directories.
4. Scheduling/change-detection: content hashes already stored per snapshot → "what changed since last run" reports.

---

*Artifacts: clones in `research/` (3 repos), rebuild in `bluebook-scraper-v2/` with its own README, tests and fixtures. All statistics above were computed directly from the cloned files on 2026-10-19.*

---

## 10. Phase-2 addendum: keyword-based agent (v2.1.0)

The follow-up rebuild turned the seed-URL scraper into a reusable keyword agent and included a second line-by-line audit of the v2 code. The implementation and exact user-facing behaviour are documented in `bluebook-scraper-v2/README.md`; the detailed change list is in `bluebook-scraper-v2/CHANGELOG.md`.

### Live/indexed search mechanics incorporated

- Blue Book discovery is primarily **class + region**. The planner maps user keywords/synonyms/trade groups to class codes and cities/counties/states to candidate regions.
- Observed targeted parameters include `companylocatedin=City_ST`, `geoareaserviced=County County(ST)`, `geographicarea`, `projectspecialization`, `projecttypes`, `brands`, `associations`, `csi-group`, `searchTerm`, `nameSearch`, `sortfacets=az`, and `page` across `search.html`, `city-search.html`, and `search-build/search.html`.
- Result pages can repeat one company for multiple associated locations. v2.1 tracks raw listing rows separately from unique `company_id`s and preserves the branch data before dedupe.
- Result pages expose bounded Related Searches/Did-You-Mean class links. Balanced/broad modes can learn additional class codes dynamically while preserving geography/filters.
- No native ZIP search parameter was verified. ZIP input is mapped to inferred-state regions, retained in metadata, and explicitly warned rather than presented as a native Blue Book ZIP filter.

### Principal phase-2 fixes

- Crawler exceptions, final redirects, and non-200 statuses are handled per job; bad pages cannot be silently marked successfully ingested.
- Listing validation distinguishes genuine zero-result pages from unrecognized shells, and profile validation no longer uses a database-known name as evidence that an empty page was valid.
- Card/profile/contact parsers retain all public phones/emails, branch addresses, trade codes, JSON-LD address/email, company-info pairs, alternate contact rows, and project labels.
- Primary identity remains numeric Blue Book ID. Conflicting names/phones/websites/emails become alternates. Cross-ID candidates are reported from normalized-name plus phone/domain/address evidence but are not automatically merged or deleted.
- Search totals use raw rows and maximum observed page size; `stats` reports unique coverage and raw-row coverage separately.
- Exports lead with the requested 11-column business view and retain full relational/provenance/duplicate/coverage outputs.

### Phase-2 validation

- 39/39 offline tests pass and all source/tests compile.
- Repo B legacy import still reproduces 2,011 valid companies, 1 rejected artifact, 473 primary phones, 624 preserved alternate phone values, 0 fake locations, and 1,538 phone-less companies queued for enrichment.
- Keyword plans, dry-runs, config loading, fixture imports/exports, stats, duplicates, and doctor checks were run locally in the sandbox.
- A live end-to-end Playwright crawl remains untested here: Playwright is not installed in the sandbox and direct sandbox egress receives Blue Book/CloudFront 403. Search mechanics were checked through live/indexed research pages, but a headed calibration run on the user's machine/session is still required before claiming live fill rates or complete result capture.

---

## 11. Phase-3 addendum: exact six-column individual contacts (v2.2.0)

Phase 3 adds a person-level delivery shape without discarding the richer audit exports:

- People extraction now searches Key Contacts, Principal Contacts, Company Management, leadership/team and department sections, Company Info role labels, schema.org `Person` data, profile-root embedded sections, and named location blocks.
- `export-contacts` writes a separate one-sheet `bluebook_contacts_exact.xlsx` with exactly **Blue Book Profile Link, Company Name, Company Website, Person Name, Phone Number, Email**.
- The workbook has one row per company + conservatively normalized person name. Companies with no named people retain one blank-person row. Similar names are not merged; suffixes and token order remain distinct.
- Direct person phones win over the company/main-location business phone. Company-email fallback is guarded so one person's sole direct address is not assigned to colleagues. Missing values stay blank; no placeholders or constructed emails are permitted.
- Final export validation enforces headers/order, scalar cells, no duplicate company/person keys, and no exact duplicate rows.
- Validation after phase 3: **46/46 offline tests pass**, compile succeeds, and an exact-format workbook generated from the imported Repo B legacy snapshot contains 2,011 unique company rows (473 with business phone) and zero duplicate/placeholder rows. That legacy source contains no stored people or websites, so it is a format/import validation artifact—not evidence of a fresh person-enriched live crawl. A local headed crawl is still required to populate people/websites for a new target search.
