import unittest

from bluebook import phones, urls


class UrlTests(unittest.TestCase):
    def test_canonical_rejects_empty_and_foreign(self):
        # Repo B bug: canonical('') returned the homepage -> bogus lead.
        self.assertEqual(urls.canonical(""), "")
        self.assertEqual(urls.canonical("https://example.com/x"), "")

    def test_company_identity_is_numeric_id(self):
        a = "https://www.thebluebook.com/iProView/553737/acme/general-contractors/"
        b = "https://www.thebluebook.com/iProView/553737/acme/subcontractors/"
        self.assertEqual(urls.company_id(a), urls.company_id(b))
        self.assertEqual(urls.company_id(a), "553737")

    def test_contacts_url_needs_slug(self):
        self.assertEqual(
            urls.contacts_url("https://www.thebluebook.com/iProView/1/acme/general-contractors/"),
            "https://www.thebluebook.com/iProView/1/acme/general-contractors/locations-contacts/")
        self.assertEqual(urls.contacts_url("https://www.thebluebook.com/iProView/1"), "")

    def test_same_search_containment(self):
        seed = "https://www.thebluebook.com/search.html?region=3&class=2200"
        self.assertTrue(urls.same_search(seed, seed + "&page=4"))
        # The site adds a display searchTerm to its own pagination hrefs.
        self.assertTrue(urls.same_search(seed, seed + "&searchTerm=General+Contractors&page=4"))
        self.assertFalse(urls.same_search(seed, "https://www.thebluebook.com/search.html?region=4&class=2200&page=4"))
        self.assertFalse(urls.same_search(seed, seed + "&unknownfilter=1&page=4"))

    def test_kind_classification(self):
        self.assertEqual(urls.kind_of("https://www.thebluebook.com/search.html?region=3"), "listing")
        self.assertEqual(urls.kind_of("https://www.thebluebook.com/iSearch/results/tx/houston/plumbing/sc/261/"), "listing")
        self.assertEqual(urls.kind_of("https://www.thebluebook.com/iProView/9/x/general-contractors/locations-contacts/"), "contacts")
        self.assertEqual(urls.kind_of("https://www.thebluebook.com/iProView/9"), "profile")


class PhoneTests(unittest.TestCase):
    def test_normalize_formats_and_ext(self):
        n = phones.normalize("(310) 555-0142 ext 12")
        self.assertEqual(n["e164"], "+13105550142")
        self.assertEqual(n["pretty"], "(310) 555-0142")
        self.assertEqual(n["ext"], "12")
        self.assertEqual(phones.normalize("+1 310.555.0142")["e164"], "+13105550142")

    def test_blocklist_and_invalid(self):
        self.assertIsNone(phones.normalize("888-720-1710"))  # Blue Book support
        self.assertIsNone(phones.normalize("123-456-7890"))  # area starts with 1
        self.assertIsNone(phones.normalize("not a phone"))

    def test_labelled_only(self):
        hits = phones.find_labelled("Call us. Phone: 310-555-0142. Est. 1998. Alt 213-555-0177")
        self.assertEqual([h["e164"] for h in hits], ["+13105550142"])


if __name__ == "__main__":
    unittest.main()
