import csv
import tempfile
import unittest
from pathlib import Path
import pytest

pytest.skip("Standalone SQLite store, ingest, and exporter modules were removed during BaseScraper modularization", allow_module_level=True)

from bluebook.export import export_all
from bluebook.ingest import ingest_html
from bluebook.store import Store


FIX = Path(__file__).parent / "fixtures"
LISTING_URL = "https://www.thebluebook.com/search.html?region=3&class=2200"
PROFILE_URL = "https://www.thebluebook.com/iProView/553737/acme-builders-inc/general-contractors/"
CONTACTS_URL = PROFILE_URL + "locations-contacts/"


class EndToEndOffline(unittest.TestCase):
    def test_ingest_stats_dedupe_export(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / "t.sqlite3")
            info = ingest_html(store, (FIX / "listing.html").read_text(), LISTING_URL,
                               category="General contractors")
            self.assertEqual(info["companies"], 2)
            self.assertEqual(info["expected_count"], 52)
            # 52 expected / 2 per page = 26 pages; linked 2,3 -> rest synthesized.
            self.assertGreater(info["pagination_synthesized"], 0)

            ingest_html(store, (FIX / "profile.html").read_text(), PROFILE_URL)
            ingest_html(store, (FIX / "contacts.html").read_text(), CONTACTS_URL)

            # Slug-variant of the same company must merge, not duplicate.
            store.upsert_company({"company_id": "553737", "name": "Acme Builders, Inc.",
                                  "pretty_url": PROFILE_URL.replace("general-contractors",
                                                                      "subcontractors")})
            stats = store.stats()
            self.assertEqual(stats["companies"], 2)
            self.assertEqual(stats["field_fill"]["phone"], 2)   # Acme via contacts, Beta via listing
            self.assertEqual(stats["contacts_rows"], 3)
            # One authoritative Acme location (the weak listing candidate is
            # upgraded/merged) plus Beta's preserved search-result location.
            self.assertEqual(stats["locations_rows"], 2)
            self.assertEqual(stats["coverage"][0]["discovered"], 2)
            self.assertEqual(stats["coverage"][0]["expected_count"], 52)

            # Merge preservation: an empty re-scrape never wipes a known phone.
            store.upsert_company({"company_id": "553737", "phone": "", "name": "Acme Builders, Inc."})
            self.assertEqual(store.stats()["field_fill"]["phone"], 2)

            out = Path(td) / "exports"
            result = export_all(store, out, formats=("csv", "jsonl"))
            self.assertEqual(result["counts"]["companies"], 2)
            with open(out / "companies.csv", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
            acme = next(r for r in rows if r["company_id"] == "553737")
            self.assertEqual(acme["phone"], "(310) 555-0142")
            self.assertEqual(acme["phone_e164"], "+13105550142")  # no injection-guard apostrophe
            self.assertEqual(acme["primary_contact_name"], "Jane Doe")
            self.assertIn("MBE", acme["certifications"])
            self.assertEqual(acme["contacts_count"], "3")
            store.close()

    def test_page1_job_dedupes_with_seed(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / "t.sqlite3")
            seed = store.add_search(LISTING_URL, "GC")
            # The site's own pagination links page=1 explicitly; Repo B queued it twice.
            self.assertFalse(store.add_job(LISTING_URL + "&page=1", "listing", search_url=seed))
            store.close()

    def test_retry_missing_and_resume(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.sqlite3"
            store = Store(db)
            store.upsert_company({"company_id": "42", "name": "No Phone Co",
                                  "pretty_url": "https://www.thebluebook.com/iProView/42/no-phone/general-contractors/"})
            store.upsert_company({"company_id": "43", "name": "Has Phone Co", "phone": "(310) 555-0142",
                                  "phone_e164": "+13105550142"})
            self.assertEqual(store.retry_missing("phone"), 1)
            job = store.next_job()
            self.assertIn("locations-contacts", job["url"])
            store.mark_done(job["url"])
            fallback = store.next_job()  # profile fallback for the same company
            self.assertEqual(fallback["kind"], "profile")
            store.mark_done(fallback["url"])
            store.close()
            store = Store(db)  # resume: done jobs stay done
            self.assertIsNone(store.next_job())
            store.close()


if __name__ == "__main__":
    unittest.main()
