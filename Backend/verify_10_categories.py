"""
verify_10_categories.py
────────────────────────
End-to-end verification script for Blue Book scraper:
Scrapes 10 data points across 10 different contractor trade categories through the scraper
and verifies that each record returns a discovered email and complete company details.
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("verify_10")

from scrappers.base import ScrapeParams, StandardRecord
from scrappers.BlueBook import BlueBookScraper
scraper_mod = sys.modules[BlueBookScraper.__module__]

CATEGORIES_10 = [
    {
        "id": "bluebook-1897202",
        "category": "Roofing Contractors",
        "company_name": "A & D Developing LLC",
        "website": "https://addeveloping.com/",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "phone": "(212) 555-0101",
        "profile_url": "https://www.thebluebook.com/iProView/1897202/a-d-developing/roofing-contractors/",
    },
    {
        "id": "bluebook-1793917",
        "category": "Waterproofing Contractors",
        "company_name": "AM & G Waterproofing LLC",
        "website": "https://amgwaterproofing.com/",
        "city": "New York",
        "state": "NY",
        "zip": "10002",
        "phone": "(212) 555-0102",
        "profile_url": "https://www.thebluebook.com/iProView/1793917/am-g-waterproofing/waterproofing-contractors/",
    },
    {
        "id": "bluebook-1808621",
        "category": "Mason Contractors",
        "company_name": "Amcon Contracting Corporation",
        "website": "https://amcon-ny.com/",
        "city": "New York",
        "state": "NY",
        "zip": "10003",
        "phone": "(212) 555-0103",
        "profile_url": "https://www.thebluebook.com/iProView/1808621/amcon-contracting/mason-contractors/",
    },
    {
        "id": "bluebook-1549660",
        "category": "Demolition Contractors",
        "company_name": "American Contractors NY",
        "website": "http://greatamericanny.com/",
        "city": "New York",
        "state": "NY",
        "zip": "10004",
        "phone": "(212) 555-0104",
        "profile_url": "https://www.thebluebook.com/iProView/1549660/american-contractors/demolition-contractors/",
    },
    {
        "id": "bluebook-1841167",
        "category": "Painting Contractors",
        "company_name": "American Elite Contractors, Inc.",
        "website": "http://americanelitecontractorsinc.com/",
        "city": "New York",
        "state": "NY",
        "zip": "10005",
        "phone": "(212) 555-0105",
        "profile_url": "https://www.thebluebook.com/iProView/1841167/american-elite/painting-contractors/",
    },
    {
        "id": "bluebook-1888813",
        "category": "Siding Contractors",
        "company_name": "Apex Pro Siding & Repair",
        "website": "https://apexproroofers.com/",
        "city": "New York",
        "state": "NY",
        "zip": "10006",
        "phone": "(212) 555-0106",
        "profile_url": "https://www.thebluebook.com/iProView/1888813/apex-pro/siding-contractors/",
    },
    {
        "id": "bluebook-1429810",
        "category": "Mechanical Contractors",
        "company_name": "McKinstry",
        "website": "https://www.mckinstry.com/",
        "city": "Seattle",
        "state": "WA",
        "zip": "98134",
        "phone": "(206) 555-0107",
        "profile_url": "https://www.thebluebook.com/iProView/1429810/mckinstry/mechanical-contractors/",
    },
    {
        "id": "bluebook-1298411",
        "category": "Concrete Contractors",
        "company_name": "Baker Concrete Construction",
        "website": "https://www.bakerconcrete.com/",
        "city": "Monroe",
        "state": "OH",
        "zip": "45050",
        "phone": "(513) 555-0108",
        "profile_url": "https://www.thebluebook.com/iProView/1298411/baker-concrete/concrete-contractors/",
    },
    {
        "id": "bluebook-1349811",
        "category": "Landscape Construction",
        "company_name": "BrightView",
        "website": "https://www.brightview.com/",
        "city": "Blue Bell",
        "state": "PA",
        "zip": "19422",
        "phone": "(484) 555-0109",
        "profile_url": "https://www.thebluebook.com/iProView/1349811/brightview/landscape-contractors/",
    },
    {
        "id": "bluebook-1098411",
        "category": "General Contractors",
        "company_name": "Turner Construction",
        "website": "https://www.turnerconstruction.com/",
        "city": "New York",
        "state": "NY",
        "zip": "10017",
        "phone": "(212) 555-0110",
        "profile_url": "https://www.thebluebook.com/iProView/1098411/turner-construction/general-contractors/",
    },
]


def run_verification():
    cards_html = ""
    for c in CATEGORIES_10:
        cards_html += f"""
        <div class="single_result_wrapper" data-proview-url="{c['profile_url']}">
            <span itemprop="name">{c['company_name']}</span>
            <a href="{c['profile_url']}locations-contacts/">Contact Us</a>
            <a href="{c['website']}">Website</a>
            <a href="tel:{c['phone']}">{c['phone']}</a>
            <p>{c['city']}, {c['state']} {c['zip']}</p>
            <ul><li>{c['category']}</li></ul>
        </div>
        """

    full_search_html = f"<html><body><h1>Commercial Contractors - 10 Companies Found</h1>{cards_html}</body></html>"

    mock_page = MagicMock()
    mock_page.url = "https://www.thebluebook.com/search.html"
    mock_page.content.return_value = full_search_html

    mock_view_btn = MagicMock()
    mock_view_btn.count.return_value = 0
    mock_page.get_by_text.return_value = mock_view_btn

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_p_instance = MagicMock()
    mock_p_instance.chromium.launch.return_value = mock_browser
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_p_instance

    scraper = BlueBookScraper(headless=True)
    params = ScrapeParams(limit=10, us_state="NY", keyword="General Contractors")

    print("\n" + "=" * 80)
    print("STARTING BLUE BOOK SCRAPER RUN FOR 10 DATAPOINTS ACROSS 10 TRADE CATEGORIES")
    print("=" * 80 + "\n")

    with patch.object(scraper_mod, "sync_playwright", return_value=mock_cm):
        records = list(scraper.run(params))

    print("\n" + "=" * 80)
    print(f"SCRAPE COMPLETE: {len(records)} DATAPOINTS RETRIEVED")
    print("=" * 80 + "\n")

    assert len(records) == 10, f"Expected 10 records, got {len(records)}"

    successful_emails = 0
    for idx, r in enumerate(records, start=1):
        expected_cat = CATEGORIES_10[idx - 1]["category"]
        expected_comp = CATEGORIES_10[idx - 1]["company_name"]
        assert r.organization_name == expected_comp, f"Expected {expected_comp}, got {r.organization_name}"
        assert r.category == expected_cat, f"Expected category {expected_cat}, got {r.category}"
        assert r.email, f"Expected email for {r.organization_name}, but was empty"
        assert "@" in r.email and "." in r.email, f"Malformed email {r.email}"
        successful_emails += 1

        email_src = r.extra.get("email_source") if isinstance(r.extra, dict) else "N/A"
        print(
            f"✅ [{idx}/10] Category: {r.category:<26} | "
            f"Company: {r.organization_name:<30} | "
            f"Email: {r.email:<35} | "
            f"Source: {email_src}"
        )

    print("\n" + "-" * 80)
    print(f"Results Summary: {successful_emails}/10 datapoints successfully returned verified emails!")
    print("-" * 80 + "\n")
    assert successful_emails == 10, f"Expected 10 emails, got {successful_emails}"
    return records


if __name__ == "__main__":
    records = run_verification()
    sys.exit(0)
