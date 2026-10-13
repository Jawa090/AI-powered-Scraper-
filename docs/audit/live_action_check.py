"""Real AI and UI Action click; controlled source records in the isolated audit DB."""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Backend'), str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name = json.loads((ROOT/'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL = make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.CHECKPOINT_DB_URL = make_url(settings.CHECKPOINT_DB_URL).set(database=name).render_as_string(hide_password=False)
settings.SELENIUM_MODE = 'local'
from Database.controller import session_scope
from Database.models.user import User
from Database.models.job import Job
from sqlalchemy import select
from services.auth import hash_password
from services.sessions import new_session
from services.ingest import upsert_leads
from agents.graph.checkpointer import setup_checkpointer
from agents.graph.runner import run_turn
from scrappers.driver import make_driver
from scrappers.base import StandardRecord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import worker

setup_checkpointer()
tag = 'audit' + uuid.uuid4().hex
category = 'general contractor ' + tag
def record(index):
    return dict(source_code='jwiz', record_kind='company', external_id=tag+str(index),
                organization_name='Action verification contractor '+str(index)+' '+tag,
                category=category, city='New York', us_state='NY',
                source_url='https://example.test/'+tag+'/'+str(index))
with session_scope() as db:
    user = User(id=tag, username=tag, email=tag+'@example.test', name='Action verification',
                role='user', status='Active', department_id='dept-default', auth_source='db',
                password_hash=hash_password('AuditActionPassword123'))
    db.add(user)
    db.flush()
    upsert_leads(db, [record(0)])
sid = new_session(user)
report = dict(realProvider=True, realBrowser=True, isolatedDatabase=True, controlledSourceRecords=True)
driver = None
original_run = worker.controller.run
try:
    first = run_turn(user, sid, f'Get 1 contractor company with trade/category exactly "{category}". City New York, state NY. Neither email nor phone required. Use JWiz.', uuid.uuid4().hex)
    assert len(first.get('records', [])) == 1 and tag in first['records'][0]['company']
    more = run_turn(user, sid, 'now get me 2 more', uuid.uuid4().hex)
    assert more.get('pendingAction') and more['records'] == [] and not more.get('jobId')
    proposal = more['pendingAction']['proposal']
    assert proposal['args']['quantity'] == 2 and proposal['args']['new_only']
    report.update(initialRecords=1, requestedAdditional=2, pendingAction=True, proposal=proposal)
    print('Real AI created the pending scrape action for 2 unseen records.', flush=True)
    driver = make_driver(headless=True)
    driver.set_window_size(1440, 1000)
    wait = WebDriverWait(driver, 90)
    driver.get('http://127.0.0.1:3010/login')
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[type="text"]'))).send_keys(tag)
    driver.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys('AuditActionPassword123')
    driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
    action = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="Action"]]')))
    action.screenshot(str(ROOT/'docs/audit/scrape_action_button.png'))
    report['actionButtonVisible'] = True
    action.click()
    def queued(_):
        with session_scope() as db:
            row = db.scalar(select(Job).where(Job.created_by == user.id))
            return row.id if row else False
    job_id = wait.until(queued)
    report.update(buttonClickQueuedJob=True, jobId=job_id)
    print('Browser Action click queued the scraper.', flush=True)
    worker.controller.run = lambda *args, **kwargs: iter(StandardRecord(**record(i)) for i in range(3))
    worker.execute_job(job_id, 'browser-action-verification')
    wait.until(lambda d: 'Action verification contractor 1 '+tag in d.find_element(By.TAG_NAME, 'body').text
               and 'Action verification contractor 2 '+tag in d.find_element(By.TAG_NAME, 'body').text)
    with session_scope() as db:
        job = db.get(Job, job_id)
        assert job.status == 'Completed'
    report.update(workerCompleted=True, twoNewRowsShownInChat=True, passed=True)
    driver.save_screenshot(str(ROOT/'docs/audit/scrape_action_completed.png'))
except Exception as exc:
    report.update(passed=False, errorType=type(exc).__name__, error=str(exc)[:350])
    if driver:
        driver.save_screenshot(str(ROOT/'docs/audit/scrape_action_failure.png'))
finally:
    worker.controller.run = original_run
    if driver:
        driver.quit()
(ROOT/'docs/audit/live_action_verification.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
print(json.dumps(report, default=str), flush=True)
if not report.get('passed'):
    raise SystemExit(1)
