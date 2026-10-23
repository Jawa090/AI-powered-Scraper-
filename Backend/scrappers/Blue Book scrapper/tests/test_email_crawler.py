"""
Backend/scrappers/Blue Book scrapper/tests/test_email_crawler.py
────────────────────────────────────────────────────────────────
Unit and integration tests for Blue Book email & social media crawling:
- Email cleaning and strict validation (subdomains, prefixes, extensions)
- Cloudflare XOR email deobfuscation (attribute & href fragment, odd length check)
- HTML email extraction (mailto multi-recipients, meta tags, entities, unicode \\u0040, [at] obfuscation)
- Social profile discovery and filtering (netloc domain matching, query string preservation)
- Internal contact page link extraction (domain normalization without www, contact prioritization)
- Contractor website crawling (homepage + subpages)
- Social media profile crawling (Instagram bio, Facebook page / mobile fallback)
- Full crawler orchestrator workflow
- BlueBookScraper enrichment integration and profile fallback
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import sys
from scrappers.base import ScrapeParams, StandardRecord
from scrappers.BlueBook import BlueBookScraper, crawler
scraper_mod = sys.modules[BlueBookScraper.__module__]


class EmailValidationTests(unittest.TestCase):
    def test_clean_valid_emails(self):
        self.assertEqual(crawler.clean_email("info@riversideelectric.com"), "info@riversideelectric.com")
        self.assertEqual(crawler.clean_email("  Contact@Company.ORG  "), "contact@company.org")
        self.assertEqual(crawler.clean_email("<bids@roofing-contractors.net>"), "bids@roofing-contractors.net")
        self.assertEqual(crawler.clean_email("sales+leads@builder.io"), "sales+leads@builder.io")
        self.assertEqual(crawler.clean_email("john.doe_123@sub.domain.co.uk"), "john.doe_123@sub.domain.co.uk")

    def test_clean_invalid_and_denied_emails(self):
        # Malformed
        self.assertIsNone(crawler.clean_email("not-an-email"))
        self.assertIsNone(crawler.clean_email("user@"))
        self.assertIsNone(crawler.clean_email("@domain.com"))
        self.assertIsNone(crawler.clean_email("user@domain"))
        self.assertIsNone(crawler.clean_email(""))
        self.assertIsNone(crawler.clean_email(None))

        # Asset / media extensions
        self.assertIsNone(crawler.clean_email("logo@company.png"))
        self.assertIsNone(crawler.clean_email("icon@site.svg"))
        self.assertIsNone(crawler.clean_email("script@cdn.js"))

        # Denied domains (exact and subdomains)
        self.assertIsNone(crawler.clean_email("fake@example.com"))
        self.assertIsNone(crawler.clean_email("staging@sub.example.com"))
        self.assertIsNone(crawler.clean_email("test@domain.com"))
        self.assertIsNone(crawler.clean_email("bot@thebluebook.com"))
        self.assertIsNone(crawler.clean_email("internal@mail.thebluebook.com"))
        self.assertIsNone(crawler.clean_email("service@sentry.io"))
        self.assertIsNone(crawler.clean_email("errors@app.sentry.io"))
        self.assertIsNone(crawler.clean_email("admin@wixpress.com"))

        # Denied prefixes
        self.assertIsNone(crawler.clean_email("noreply@contractor.com"))
        self.assertIsNone(crawler.clean_email("noreply-service@contractor.com"))
        self.assertIsNone(crawler.clean_email("no_reply_alerts@company.com"))
        self.assertIsNone(crawler.clean_email("no-reply@company.com"))
        self.assertIsNone(crawler.clean_email("sentry@myorg.com"))
        self.assertIsNone(crawler.clean_email("donotreply@builder.com"))


class CloudflareDeobfuscationTests(unittest.TestCase):
    def test_decode_cloudflare_email(self):
        # "info@riverside.com" encoded with key 0x1a
        raw = "info@riverside.com"
        key = 0x1A
        hex_str = f"{key:02x}" + "".join(f"{(ord(c) ^ key):02x}" for c in raw)
        decoded = crawler.decode_cloudflare_email(hex_str)
        self.assertEqual(decoded, "info@riverside.com")

    def test_corrupted_cloudflare_hex(self):
        self.assertIsNone(crawler.decode_cloudflare_email(""))
        self.assertIsNone(crawler.decode_cloudflare_email("12"))
        self.assertIsNone(crawler.decode_cloudflare_email("123"))  # Odd length
        self.assertIsNone(crawler.decode_cloudflare_email("zzzzzzzz"))


class HtmlExtractionTests(unittest.TestCase):
    def test_mailto_extraction_single_and_multiple(self):
        html_doc = """
        <html>
            <body>
                <a href="mailto:info@floridabuilders.com?subject=Bid%20Request">Contact Us</a>
                <a href="mailto:estimating%40floridabuilders.com">Estimating</a>
                <a href="mailto:sales@multirecipient.com, bids@multirecipient.com">Bids & Sales</a>
            </body>
        </html>
        """
        emails = crawler.extract_emails_from_html(html_doc)
        self.assertIn("info@floridabuilders.com", emails)
        self.assertIn("estimating@floridabuilders.com", emails)
        self.assertIn("sales@multirecipient.com", emails)
        self.assertIn("bids@multirecipient.com", emails)

    def test_meta_and_visible_text(self):
        html_doc = """
        <html>
            <head>
                <meta property="og:description" content="Premier electrical contractor. Email us at service@floridaelectric.com">
            </head>
            <body>
                <p>Reach out anytime: office@floridaelectric.com or call 305-555-0100</p>
            </body>
        </html>
        """
        emails = crawler.extract_emails_from_html(html_doc)
        self.assertIn("service@floridaelectric.com", emails)
        self.assertIn("office@floridaelectric.com", emails)

    def test_html_entities_and_unicode_decoding(self):
        html_doc = """
        <script>var config = {"email": "contact\\u0040modernroofing.com"};</script>
        <p>Bids: bids&#64;modernroofing.com</p>
        <p>Support: help [at] modernroofing [dot] com</p>
        <p>Estimates: quote(at)modernroofing.com</p>
        """
        emails = crawler.extract_emails_from_html(html_doc)
        self.assertIn("contact@modernroofing.com", emails)
        self.assertIn("bids@modernroofing.com", emails)
        self.assertIn("help@modernroofing.com", emails)
        self.assertIn("quote@modernroofing.com", emails)

    def test_cloudflare_html_integration(self):
        raw = "admin@southfloridapaving.com"
        key = 0x2B
        hex_str = f"{key:02x}" + "".join(f"{(ord(c) ^ key):02x}" for c in raw)
        html_doc = f"""
        <div>
            <a class="__cf_email__" data-cfemail="{hex_str}">[email&#160;protected]</a>
            <a href="/cdn-cgi/l/email-protection#{hex_str}">Protected Link</a>
        </div>
        """
        emails = crawler.extract_emails_from_html(html_doc)
        self.assertIn("admin@southfloridapaving.com", emails)


class SocialLinkDiscoveryTests(unittest.TestCase):
    def test_extract_social_links(self):
        html_doc = """
        <div>
            <a href="https://www.facebook.com/RiversideElectricFL/">Facebook</a>
            <a href="https://instagram.com/riverside_electric?hl=en">Instagram</a>
            <a href="https://www.linkedin.com/company/riverside-electric">LinkedIn</a>
            <a href="https://twitter.com/riverside_elec">Twitter</a>
            <a href="https://youtube.com/@riverside_elec">YouTube</a>
            <a href="https://facebook.com/sharer/sharer.php?u=foo">Share on Facebook</a>
            <a href="https://twitter.com/intent/tweet">Tweet</a>
            <a href="https://www.instagram.com/p/C123456/">Post</a>
            <a href="https://www.apex.com/contact">Not Twitter</a>
        </div>
        """
        socials = crawler.extract_social_links_from_html(html_doc, "https://riversideelectric.com")
        self.assertEqual(len(socials["facebook"]), 1)
        self.assertIn("riversideelectricfl", socials["facebook"][0].lower())
        self.assertEqual(len(socials["instagram"]), 1)
        self.assertIn("riverside_electric", socials["instagram"][0].lower())
        self.assertEqual(len(socials["linkedin"]), 1)
        self.assertEqual(len(socials["twitter"]), 1)
        self.assertEqual(len(socials["youtube"]), 1)
        self.assertIn("riverside_elec", socials["youtube"][0].lower())

    def test_clean_website_url(self):
        self.assertEqual(crawler.clean_website_url("riversideelectric.com"), "https://riversideelectric.com")
        self.assertEqual(crawler.clean_website_url("www.riversideelectric.com/"), "https://www.riversideelectric.com")
        self.assertEqual(crawler.clean_website_url("http://insecure-site.org/home/"), "http://insecure-site.org/home")
        self.assertIsNone(crawler.clean_website_url(""))
        self.assertIsNone(crawler.clean_website_url(None))

    def test_social_platform_detection_no_false_positives(self):
        # Domains ending with x.com (e.g. apex.com, phoenix.com) must NOT be detected as Twitter
        self.assertIsNone(crawler.detect_social_platform("https://www.apex.com/about"))
        self.assertIsNone(crawler.detect_social_platform("https://matrix.com"))
        self.assertIsNone(crawler.detect_social_platform("https://phoenix.com/contact"))

        # Actual platforms
        self.assertEqual(crawler.detect_social_platform("https://x.com/contractor"), "twitter")
        self.assertEqual(crawler.detect_social_platform("https://twitter.com/builder"), "twitter")
        self.assertEqual(crawler.detect_social_platform("https://www.instagram.com/miami_electric"), "instagram")
        self.assertEqual(crawler.detect_social_platform("https://facebook.com/pages/florida-hvac/12345"), "facebook")
        self.assertEqual(crawler.detect_social_platform("https://m.facebook.com/pg/florida-hvac"), "facebook")


class InternalContactLinkTests(unittest.TestCase):
    def test_find_contact_links_with_www_variation(self):
        html_doc = """
        <nav>
            <a href="https://acmeelectric.com/about-us">About Our Company</a>
            <a href="https://acmeelectric.com/services">Services</a>
            <a href="https://acmeelectric.com/contact-us">Contact Us</a>
            <a href="https://google.com">External</a>
            <a href="#top">Top</a>
        </nav>
        """
        links = crawler.find_internal_contact_links(html_doc, "https://www.acmeelectric.com")
        self.assertTrue(any("contact" in u for u in links))
        self.assertTrue(any("about" in u for u in links))
        self.assertFalse(any("google.com" in u for u in links))
        self.assertTrue("contact" in links[0])


class WebsiteCrawlingTests(unittest.TestCase):
    @patch("requests.Session.get")
    def test_crawl_website_email_on_homepage(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html>
            <body>
                <h1>Acme Builders</h1>
                <a href="mailto:info@acmebuilders.com">Email Us</a>
                <a href="https://instagram.com/acmebuilders">IG</a>
            </body>
        </html>
        """
        mock_resp.url = "https://acmebuilders.com"
        mock_get.return_value = mock_resp

        email, socials = crawler.crawl_website_for_email_and_social("https://acmebuilders.com")
        self.assertEqual(email, "info@acmebuilders.com")
        self.assertTrue(any("acmebuilders" in s for s in socials["instagram"]))

    @patch("requests.Session.get")
    def test_crawl_website_email_on_contact_subpage(self, mock_get):
        home_resp = MagicMock()
        home_resp.status_code = 200
        home_resp.text = """
        <html>
            <body>
                <h1>Welcome</h1>
                <a href="/contact-us">Get in touch</a>
            </body>
        </html>
        """
        home_resp.url = "https://apexcontractors.com"

        contact_resp = MagicMock()
        contact_resp.status_code = 200
        contact_resp.text = """
        <html>
            <body>
                <h2>Contact Us</h2>
                <p>Email our team at contact@apexcontractors.com</p>
                <a href="https://www.facebook.com/ApexContractorsFL">Facebook</a>
            </body>
        </html>
        """
        contact_resp.url = "https://apexcontractors.com/contact-us"

        mock_get.side_effect = [home_resp, contact_resp]

        email, socials = crawler.crawl_website_for_email_and_social("https://apexcontractors.com")
        self.assertEqual(email, "contact@apexcontractors.com")
        self.assertTrue(any("apexcontractors" in s.lower() for s in socials["facebook"]))


class SocialCrawlingTests(unittest.TestCase):
    @patch("requests.get")
    def test_crawl_instagram_bio_email(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html>
            <head>
                <meta property="og:description" content="Commercial & Residential Electricians. Licensed & Insured. Email: service@riversideelectric.com | Call (305) 555-0199">
            </head>
        </html>
        """
        mock_resp.url = "https://www.instagram.com/riverside_electric/"
        mock_get.return_value = mock_resp

        email = crawler.crawl_social_profile_for_email("instagram", "https://www.instagram.com/riverside_electric/")
        self.assertEqual(email, "service@riversideelectric.com")

    @patch("requests.get")
    def test_crawl_facebook_email(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html>
            <body>
                <div>Email: info@miamicontractors.com</div>
            </body>
        </html>
        """
        mock_resp.url = "https://www.facebook.com/MiamiContractors/"
        mock_get.return_value = mock_resp

        email = crawler.crawl_social_profile_for_email("facebook", "https://www.facebook.com/MiamiContractors/")
        self.assertEqual(email, "info@miamicontractors.com")


class FullCrawlerWorkflowTests(unittest.TestCase):
    @patch.object(crawler, "crawl_website_for_email_and_social")
    @patch.object(crawler, "crawl_social_profile_for_email")
    def test_website_has_no_email_social_crawl_succeeds(self, mock_soc, mock_web):
        mock_web.return_value = (None, {"instagram": ["https://www.instagram.com/riverside/"], "facebook": [], "linkedin": [], "twitter": [], "youtube": []})
        mock_soc.return_value = "bids@riverside.com"

        email, meta = crawler.crawl_contractor_for_email(
            website_url="https://riverside.com",
            social_urls=[],
        )
        self.assertEqual(email, "bids@riverside.com")
        self.assertEqual(meta["email_source"], "social_crawl:instagram")
        self.assertTrue(any("instagram.com/riverside" in s for s in meta["socials"]))

    @patch.object(crawler, "crawl_website_for_email_and_social")
    @patch.object(crawler, "crawl_social_profile_for_email")
    def test_no_website_bluebook_has_social_link(self, mock_soc, mock_web):
        mock_soc.return_value = "contact@miamielectric.com"

        email, meta = crawler.crawl_contractor_for_email(
            website_url=None,
            social_urls=["https://www.instagram.com/miamielectric/"],
        )
        mock_web.assert_not_called()
        self.assertEqual(email, "contact@miamielectric.com")
        self.assertEqual(meta["email_source"], "social_crawl:instagram")


class ScraperCrawlerIntegrationTests(unittest.TestCase):
    @patch.object(crawler, "crawl_contractor_for_email")
    def test_scraper_enriches_email_and_standard_record(self, mock_crawl):
        mock_crawl.return_value = ("info@sunshine-electric.com", {"email_source": "website_crawl", "socials": ["https://instagram.com/sunshine"]})

        scraper = BlueBookScraper(headless=True)
        raw_company = {
            "id": "bluebook-12345",
            "record_kind": "company",
            "source_code": "bluebook",
            "scrapper_code": "bluebook",
            "external_id": "12345",
            "profile_url": "https://www.thebluebook.com/iProView/12345/sunshine-electric/contractors/",
            "company_name": "Sunshine Electric Co",
            "phone": "(407) 555-0188",
            "email": "",
            "website": "https://sunshine-electric.com",
            "city": "Orlando",
            "state": "FL",
            "Zip_Code": "32801",
            "category": "Electrical Contractors",
            "contact_name": "David Ray",
            "contact_title": "Master Electrician",
            "extra": {},
        }

        raw_company["email"] = "info@sunshine-electric.com"
        standard = scraper.to_standard(raw_company)
        self.assertIsInstance(standard, StandardRecord)
        self.assertEqual(standard.email, "info@sunshine-electric.com")
        self.assertEqual(standard.website, "https://sunshine-electric.com")
        self.assertEqual(standard.organization_name, "Sunshine Electric Co")

    @patch.object(crawler, "crawl_contractor_for_email")
    @patch.object(scraper_mod, "sync_playwright")
    def test_scraper_scrape_enriches_via_crawler(self, mock_playwright, mock_crawl):
        mock_crawl.return_value = (
            "bids@sunshine-electric.com",
            {
                "email_source": "website_crawl",
                "socials": ["https://www.instagram.com/sunshine_electric/"],
                "website": "https://sunshine-electric.com",
            },
        )

        mock_page = MagicMock()
        mock_page.url = "https://www.thebluebook.com/search.html"
        mock_page.content.return_value = """
        <html>
            <body>
                <h1>Electrical Contractors servicing Florida - 1 Companies Found</h1>
                <div class="single_result_wrapper" data-proview-url="/iProView/12345/sunshine-electric/contractors/">
                    <span itemprop="name">Sunshine Electric Co</span>
                    <a href="/iProView/12345/sunshine-electric/contractors/locations-contacts/">Contact Us</a>
                    <a href="https://sunshine-electric.com">Website</a>
                    <a href="https://www.instagram.com/sunshine_electric/">Instagram</a>
                    <a href="tel:4075550188">(407) 555-0188</a>
                    <p>Orlando, FL 32801</p>
                </div>
            </body>
        </html>
        """
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
        mock_playwright.return_value = mock_cm

        scraper = BlueBookScraper(headless=True)
        params = ScrapeParams(limit=1, us_state="FL", keyword="Electrical Contractors")
        results = list(scraper.scrape(params))

        self.assertEqual(len(results), 1)
        record = results[0]
        self.assertEqual(record["email"], "bids@sunshine-electric.com")
        self.assertEqual(record["website"], "https://sunshine-electric.com")
        self.assertIn("https://www.instagram.com/sunshine_electric/", record["extra"]["socials"])
        self.assertEqual(record["extra"]["email_source"], "website_crawl")
        mock_crawl.assert_called_once()

    @patch.object(crawler, "crawl_contractor_for_email")
    @patch.object(scraper_mod, "sync_playwright")
    def test_scraper_scrapes_10_categories_and_returns_emails(self, mock_playwright, mock_crawl):
        categories_10 = [
            ("Roofing Contractors", "A & D Developing LLC", "https://addeveloping.com/", "info@addeveloping.com", "website_crawl"),
            ("Waterproofing Contractors", "AM & G Waterproofing LLC", "https://amgwaterproofing.com/", "info@amgwaterproofing.com", "website_crawl"),
            ("Mason Contractors", "Amcon Contracting Corporation", "https://amcon-ny.com/", "info@amcon-ny.com", "website_crawl"),
            ("Demolition Contractors", "American Contractors NY", "http://greatamericanny.com/", "greatamericanny@gmail.com", "website_crawl"),
            ("Painting Contractors", "American Elite Contractors, Inc.", "http://americanelitecontractorsinc.com/", "estimating@americanelitecontractorsinc.com", "website_crawl"),
            ("Siding Contractors", "Apex Pro Siding & Repair", "https://apexproroofers.com/", "apexprocontracting@gmail.com", "website_crawl"),
            ("Mechanical Contractors", "McKinstry", "https://www.mckinstry.com/", "together@mckinstry.com", "website_crawl"),
            ("Concrete Contractors", "Baker Concrete Construction", "https://www.bakerconcrete.com/", "mcgahae@bakerconstruction.com", "website_crawl"),
            ("Landscape Construction", "BrightView", "https://www.brightview.com/", "communications@brightview.com", "social_crawl:facebook"),
            ("General Contractors", "Turner Construction", "https://www.turnerconstruction.com/", "turner@tcco.com", "website_crawl"),
        ]

        # Configure mock_crawl to return appropriate email per website
        crawl_responses = {
            web: (em, {"email_source": src, "socials": [], "website": web})
            for _, _, web, em, src in categories_10
        }
        mock_crawl.side_effect = lambda website_url=None, social_urls=None, timeout=None: crawl_responses.get(
            website_url, ("test@example.com", {"email_source": "mock", "socials": []})
        )

        cards_html = ""
        for idx, (cat, comp, web, em, _) in enumerate(categories_10, start=1):
            cards_html += f"""
            <div class="single_result_wrapper" data-proview-url="/iProView/{1000 + idx}/{comp.lower().replace(' ', '-')}/">
                <span itemprop="name">{comp}</span>
                <a href="/iProView/{1000 + idx}/contacts/">Contact</a>
                <a href="{web}">Website</a>
                <p>New York, NY 10001</p>
                <ul><li>{cat}</li></ul>
            </div>
            """

        mock_page = MagicMock()
        mock_page.url = "https://www.thebluebook.com/search.html"
        mock_page.content.return_value = f"<html><body><h1>Contractors - 10 Companies Found</h1>{cards_html}</body></html>"

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
        mock_playwright.return_value = mock_cm

        scraper = BlueBookScraper(headless=True)
        params = ScrapeParams(limit=10, us_state="NY", keyword="General Contractors")
        records = list(scraper.run(params))

        self.assertEqual(len(records), 10)
        for idx, (expected_cat, expected_comp, expected_web, expected_em, expected_src) in enumerate(categories_10):
            rec = records[idx]
            self.assertEqual(rec.category, expected_cat)
            self.assertEqual(rec.organization_name, expected_comp)
            self.assertEqual(rec.website, expected_web)
            self.assertEqual(rec.email, expected_em)
            self.assertEqual(rec.extra.get("email_source"), expected_src)


if __name__ == "__main__":
    unittest.main()

