"""Parse populated Bonfire rows, including portals with a separate header table."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def parse_listings(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    records = []
    seen = set()
    for row in soup.select('table tr'):
        cells = row.find_all('td', recursive=False)
        link = row.select_one('a[href*="/opportunities/"], a[href*="/opportunity/"]')
        if not link or len(cells) < 4:
            continue
        reference = cells[1].get_text(' ', strip=True)
        title = cells[2].get_text(' ', strip=True)
        if not reference or not title or reference in seen:
            continue
        seen.add(reference)
        records.append({'ref_number': reference, 'title': title,
            'status': cells[0].get_text(' ', strip=True), 'close_date': cells[3].get_text(' ', strip=True),
            'issuing_organization': 'City of Dallas', 'location': 'Dallas, TX, USA',
            'url': urljoin(base_url, link['href'])})
    return records
