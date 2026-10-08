"""Browser smoke tests against the real local API and disposable database."""
import sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Backend'),str(ROOT)]
from settings import settings
settings.SELENIUM_MODE='local'
from scrappers.driver import make_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
URL='http://127.0.0.1:3010'
driver=make_driver(headless=True)
wait=WebDriverWait(driver,25)
report={'browser':'Chrome','api':'real PostgreSQL preview','checks':{}}
def text(): return driver.find_element(By.TAG_NAME,'body').text
def go(path): driver.get(URL+path)
def login(username,password):
    go('/login')
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,'input[type="text"]'))).send_keys(username)
    driver.find_element(By.CSS_SELECTOR,'input[type="password"]').send_keys(password)
    driver.find_element(By.CSS_SELECTOR,'button[type="submit"]').click()
    wait.until(lambda d: 'AI Agent' in text() and not d.find_elements(By.CSS_SELECTOR,'input[type="password"]'))
try:
    login('Admin','Admin')
    go('/admin/activity')
    wait.until(lambda d: 'preview-user@example.test' in text() and 'Data delivered to users' in text())
    heads=[element.text for element in driver.find_elements(By.CSS_SELECTOR,'section[aria-label="Delivered data by user"] h3')]
    assert 'admin' in heads and 'preview-user@example.test' in heads
    sections=driver.find_elements(By.CSS_SELECTOR,'section[aria-label="Delivered data by user"] article')
    assert any('preview-user@example.test' in section.text and 'Yonkers' in section.text and 'Roofing' in section.text for section in sections)
    assert any(section.find_element(By.TAG_NAME,'h3').text=='admin' and 'Yonkers' in section.text for section in sections)
    report['checks']['emailAndAdminHeadingsWithActualRows']=True
    driver.save_screenshot(str(ROOT/'docs/audit/admin_deliveries.png'))
    driver.refresh();wait.until(lambda d: 'preview-user@example.test' in text())
    report['checks']['adminReload']=True
    go('/admin/users');wait.until(lambda d: 'PreviewUser' in text())
    assert 'preview-user@example.test' in text() and 'Edit email' in text()
    report['checks']['emailManagement']=True
    # Account switching must restore the owner's server history rather than the admin's cache.
    driver.execute_script('sessionStorage.clear(); localStorage.clear();')
    login('PreviewUser','PreviewPassword123')
    wait.until(lambda d: 'two live roofing companies from Yonkers NY' in text())
    before=text();driver.refresh();wait.until(lambda d: 'two live roofing companies from Yonkers NY' in text())
    report['checks']['ownHistorySurvivesReload']=True
    go('/admin/activity');wait.until(lambda d: 'AI Agent' in text())
    assert 'Data delivered to users' not in text()
    report['checks']['normalUserCannotViewAdmin']=True
    go('/datasets/nonexistent-browser-check')
    wait.until(lambda d: 'not found' in text().lower() or 'unavailable' in text().lower())
    report['checks']['missingDatasetShowsNoUnrelatedData']=True
    report['passed']=True
except Exception as exc:
    report.update(passed=False,errorType=type(exc).__name__,error=str(exc)[:350])
    driver.save_screenshot(str(ROOT/'docs/audit/browser_failure.png'))
finally:
    driver.quit()
(ROOT/'docs/audit/browser_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
