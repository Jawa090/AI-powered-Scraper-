"""Capture public source HTML to verify current parser selectors."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Backend'), str(ROOT)]
source = sys.argv[1]
from bs4 import BeautifulSoup
if source == 'jwiz':
    from scrappers.jwiz import HTTPClient, build_search_url, find_result_cards
    with_client = HTTPClient()
    response = with_client.get(build_search_url('new-york-ny', 'roofing', 0))
    html = response.text
    soup = BeautifulSoup(html, 'html.parser')
    cards = find_result_cards(soup)
    print(str(cards[0])[:10000] if cards else soup.get_text(' ', strip=True)[:3000])
    url = 'https://jwiz.com/jewish/nikolins-contracting-co-38405.html'
    profile = with_client.get(url).text
    (ROOT / 'docs/audit/jwiz_profile.html').write_text(profile, encoding='utf-8')
    print('PROFILE:', BeautifulSoup(profile, 'html.parser').get_text(' ', strip=True)[-9000:])
    with_client.close()
else:
    from settings import settings
    settings.SELENIUM_MODE = 'local'
    from scrappers.driver import make_driver
    import time
    driver = make_driver(headless=True)
    try:
        driver.get('https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities')
        time.sleep(15)
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        print('BODY:', soup.get_text(' ', strip=True)[:7000])
        print('TABLES:', [t.get_text(' ', strip=True)[:2500] for t in soup.select('table')])
        print('LINKS:', [(a.get_text(' ', strip=True), a.get('href')) for a in soup.select('a[href]')][:40])
    finally:
        driver.quit()
(ROOT / f'docs/audit/{source}_search.html').write_text(html, encoding='utf-8')
