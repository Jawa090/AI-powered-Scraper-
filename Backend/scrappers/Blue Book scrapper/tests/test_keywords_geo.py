import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bluebook import geo
from bluebook.keywords import build_plan, load_custom_catalog, resolve_keyword


class KeywordResolutionTests(unittest.TestCase):
    def test_user_keyword_examples(self):
        expected = {
            "construction contractors": "2200",
            "general contractors": "2200",
            "roofing contractors": "3580",
            "demolition contractors": "4850",
            "electrical contractors": "1680",
        }
        for keyword, code in expected.items():
            with self.subTest(keyword=keyword):
                resolution = resolve_keyword(keyword, expansion="off")
                self.assertFalse(resolution.unresolved)
                self.assertEqual(resolution.trades[0].trade.code, code)

    def test_groups_and_unknown_keywords(self):
        hvac_codes = {item.trade.code for item in resolve_keyword("HVAC", expansion="off").trades}
        self.assertTrue({"60", "2370", "2844"} <= hvac_codes)
        concrete_codes = {item.trade.code for item in resolve_keyword("concrete contractors", expansion="off").trades}
        self.assertTrue({"710", "720", "2130"} <= concrete_codes)
        unknown = resolve_keyword("underwater basket weaving")
        self.assertTrue(unknown.unresolved)
        self.assertTrue(unknown.suggestions)

    def test_balanced_related_expansion_is_bounded(self):
        resolution = resolve_keyword("general contractors", expansion="balanced")
        codes = [item.trade.code for item in resolution.trades]
        self.assertIn("407", codes)          # Building Alterations
        self.assertLessEqual(len([item for item in resolution.trades if item.relation == "related"]), 4)


class PlanTests(unittest.TestCase):
    def test_city_county_state_zip_and_filters(self):
        city = build_plan(["roofing contractors"], cities=["Houston, TX"], expansion="off")
        self.assertTrue(city.specs)
        self.assertTrue(all(urlsplit(s.url).path.endswith("city-search.html") for s in city.specs))
        self.assertTrue(all(parse_qs(urlsplit(s.url).query)["companylocatedin"] == ["Houston_TX"] for s in city.specs))

        county = build_plan(["electrical contractors"], counties=["Harris, TX"], expansion="off",
                            filters={"brands": ["Example Brand"], "sortfacets": ["az"]})
        first_q = parse_qs(urlsplit(county.specs[0].url).query)
        self.assertEqual(first_q["geoareaserviced"], ["Harris County(TX)"])
        self.assertEqual(first_q["brands"], ["Example Brand"])
        self.assertEqual(first_q["sortfacets"], ["az"])

        state = build_plan(["demolition"], states=["Texas"], expansion="off")
        self.assertEqual({s.region for s in state.specs}, set(geo.regions_for_state("TX")))

        zip_plan = build_plan(["general contractors"], zips=["90210"], expansion="off")
        self.assertTrue(zip_plan.specs)
        self.assertTrue(all(s.state == "CA" and s.zip == "90210" for s in zip_plan.specs))
        self.assertTrue(any("verified native ZIP" in w for w in zip_plan.warnings))

    def test_synonyms_dedupe_to_same_searches(self):
        one = build_plan(["roofing contractors"], regions=[13], expansion="off")
        two = build_plan(["roofing contractors", "roofers"], regions=[13], expansion="off")
        self.assertEqual(len(two.specs), len(one.specs))
        self.assertEqual(set(two.specs[0].metadata["keywords"]), {"roofing contractors", "roofers"})

    def test_city_both_mode_and_direct_class_code(self):
        both = build_plan(["roofing"], cities=["Dallas, TX"], regions=[12], expansion="off", location_mode="both")
        paths = {urlsplit(s.url).path for s in both.specs}
        self.assertIn("/city-search.html", paths)
        self.assertIn("/search.html", paths)

        direct = build_plan([], class_codes=["0830"], states=["CA"], expansion="off")
        self.assertTrue(direct.specs)
        self.assertTrue(all(s.class_code == "830" for s in direct.specs))

    def test_custom_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            path.write_text(json.dumps({
                "widget installers": {"trade": "Widget Installers", "class_code": "9999",
                                      "aliases": ["widget erection"]}
            }), encoding="utf-8")
            catalog = load_custom_catalog(path)
            resolution = resolve_keyword("widget erection", catalog=catalog, expansion="off")
            self.assertEqual(resolution.trades[0].trade.code, "9999")
            plan = build_plan(["widget installers"], states=["NY"], catalog=catalog, expansion="off")
            self.assertTrue(all(s.class_code == "9999" for s in plan.specs))


class GeoTests(unittest.TestCase):
    def test_location_and_zip_parsing(self):
        self.assertEqual(geo.infer_state_from_zip("10001"), "NY")
        self.assertEqual(geo.infer_state_from_zip("77002"), "TX")
        city = geo.parse_location("Denver, CO 80202")
        self.assertEqual((city["city"], city["state"], city["zip"]), ("Denver", "CO", "80202"))
        county = geo.parse_location("Harris County, TX")
        self.assertEqual((county["county"], county["state"]), ("Harris County", "TX"))
        self.assertEqual(geo.regions_for_state("CA"), [3, 7, 9, 33, 36])


if __name__ == "__main__":
    unittest.main()
