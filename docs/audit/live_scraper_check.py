"""Small live-source check, saving only to the disposable implementation database."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Backend'), str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name = json.loads((ROOT / 'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL = make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.SCRAPER_MODE = 'live'
settings.SELENIUM_MODE = 'local'
settings.NYSCR_HEADLESS = True
from scrappers.controller import run, check_ready
from Database.controller import session_scope, Repositories
from services.ingest import upsert_leads
from routes.serializers import serialize_lead
source = sys.argv[1]
params = {'limit': 2, 'timeout_s': 45}
if source == 'jwiz':
    params.update(keyword=(sys.argv[4] if len(sys.argv) > 4 else 'roofing'), city=(sys.argv[2] if len(sys.argv) > 2 else 'New York'), us_state='NY')
    if len(sys.argv) > 3:
        params['limit'] = int(sys.argv[3])
report = {'source': source, 'mode': 'live', 'ready': check_ready(source)[0], 'params': params}
try:
    records = list(run(source, params))
    with session_scope() as db:
        result = upsert_leads(db, records, department_id='dept-default')
        report.update(found=len(records), inserted=result.inserted, updated=result.updated,
            unchanged=result.unchanged, failed=result.failed, skipped=result.skipped)
        ids = list(result.lead_ids)
    with session_scope() as db:
        report['savedRecords'] = [serialize_lead(Repositories(db).leads.get_by_id(lid)) for lid in ids]
    report['persistedAfterCommit'] = len(report['savedRecords']) == len(records)
except Exception as exc:
    report.update(errorType=type(exc).__name__, error=str(exc)[:500])
suffix = '_nyc' if source == 'jwiz' and params['city'] == 'New York' and params['limit'] == 10 else '_positive' if len(sys.argv) > 2 else ''
path = ROOT / f'docs/audit/live_{source}{suffix}.json'
path.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'savedRecords'}, default=str), flush=True)
