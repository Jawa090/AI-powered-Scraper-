"""
Routing accuracy regression tests for the rule-based path (QueryParser +
recommend_scraper). This is the path the chatbot takes whenever the LLM is
unavailable, so it must pick the right category, location and scraper.

Pure unit tests: no database, no LLM, no network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.query.parser import QueryParser
from execution.registry import recommend_scraper

# (prompt, category, location, quantity, scraper)
CASES = [
    ("Find 50 plumbers in New York", "Plumber", "New York", 50, "jwiz"),
    ("I need 20 plumbing contractors in Brooklyn", "Plumber", "Brooklyn", 20, "jwiz"),
    ("Get me 30 electricians in New Jersey", "Electrician", "New Jersey", 30, "jwiz"),
    ("Find 10 roofing contractors in Queens", "Roofing Contractors", "Queens", 10, "jwiz"),
    ("Give us 10 HVAC contractors in Manhattan", "HVAC", "Manhattan", 10, "jwiz"),
    ("50 contractors in the Bronx", "Contractor", "Bronx", 50, "jwiz"),
    ("I want 100 carpenters in Buffalo", "Carpenter", "Buffalo", 100, "jwiz"),
    ("Find 20 roofers near Albany NY", "Roofing", "Albany", 20, "jwiz"),
    ("Get 10 electrical contractors in Lakewood NJ", "Electrical Contractors", "Lakewood", 10, "jwiz"),
    ("Need 5 landscaping companies in New York", "Landscaping", "New York", 5, "jwiz"),
    ("Find 25 plumbers in Houston, Texas", "Plumber", "Houston", 25, "jwiz"),
    ("Find 10 general contractors in Dallas", "General Contractor", "Dallas", 10, "jwiz"),
    ("1000 GC contractor in NY from JWiz", "General Contractor", "New York", 1000, "jwiz"),
    ("Find 20 plumbers in Philadelphia this week", "Plumber", "Philadelphia", 20, "jwiz"),
    ("Find 15 painters in Staten Island", "Painter", "Staten Island", 15, "jwiz"),
    ("Show me 25 open bids from Dallas City Hall", "All Open Opportunities", "Dallas", 25, "bonfire"),
    ("15 paving RFPs in Dallas", "Paving & Road Repairs", "Dallas", 15, "bonfire"),
    ("Find 30 street sweeping contracts in Dallas", "Street Sweeping", "Dallas", 30, "bonfire"),
    ("Find 20 DASNY construction bids", "Construction", "New York", 20, "dasny"),
    ("I need 40 construction RFPs in New York", "Construction", "New York", 40, "dasny"),
    ("Show 12 architectural bids from DASNY", "Architectural Services", "New York", 12, "dasny"),
    ("Find 20 state contracts from the NY contract reporter", "All Open Opportunities", "New York", 20, "nyscr"),
]


class TestQueryRouting(unittest.TestCase):
    def test_routing_cases(self):
        for prompt, cat, loc, qty, script in CASES:
            with self.subTest(prompt=prompt):
                q = QueryParser.parse(prompt)
                self.assertEqual(q.category, cat)
                self.assertEqual(q.location, loc)
                self.assertEqual(q.quantity, qty)
                chosen = q.source_preference or recommend_scraper(q.category, q.location, q.original_text)
                self.assertEqual(chosen, script)

    def test_contractor_is_not_a_contract(self):
        """'contractor' must not flip a business search into procurement."""
        self.assertEqual(QueryParser.parse("Find 10 roofing contractors in Queens").intent, "lead_search")

    def test_greeting_needs_a_whole_word(self):
        """'hi' inside 'which' / 'Philadelphia' is not a greeting."""
        self.assertEqual(QueryParser.parse("hi, what can you do?").intent, "general_inquiry")
        self.assertNotEqual(QueryParser.parse("Which plumbers do we have in New York?").intent, "general_inquiry")
        self.assertNotEqual(QueryParser.parse("Find 20 plumbers in Philadelphia").intent, "general_inquiry")

    def test_us_pronoun_is_not_a_location(self):
        self.assertIsNone(QueryParser.parse("Give us 10 plumbers").location)


if __name__ == "__main__":
    unittest.main()
