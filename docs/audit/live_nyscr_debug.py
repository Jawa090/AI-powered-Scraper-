"""Attach to the user-visible debugging Chrome; let the human sign in."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Backend'), str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scrappers.nyscr import NyscrScraper
from scrappers.base import ScrapeParams
from Database.controller import session_scope, Repositories
from services.ingest import upsert_leads
from routes.serializers import serialize_lead
name = json.loads((ROOT/'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL = make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.SELENIUM_MODE, settings.NYSCR_HEADLESS = 'local', False
settings.NYSCR_DEBUGGER_ADDRESS = '127.0.0.1:9222'
scraper = NyscrScraper(headless=False)
report = {'source': 'nyscr', 'mode': 'live', 'debugBrowser': True}
try:
    assert scraper.setup_chrome(), 'Could not attach to the debugging browser'
    logged_in = lambda: bool(scraper.driver.find_elements(By.XPATH, "//a[contains(text(), 'Log off') or contains(text(), 'Logout')]"))
    if not logged_in():
        if not scraper.driver.find_elements(By.ID, 'Username'):
            scraper.driver.get('https://www.nyscr.ny.gov/Account/Login')
        for field_id, value in [('Username', settings.NYSCR_USERNAME), ('Password', settings.NYSCR_PASSWORD)]:
            field = WebDriverWait(scraper.driver, 20).until(EC.visibility_of_element_located((By.ID, field_id)))
            field.clear(); field.send_keys(value)
        print('Visible Chrome connected. Login fields are prefilled; please click Sign In and complete verification.', flush=True)
    deadline = time.monotonic()+900
    while time.monotonic()<deadline:
        if logged_in():
            break
        time.sleep(2)
    else: raise RuntimeError('Manual sign-in was not completed during this check.')
    print('Signed-in session detected. Collecting two records.', flush=True)
    records = list(scraper.run(ScrapeParams(limit=2, timeout_s=45)))
    with session_scope() as db:
        result = upsert_leads(db, records)
        report.update(found=len(records), inserted=result.inserted, updated=result.updated, unchanged=result.unchanged, failed=result.failed)
        ids = result.lead_ids
    with session_scope() as db:
        report['savedRecords'] = [serialize_lead(Repositories(db).leads.get_by_id(lid)) for lid in ids]
    report['persistedAfterCommit'] = len(report['savedRecords']) == len(records)
except Exception as exc:
    report.update(errorType=type(exc).__name__, error=str(exc)[:300])
finally:
    scraper.close()
(ROOT/'docs/audit/live_nyscr_debug.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='savedRecords'}),flush=True)
