# Adding a Modular Scraper

This guide details how to add a new data scraper to the modular scraper framework (Phase P6).

The scraper framework is strictly modular:
- Scrapers live in `Backend/scrappers/<name>.py`.
- All scrapers inherit `BaseScraper` from `scrappers.base`.
- All external consumers interact exclusively via `scrappers.controller`. No external code imports specific scraper files.

---

## Step 1: Copy and Implement Scraper

1. Copy `Backend/scrappers/_template.py` to `Backend/scrappers/<name>.py`.
2. Define class `<Name>Scraper(BaseScraper)`.
3. Set the class attribute `meta: ScraperMeta` with:
   - `id`: unique lowercase alphanumeric string (e.g. `austinbids`).
   - `name`: human-readable title.
   - `description`: concise summary of data sources.
   - `record_kind`: `"opportunity"` (bids, contracts) or `"company"` (business directories).
   - `category`: high-level domain.
   - `version`: semantic version string (`"1.0.0"`).
   - `coverage`: geographical coverage dict (e.g. `{"city": "Austin", "state": "TX"}`).
   - `supports`: subset of `["limit", "keyword", "location"]`.
   - `fields`: list of standard fields extracted.
   - `required_env`: list of environment variable names required for authentication (if any).
   - `default_limit` and `max_limit`: integer bounds.
4. Implement `__init__(self, ctx=None)`:
   - Must never raise exceptions for missing environment variables or credentials.
5. Implement `scrape(self, params: ScrapeParams) -> Iterator[Dict[str, Any]]`:
   - Yields raw dictionary records.
   - Filters by keyword and location according to `params`.
   - Checks `self.ctx.should_cancel()` periodically.
6. Implement `to_standard(self, raw: Dict[str, Any]) -> StandardRecord`:
   - Maps raw source fields to `StandardRecord`.
   - For opportunities: sets `external_id` (numeric or per-source unique ID).
   - For companies: sets `external_id` or leaves `None` for fingerprint-based deduplication.
   - Missing fields must be `None` (never fabricate email or placeholder phone numbers).
7. Implement `close(self)`:
   - Clean up browser or network sessions. Must be safe to invoke multiple times.

---

## Step 2: Create Test Fixtures

Create offline JSON fixtures in `Backend/tests/fixtures/<name>/records.json`.
The fixtures should contain at least 2 realistic raw or standardized records extracted from the source.

---

## Step 3: Register in Controller

Open `Backend/scrappers/controller.py`:
1. Import your scraper:
   ```python
   from scrappers.<name> import <Name>Scraper
   ```
2. Add `<Name>Scraper` to the `REGISTERED_SCRAPERS` tuple:
   ```python
   REGISTERED_SCRAPERS = (
       BonfireScraper,
       DasnyScraper,
       JWizScraper,
       NyscrScraper,
       <Name>Scraper,
   )
   ```

Nothing else in the codebase needs to be modified.

---

## Step 4: Verify Contract Tests

Run contract tests to verify registration, metadata, and fixture conversion:
```bash
python -m pytest Backend/tests/unit/test_scraper_contract.py -v
python -m pytest Backend/tests/unit/test_scrapers_registered.py -v
python -m pytest Backend/tests/unit/test_no_direct_scraper_imports.py -v
```
