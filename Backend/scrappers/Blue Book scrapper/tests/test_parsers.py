import unittest
from pathlib import Path

from bluebook.parsers import detect_access, parse_contacts, parse_listing, parse_profile
from bluebook.names import normalize_person_name


FIX = Path(__file__).parent / "fixtures"
LISTING_URL = "https://www.thebluebook.com/search.html?region=3&class=2200"
PROFILE_URL = "https://www.thebluebook.com/iProView/553737/acme-builders-inc/general-contractors/"
CONTACTS_URL = PROFILE_URL + "locations-contacts/"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


class ListingTests(unittest.TestCase):
    def test_cards_pagination_expected(self):
        r = parse_listing(load("listing.html"), LISTING_URL, "General contractors")
        self.assertEqual(r["expected_count"], 52)
        self.assertEqual(len(r["companies"]), 2)
        by_id = {c["company_id"]: c for c in r["companies"]}
        self.assertEqual(by_id["553737"]["name"], "Acme Builders, Inc.")
        self.assertEqual(by_id["553737"]["website"], "https://acme.example.com/")
        self.assertEqual(by_id["1326610"]["phone_e164"], "+12135550177")
        self.assertEqual(by_id["1326610"]["city_state"], "Los Angeles, CA")
        # Sponsor outside the cleaned scope / cards must not appear.
        self.assertNotIn("9999999", by_id)
        # Only same-search pagination (other region excluded).
        self.assertEqual(len(r["pagination"]), 2)
        self.assertTrue(all("region=3" in p for p in r["pagination"]))


class ProfileTests(unittest.TestCase):
    def test_profile_fields(self):
        d = parse_profile(load("profile.html"), PROFILE_URL, "Acme Builders, Inc.")
        self.assertEqual(d["company_id"], "553737")
        self.assertEqual(d["name"], "Acme Builders, Inc.")
        self.assertEqual(d["website"], "https://acme.example.com/")
        self.assertIn("Construction Management", d["trades"])
        self.assertIn("Orange County", d["service_areas"])
        self.assertEqual(d["listed_since"], "2005")
        self.assertEqual(d["established"], "1998")
        self.assertEqual(d["company_size"], "10-24 Employees")
        self.assertEqual(d["annual_volume"], "$1M - $5M")
        self.assertEqual(d["certifications"], ["MBE", "DBE"])
        self.assertTrue(d["csi_codes"])
        self.assertTrue(any("linkedin" in s for s in d["socials"]))
        self.assertEqual(d["contacts_url"], CONTACTS_URL)
        # Unrelated JSON-LD sponsor phone must never be adopted.
        self.assertNotEqual(d["phone_e164"], "+12125550199")


class ContactsTests(unittest.TestCase):
    def test_locations_and_all_contact_groups(self):
        d = parse_contacts(load("contacts.html"), CONTACTS_URL, "Acme Builders, Inc.")
        self.assertEqual(len(d["locations"]), 1)
        loc = d["locations"][0]
        self.assertEqual(loc["phone"], "(310) 555-0142")
        self.assertEqual(loc["fax"], "(310) 555-0143")  # fax separated, not a phone
        self.assertEqual(loc["city"], "Torrance")
        self.assertEqual(loc["state"], "CA")
        self.assertEqual(loc["zip"], "90502")
        self.assertTrue(loc["is_main"])
        self.assertEqual(d["phone"], "(310) 555-0142")
        self.assertEqual(d["phone_source"], "tel_link")

        self.assertEqual(len(d["contacts"]), 3)  # no 7-contact XPath cap issues; all groups
        by_name = {c["name"]: c for c in d["contacts"]}
        self.assertEqual(by_name["Jane Doe"]["title"], "President")
        self.assertIn("Owners", by_name["Jane Doe"]["department"])
        self.assertEqual(by_name["John Doe"]["phone"], "(310) 555-0144")
        self.assertEqual(by_name["John Doe"]["fax"], "(310) 555-0143")
        self.assertIn("Estimating", by_name["Alex Roe"]["department"])
        self.assertEqual(by_name["Alex Roe"]["title"], "Estimator")


class AccessTests(unittest.TestCase):
    def test_detect_access(self):
        self.assertEqual(detect_access("<html>Verify you are human</html>"), "challenge")
        self.assertEqual(detect_access("<html>Request blocked</html>", 403), "blocked")
        self.assertEqual(detect_access("<html>Normal results</html>"), "")


LISTING_DUP_URL = "https://www.thebluebook.com/search.html?region=12&class=3580"
PROFILE_RICH_URL = "https://www.thebluebook.com/iProView/318510/harbor-mechanical/subcontractors/"
PROFILE_PEOPLE_URL = "https://www.thebluebook.com/iProView/424242/widget-builders/general-contractors/"


class ParserEnhancementTests(unittest.TestCase):
    def test_duplicate_listing_cards_preserve_branch_data(self):
        result = parse_listing(load("listing_duplicates.html"), LISTING_DUP_URL)
        self.assertEqual(result["result_rows"], 2)
        self.assertEqual(result["per_page"], 2)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(result["max_page"], 7)
        self.assertEqual(len(result["companies"]), 1)
        company = result["companies"][0]
        self.assertEqual(company["profile_url"], "https://www.thebluebook.com/iProView/777123/widget-roofing/subcontractors/")
        self.assertEqual(company["email"], "bids@widget-roofing.test")
        self.assertIn("estimating@widget-roofing.test", company["extra_emails"])
        self.assertEqual(len(company["locations"]), 2)
        all_phones = {company["phone"], *company["extra_phones"]}
        self.assertTrue({"(214) 555-0101", "(817) 555-0102", "(817) 555-0199"} <= all_phones)
        self.assertEqual({r["class_code"] for r in result["related_searches"]}, {"4660", "9999"})

    def test_rich_profile_email_address_codes_and_service_areas(self):
        data = parse_profile(load("profile_rich.html"), PROFILE_RICH_URL)
        self.assertEqual(data["email"], "hello@harbor-mechanical.test")
        self.assertIn("bids@harbor-mechanical.test", data["extra_emails"])
        self.assertEqual((data["street"], data["city"], data["state"], data["zip"]),
                         ("51 Church St.", "Freeport", "NY", "11520"))
        self.assertIn("1680", data["trade_codes"])
        self.assertIn("Electrical Contractors", data["trades"])
        self.assertIn("Nassau County, New York", data["service_areas"])
        self.assertIn("MWBE", data["certifications"])
        self.assertEqual(data["established"], "1999")
        self.assertEqual(data["company_size"], "25-49 Employees")

    def test_contacts_preserve_alternate_rows_and_partial_surname(self):
        html = """<html><head><title>Widget Co - Locations and Key Contacts</title></head><body><main>
        <div id='keyContactSection'><h4>Owners, Principals & Senior Executives</h4>
          <div><button>Casey Example</button><div>President</div><a href='tel:+12125550101'>(212) 555-0101</a></div>
          <div><button>Casey Example</button><div>President</div><a href='tel:+12125550102'>(212) 555-0102</a></div>
          <div><button>Donna .</button><div>Estimator</div>
               <a href='tel:+12125550103'>(212) 555-0103</a>
               <a href='mailto:Donna@widget.test'>Email</a></div>
        </div></main></body></html>"""
        data = parse_contacts(html, "https://www.thebluebook.com/iProView/99/widget/general-contractors/locations-contacts/",
                              expected_name="Widget Co")
        casey = [c for c in data["contacts"] if c["name"] == "Casey Example"]
        self.assertEqual(len(casey), 2)
        donna = next(c for c in data["contacts"] if c["name"] == "Donna .")
        self.assertEqual(donna["email"], "Donna@widget.test")


class PeopleParserTests(unittest.TestCase):
    def test_profile_management_estimating_and_labelled_people(self):
        data = parse_profile(load("profile_people.html"), PROFILE_PEOPLE_URL)
        by_name = {c["name"]: c for c in data["contacts"]}
        self.assertTrue({"Casey Example", "Donna Lee", "Robin Johnson", "Avery Stone"} <= set(by_name))
        self.assertEqual(by_name["Casey Example"]["title"], "President")
        self.assertEqual(by_name["Casey Example"]["email"], "Casey@widget-builders.test")
        self.assertEqual(by_name["Donna Lee"]["phone"], "(214) 555-0198")
        self.assertEqual(by_name["Avery Stone"]["department"], "Project Management")

    def test_contacts_all_sections_and_location_person(self):
        html = """<html><head><title>Widget Co - Locations and Key Contacts</title></head><body><main>
        <section><h2>Locations</h2><div id='locationsPage-1'><div>
          <h3>Widget Co</h3><div>100 Main St.<br>Dallas, TX 75201</div>
          <a href='tel:+12145550100'>(214) 555-0100</a>
          <p><strong>Location Person</strong><br>Branch Manager</p>
        </div></div></section>
        <section><h2>Key Contacts</h2><div id='keyContactSection'>
          <div><button>Key Person</button><div>President</div><a href='tel:+12145550101'>(212) 555-0101</a></div>
        </div></section>
        <section><h2>Company Management</h2>
          <div><strong>Management Person</strong><div>Operations Manager</div><a href='tel:+12145550102'>(214) 555-0102</a></div>
        </section>
        <section><h2>Principal Contacts</h2><div>Principal Contact: Principal Person</div></section>
        </main></body></html>"""
        data = parse_contacts(
            html, "https://www.thebluebook.com/iProView/99/widget/general-contractors/locations-contacts/",
            expected_name="Widget Co")
        names = {c["name"] for c in data["contacts"]}
        self.assertTrue({"Location Person", "Key Person", "Management Person", "Principal Person"} <= names)

    def test_person_name_normalization_is_conservative(self):
        self.assertEqual(normalize_person_name("Dr. Casey Example"), "casey example")
        self.assertNotEqual(normalize_person_name("Donna Smith"), normalize_person_name("Donna Smith Jr."))
        self.assertNotEqual(normalize_person_name("Anna Lee"), normalize_person_name("Ann A. Lee"))


class AddressParserTests(unittest.TestCase):
    def test_address_lines_rejects_buttons_and_phones_as_street(self):
        from bluebook.parsers import _parse_address_lines
        lines = ["Contact Us", "Website", "(212) 555-0101", "New York, NY 10001", "Roofing Contractors"]
        addr = _parse_address_lines(lines)
        self.assertEqual(addr["street"], "")
        self.assertEqual(addr["city"], "New York")
        self.assertEqual(addr["state"], "NY")
        self.assertEqual(addr["zip"], "10001")
        self.assertEqual(addr["address_raw"], "New York, NY 10001")

    def test_address_lines_preserves_legitimate_street_address(self):
        from bluebook.parsers import _parse_address_lines
        lines = ["Acme Roofing Inc", "123 Main St., Suite 400", "New York, NY 10001"]
        addr = _parse_address_lines(lines)
        self.assertEqual(addr["street"], "123 Main St., Suite 400")
        self.assertEqual(addr["city"], "New York")
        self.assertEqual(addr["state"], "NY")
        self.assertEqual(addr["zip"], "10001")
        self.assertEqual(addr["address_raw"], "123 Main St., Suite 400, New York, NY 10001")


if __name__ == "__main__":
    unittest.main()

