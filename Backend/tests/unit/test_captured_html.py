"""Regressions for the actual layouts observed during the live source checks."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scrappers.bonfire_parser import parse_listings
from scrappers.jwiz import Lead, enrich_profile, extract_city_state
from scrappers.dasny import DasnyScraper, parse_detail_header
from scrappers.nyscr import parse_detail_content


FIXTURES = Path(__file__).parents[1] / 'fixtures'


def test_bonfire_uses_populated_table_after_the_cloned_header():
    html = (FIXTURES / 'bonfire/captured_search.html').read_text(encoding='utf-8')
    rows = parse_listings(html, 'https://dallascityhall.bonfirehub.com')
    assert len(rows) >= 2
    assert len({row['ref_number'] for row in rows}) == len(rows)
    assert all(row['title'] and row['url'].startswith('https://dallascityhall.bonfirehub.com/') for row in rows)
    assert all(row['issuing_organization'] == 'City of Dallas' for row in rows)


@pytest.mark.parametrize(('address', 'city', 'state'), [
    ('Yonkers, NY', 'Yonkers', 'New York'),
    ('New York, NY 10001', 'New York', 'New York'),
    ('123 Main Street, Yonkers, NY 10701', 'Yonkers', 'New York'),
    ('Brooklyn, NY', 'Brooklyn', 'New York'),
    ('NJ', '', 'New Jersey'),
])
def test_jwiz_observed_city_is_not_replaced_by_the_search_location(address, city, state):
    assert extract_city_state(address) == (city, state)


def test_jwiz_category_comes_from_profile_categories_not_the_requested_keyword(monkeypatch):
    monkeypatch.setattr('scrappers.jwiz.time.sleep', lambda *_: None)
    html = (FIXTURES / 'jwiz/captured_profile.html').read_text(encoding='utf-8')
    client = SimpleNamespace(get=lambda _: SimpleNamespace(text=html))
    lead = Lead(company_name='Original search card name', profile_url='https://jwiz.com/example', source_keyword='roofing')
    assert enrich_profile(client, lead)
    assert lead.company_name == 'Original search card name'
    assert lead.source_category == 'Roofing; Painters; Home Improvement'
    assert 'Windows' in lead.description
    unrelated = Lead(company_name='Original search card name', profile_url='https://jwiz.com/example', source_keyword='excavation')
    assert enrich_profile(client, unrelated)
    assert unrelated.source_category == lead.source_category  # Recover actual data without relabeling it.
    assert unrelated.email == lead.email and unrelated.phone == lead.phone


def test_dasny_detail_title_and_location_are_read_from_the_opportunity():
    html = (FIXTURES / 'dasny/captured_detail.html').read_text(encoding='utf-8')
    record = parse_detail_header(html)
    assert record['title'].startswith('SUNY DCC at Fishkill')
    assert record['headers']['Solicitation #'] == '4002449999-P20'
    assert record['headers']['Type'] == 'Bid'
    assert record['description'] is None  # Site-wide politician banner is excluded.
    address = record['headers']['Location Where Goods to be Delivered or Service Performed']
    assert DasnyScraper()._parse_location(address)[1:] == ('Fishkill', 'NY', '12524')


def test_nyscr_details_are_read_from_content_not_the_translation_banner():
    html = (FIXTURES / 'nyscr/captured_detail.html').read_text(encoding='utf-8')
    record = parse_detail_content(html)
    assert record['title'].startswith('Request for Qualifications')
    assert record['fields']['cr#'] == '2139393'
    assert record['fields']['agency'] == 'State University of New York (SUNY)'
    assert record['fields']['due date'] == '10/29/2026 11:00 AM'
    assert 'Engineering' in record['fields']['category']
    assert 'heat recovery' in record['description'].lower()
    assert record['contacts'][0]['name'] == 'Michael Dillon'
    assert record['contacts'][0]['email'] == 'michael.dillon@stonybrookmedicine.edu'
    assert record['contacts'][0]['phone'] == '631-216-8503'


def test_jwiz_generic_company_words_do_not_reject_the_observed_trade(monkeypatch):
    monkeypatch.setattr('scrappers.jwiz.time.sleep', lambda *_: None)
    html = (FIXTURES / 'jwiz/captured_profile.html').read_text(encoding='utf-8')
    client = SimpleNamespace(get=lambda _: SimpleNamespace(text=html))
    lead = Lead(company_name='Original name', profile_url='https://jwiz.com/example', source_keyword='roofing companies')
    assert enrich_profile(client, lead)
    assert 'Roofing' in lead.source_category


def test_jwiz_abbreviated_new_york_city_and_state_only_search():
    from Database.search import normalize_city
    from scrappers.utils import location_match
    from scrappers.jwiz import build_location_slug
    from scrappers.base import ScrapeParams
    assert normalize_city('NY') == 'New York'
    assert location_match('NY', 'NY', ScrapeParams(city='New York', us_state='NY'))
    assert not location_match('Yonkers', 'NY', ScrapeParams(city='New York', us_state='NY'))
    assert build_location_slug(ScrapeParams(us_state='NY')) == 'ny'
