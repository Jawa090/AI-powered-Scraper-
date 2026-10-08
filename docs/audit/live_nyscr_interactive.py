"""Opt-in live NYSCR check with a real human completing portal verification."""
import sys, time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Backend'), str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
from scrappers.base import NullScrapeContext, SourceBlocked
from scrappers.controller import run
from Database.controller import session_scope, Repositories
from services.ingest import upsert_leads
from routes.serializers import serialize_lead
name = json.loads((ROOT / 'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL = make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.SELENIUM_MODE, settings.NYSCR_HEADLESS, settings.SCRAPER_MODE = 'local', False, 'live'
resume = ROOT / 'docs/audit/nyscr_resume.flag'
if resume.exists(): resume.unlink()
class HumanVerification(NullScrapeContext):
    def wait_for_user(self, reason):
        print('Manual verification required in the NYSCR Chrome window. Open Login again if the error page has no challenge; sign in manually, then tell Codex verified.', flush=True)
        start = time.monotonic()
        while time.monotonic() - start < 600:
            if resume.exists(): return True
            time.sleep(1)
        raise SourceBlocked('Human verification was not completed during this check.')
report = {'source': 'nyscr', 'mode': 'live', 'interactive': True}
try:
    records = list(run('nyscr', {'limit': 2, 'timeout_s': 45}, ctx=HumanVerification()))
    with session_scope() as db:
        result = upsert_leads(db, records)
        ids = result.lead_ids
        report.update(found=len(records), inserted=result.inserted, updated=result.updated, unchanged=result.unchanged, failed=result.failed)
    with session_scope() as db:
        report['savedRecords'] = [serialize_lead(Repositories(db).leads.get_by_id(lid)) for lid in ids]
    report['persistedAfterCommit'] = len(report['savedRecords']) == len(records)
except Exception as exc:
    report.update(errorType=type(exc).__name__, error=str(exc)[:400])
(ROOT / 'docs/audit/live_nyscr_interactive.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k != 'savedRecords'}), flush=True)
