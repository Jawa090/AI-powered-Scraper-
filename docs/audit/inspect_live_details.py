"""Capture only public opportunity content needed for parser regressions."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Backend'), str(ROOT)]
from settings import settings
settings.SELENIUM_MODE = 'local'
from scrappers.driver import make_driver
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = make_driver(headless=False, debugger_address='127.0.0.1:9222')
try:
    data = json.loads((ROOT / 'docs/audit/live_nyscr_debug.json').read_text())
    driver.get(data['savedRecords'][0]['sourceUrl'])
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'h1')))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    for element in soup.select('script, input, nav, header, footer'):
        element.decompose()
    (ROOT / 'docs/audit/nyscr_detail.html').write_text(str(soup), encoding='utf-8')
    print(json.dumps({'containers': [(element.get('class'), element.get_text(' ', strip=True)[:180])
        for element in soup.select('.container')], 'body': soup.get_text('\n', strip=True)[:7500]}, default=str), flush=True)
finally:
    driver.service.stop()
