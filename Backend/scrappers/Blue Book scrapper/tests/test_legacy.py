import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import pytest

pytest.skip("Legacy SQLite store and migration modules were removed during BaseScraper modularization", allow_module_level=True)

from bluebook.legacy import import_legacy_db
from bluebook.store import Store



def make_legacy(path: Path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE jobs(url TEXT PRIMARY KEY,kind TEXT,category TEXT,state TEXT DEFAULT 'pending',error TEXT DEFAULT '')")
    db.execute("CREATE TABLE leads(id TEXT PRIMARY KEY,data TEXT)")
    leads = [
        {"company": "Phone Less Co", "phone": "", "contact_name": "", "contact_title": "",
         "address": "", "category": "General contractors",
         "profile_url": "https://www.thebluebook.com/iProView/111/phone-less/general-contractors/",
         "source_url": "https://www.thebluebook.com/search.html?class=2200&page=2&region=3",
         "status": "Profile read; missing fields were not publicly found"},
        {"company": "Has Phone Co", "phone": "3105550142; 2135550177", "contact_name": "",
         "contact_title": "", "address": "", "category": "General contractors",
         "profile_url": "https://www.thebluebook.com/iProView/222/has-phone/general-contractors/",
         "source_url": "https://www.thebluebook.com/search.html?class=2200&page=3&region=3",
         "status": "x"},
        # Repo B artefact row: profile_url is the homepage (no iProView id).
        {"company": "Bogus Row", "phone": "", "contact_name": "", "contact_title": "",
         "address": "", "category": "General contractors",
         "profile_url": "https://www.thebluebook.com",
         "source_url": "https://www.thebluebook.com/search.html?class=2200&page=83&region=3",
         "status": "x"},
    ]
    for lead in leads:
        db.execute("INSERT INTO leads VALUES(?,?)", (lead["profile_url"], json.dumps(lead)))
    db.commit()
    db.close()


class LegacyImportTests(unittest.TestCase):
    def test_import_rejects_bogus_and_queues_enrichment(self):
        with tempfile.TemporaryDirectory() as td:
            legacy = Path(td) / "progress.sqlite3"
            make_legacy(legacy)
            store = Store(Path(td) / "v2.sqlite3")
            result = import_legacy_db(store, legacy)
            self.assertEqual(result["imported"], 2)
            self.assertEqual(result["rejected"], 1)
            self.assertEqual(result["without_phone"], 1)
            self.assertEqual(result["queued_contacts_jobs"], 2)
            stats = store.stats()
            self.assertEqual(stats["companies"], 2)
            self.assertEqual(stats["field_fill"]["phone"], 1)
            self.assertEqual(stats["locations_rows"], 0)  # no fake locations from extra numbers
            has_phone = next(c for c in store.companies_flat() if c["company_id"] == "222")
            self.assertIn("(213) 555-0177", has_phone["all_phones"])
            # Phone-less company's contacts job is scheduled first.
            job = store.next_job()
            self.assertIn("/iProView/111/", job["url"])
            self.assertEqual(job["kind"], "contacts")
            store.close()


if __name__ == "__main__":
    unittest.main()
