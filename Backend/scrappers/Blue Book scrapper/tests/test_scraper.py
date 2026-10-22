"""
Backend/scrappers/Blue Book scrapper/tests/test_scraper.py
──────────────────────────────────────────────────────────
Unit tests for BlueBookScraper BaseScraper implementation:
- ScraperMeta contract validation
- Controller integration (validate_params, get_meta)
- Normalization and fallback to_standard mapping
- Parameter validation (location requirement)
- Scraper execution pipeline (run yielding StandardRecord)
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from scrappers.base import (
    BaseScraper,
    InvalidScrapeParams,
    ScrapeParams,
    ScraperMeta,
    StandardRecord,
)
import scrappers.controller as ctrl
from scrappers.BlueBook import BlueBookScraper, RECORD_KIND, SCRAPPER_CODE, SOURCE_CODE


class BlueBookScraperContractTests(unittest.TestCase):
    def test_scraper_subclass_and_codes(self):
        self.assertTrue(issubclass(BlueBookScraper, BaseScraper))
        self.assertEqual(BlueBookScraper.get_scrapper_code(), SCRAPPER_CODE)
        self.assertEqual(BlueBookScraper.get_source_code(), SOURCE_CODE)
        self.assertEqual(SCRAPPER_CODE, "bluebook")
        self.assertEqual(SOURCE_CODE, "bluebook")
        self.assertEqual(RECORD_KIND, "company")

    def test_metadata_contract(self):
        meta = BlueBookScraper.meta
        self.assertIsInstance(meta, ScraperMeta)
        self.assertEqual(meta.id, "bluebook")
        self.assertTrue(meta.id.islower() and meta.id.isalnum())
        self.assertEqual(meta.record_kind, "company")
        self.assertTrue(meta.requires_location)
        self.assertFalse(meta.requires_city)
        self.assertEqual(meta.coverage, {"country": "USA"})
        self.assertIn("location", meta.supports)
        self.assertIn("keyword", meta.supports)
        self.assertIn("limit", meta.supports)
        self.assertIn("company_name", meta.fields)
        self.assertIn("phone", meta.fields)
        self.assertIn("website", meta.fields)
        self.assertIn("address", meta.fields)
        self.assertIn("city", meta.fields)
        self.assertIn("state", meta.fields)
        self.assertIn("Zip_Code", meta.fields)
        self.assertIn("contact_name", meta.fields)
        self.assertIn("contact_title", meta.fields)

    def test_controller_integration(self):
        if BlueBookScraper not in ctrl.REGISTERED_SCRAPERS:
            ctrl.REGISTERED_SCRAPERS.append(BlueBookScraper)

        # 1. State parameter validation
        p1 = ctrl.validate_params("bluebook", {"us_state": "CA", "keyword": "Roofing", "limit": 15})
        self.assertEqual(p1.us_state, "CA")
        self.assertEqual(p1.keyword, "Roofing")
        self.assertEqual(p1.limit, 15)

        # 2. Location string resolution
        p2 = ctrl.validate_params("bluebook", {"location": "Austin, TX", "limit": 10})
        self.assertEqual(p2.city, "Austin")
        self.assertEqual(p2.us_state, "TX")

        # 3. Default limit
        p3 = ctrl.validate_params("bluebook", {"us_state": "NY"})
        self.assertEqual(p3.limit, BlueBookScraper.meta.default_limit)

        # 4. Location required validation
        with self.assertRaises(InvalidScrapeParams):
            ctrl.validate_params("bluebook", {"keyword": "Plumbing"})

    def test_to_standard_direct_and_fallback(self):
        scraper = BlueBookScraper(headless=True)
        raw = {
            "id": "bluebook-553737",
            "record_kind": "company",
            "source_code": "bluebook",
            "scrapper_code": "bluebook",
            "external_id": "553737",
            "profile_url": "https://www.thebluebook.com/iProView/553737/acme/general-contractors/",
            "company_name": "Acme Builders, Inc.",
            "phone": "(310) 555-0142",
            "email": "info@acme.example.com",
            "website": "https://acme.example.com/",
            "address": "100 Main St.",
            "city": "Torrance",
            "state": "CA",
            "Zip_Code": "90502",
            "category": "General Contractors",
            "contact_name": "Jane Doe",
            "contact_title": "President",
            "extra": {"trades": ["General Contractors"], "certifications": ["MBE"]},
        }

        # Normalizer / direct mapping
        record = scraper.to_standard(raw)
        self.assertIsInstance(record, StandardRecord)
        self.assertEqual(record.source_code, "bluebook")
        self.assertEqual(record.record_kind, "company")
        self.assertEqual(record.external_id, "553737")
        self.assertEqual(record.organization_name, "Acme Builders, Inc.")
        self.assertEqual(record.city, "Torrance")
        self.assertEqual(record.us_state, "CA")
        self.assertEqual(record.postal_code, "90502")
        self.assertEqual(record.phone, "(310) 555-0142")
        self.assertEqual(record.contact_name, "Jane Doe")
        self.assertEqual(record.contact_title, "President")

    def test_scrape_raises_on_missing_location(self):
        scraper = BlueBookScraper(headless=True)
        with self.assertRaises(InvalidScrapeParams):
            # No state, city, or location
            list(scraper.scrape(ScrapeParams(limit=5, keyword="Roofing")))

    def test_run_with_mocked_scrape(self):
        scraper = BlueBookScraper(headless=True)

        sample_raw = {
            "id": "bluebook-999",
            "record_kind": "company",
            "source_code": "bluebook",
            "scrapper_code": "bluebook",
            "external_id": "999",
            "profile_url": "https://www.thebluebook.com/iProView/999/alpha/plumbing/",
            "company_name": "Alpha Plumbing LLC",
            "phone": "(214) 555-0199",
            "city": "Dallas",
            "state": "TX",
            "Zip_Code": "75201",
            "category": "Plumbing Contractors",
            "contact_name": "Sam Taylor",
            "contact_title": "Lead Estimator",
            "extra": {"trades": ["Plumbing Contractors"]},
        }

        with patch.object(scraper, "scrape", return_value=iter([sample_raw])):
            params = ScrapeParams(limit=1, us_state="TX", keyword="Plumbing")
            results = list(scraper.run(params))
            self.assertEqual(len(results), 1)
            rec = results[0]
            self.assertIsInstance(rec, StandardRecord)
            self.assertEqual(rec.organization_name, "Alpha Plumbing LLC")
            self.assertEqual(rec.city, "Dallas")
            self.assertEqual(rec.us_state, "TX")
            self.assertEqual(rec.phone, "(214) 555-0199")


if __name__ == "__main__":
    unittest.main()
