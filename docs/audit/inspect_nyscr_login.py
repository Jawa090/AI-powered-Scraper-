"""Inspect login state without logging credentials, input values or cookies."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from urllib.parse import urlparse
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Backend'), str(ROOT)]
from settings import settings, _read_env_file
raw = _read_env_file(ROOT / '.env')
print('Credential alias matches:', settings.NYSCR_USERNAME == raw.get('ny_USERNAME'), settings.NYSCR_PASSWORD == raw.get('ny_PASSWORD'))
settings.SELENIUM_MODE = 'local'
from scrappers.nyscr import NyscrScraper
from selenium.webdriver.common.by import By
scraper = NyscrScraper(headless=True)
try:
    assert scraper.setup_chrome()
    try:
        scraper.login()
        print('Login succeeded')
    except Exception as exc:
        print('Login state:', type(exc).__name__)
    print('Path:', urlparse(scraper.driver.current_url).path)
    print('Visible input fields:', [(el.get_attribute('id'), el.get_attribute('type')) for el in scraper.driver.find_elements(By.TAG_NAME, 'input') if el.is_displayed()])
    body = scraper.driver.find_element(By.TAG_NAME, 'body').text
    for secret in [settings.NYSCR_PASSWORD, settings.NYSCR_USERNAME]:
        if secret:
            body = body.replace(secret, '[redacted]')
    print('Visible page text:', body[:3500])
finally:
    scraper.close()
