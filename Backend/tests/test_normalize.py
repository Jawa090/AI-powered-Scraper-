"""
tests/test_normalize.py
───────────────────────
Unit tests for Database/normalize.py — pure normalization functions.
"""

import pytest
import sys
import os

import _paths

from Database.normalize import (
    normalize_name,
    normalize_domain,
    normalize_phone,
    normalize_email,
    normalize_state,
    parse_location,
    parse_due_date,
    org_key,
    lead_identity,
    fingerprint,
)


class TestNormalizeName:
    """Test company/org name normalization."""

    def test_basic_lowercase(self):
        assert normalize_name("ACME") == "acme"

    def test_strip_inc(self):
        assert normalize_name("Acme, Inc.") == "acme"

    def test_strip_llc(self):
        assert normalize_name("Smith Plumbing LLC") == "smith plumbing"

    def test_strip_corporation(self):
        assert normalize_name("ABC Corporation") == "abc"

    def test_strip_corp(self):
        assert normalize_name("XYZ Corp.") == "xyz"

    def test_match_across_variations(self):
        """'Acme, Inc.' and 'ACME Inc' should normalize to the same value."""
        assert normalize_name("Acme, Inc.") == normalize_name("ACME Inc")

    def test_unicode_nfkc(self):
        # Full-width A → normal A
        assert normalize_name("Ａcme") == "acme"

    def test_collapse_whitespace(self):
        assert normalize_name("  Acme   Corp  ") == "acme"

    def test_none_input(self):
        assert normalize_name(None) is None

    def test_empty_string(self):
        assert normalize_name("") is None

    def test_whitespace_only(self):
        assert normalize_name("   ") is None

    def test_just_legal_suffix(self):
        assert normalize_name("LLC") is None


class TestNormalizeDomain:
    """Test domain extraction and normalization."""

    def test_full_url(self):
        assert normalize_domain("https://www.example.com/page") == "example.com"

    def test_www_stripping(self):
        assert normalize_domain("www.example.com") == "example.com"

    def test_bare_domain(self):
        assert normalize_domain("example.com") == "example.com"

    def test_http_scheme(self):
        assert normalize_domain("http://EXAMPLE.COM") == "example.com"

    def test_none_input(self):
        assert normalize_domain(None) is None

    def test_empty_string(self):
        assert normalize_domain("") is None

    def test_no_dot(self):
        assert normalize_domain("localhost") is None


class TestNormalizePhone:
    """Test phone normalization to E.164 format."""

    def test_parenthesized(self):
        result = normalize_phone("(214) 555-0100")
        assert result is not None
        assert result.startswith("+1")

    def test_dotted(self):
        result = normalize_phone("214.555.0100")
        assert result is not None

    def test_same_result_different_formats(self):
        """Different formats of the same number should normalize identically."""
        a = normalize_phone("(214) 555-0100")
        b = normalize_phone("214.555.0100")
        c = normalize_phone("+1 214 555 0100")
        assert a == b == c

    def test_none_input(self):
        assert normalize_phone(None) is None

    def test_empty_string(self):
        assert normalize_phone("") is None

    def test_too_short(self):
        assert normalize_phone("123") is None


class TestNormalizeEmail:
    """Test email normalization."""

    def test_basic(self):
        assert normalize_email("User@Example.COM") == "user@example.com"

    def test_strip_whitespace(self):
        assert normalize_email("  test@email.com  ") == "test@email.com"

    def test_none_input(self):
        assert normalize_email(None) is None

    def test_empty_string(self):
        assert normalize_email("") is None

    def test_invalid_email(self):
        assert normalize_email("not-an-email") is None

    def test_no_tld(self):
        assert normalize_email("user@domain") is None


class TestFingerprint:
    """Test dedup fingerprint generation."""

    def test_same_data_same_fingerprint(self):
        fp1 = fingerprint(name="Acme Inc.", domain="acme.com")
        fp2 = fingerprint(name="ACME, Inc", domain="www.acme.com")
        assert fp1 == fp2

    def test_different_data_different_fingerprint(self):
        fp1 = fingerprint(name="Acme Inc.", domain="acme.com")
        fp2 = fingerprint(name="Beta Corp", domain="beta.com")
        assert fp1 != fp2

    def test_all_none_returns_none(self):
        assert fingerprint() is None
        assert fingerprint(name=None, domain=None) is None

    def test_returns_64_char_hex(self):
        fp = fingerprint(name="Test Company")
        assert fp is not None
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_phone_contributes(self):
        fp_no_phone = fingerprint(name="Acme")
        fp_with_phone = fingerprint(name="Acme", phone="(212) 555-1234")
        assert fp_no_phone != fp_with_phone


class TestNormalizeState:
    """Test state normalization to 2-letter uppercase USPS code."""

    def test_full_state_name(self):
        assert normalize_state("Texas") == "TX"
        assert normalize_state("new york") == "NY"
        assert normalize_state("CALIFORNIA") == "CA"

    def test_abbreviation(self):
        assert normalize_state("TX") == "TX"
        assert normalize_state("ny") == "NY"
        assert normalize_state("Tx.") == "TX"

    def test_dc_and_territories(self):
        assert normalize_state("District of Columbia") == "DC"
        assert normalize_state("Puerto Rico") == "PR"
        assert normalize_state("guam") == "GU"

    def test_invalid_and_none(self):
        assert normalize_state(None) is None
        assert normalize_state("") is None
        assert normalize_state("   ") is None
        assert normalize_state("Atlantis") is None


class TestParseLocation:
    """Test parsing location string into (city, state, postal)."""

    def test_city_state_zip(self):
        assert parse_location("Dallas, TX 75201") == ("Dallas", "TX", "75201")
        assert parse_location("Dallas, TX, 75201") == ("Dallas", "TX", "75201")

    def test_city_full_state_zip(self):
        assert parse_location("Dallas, Texas 75201") == ("Dallas", "TX", "75201")

    def test_city_state_only(self):
        assert parse_location("Dallas, TX") == ("Dallas", "TX", None)
        assert parse_location("Albany, New York") == ("Albany", "NY", None)

    def test_city_only(self):
        assert parse_location("Houston") == ("Houston", None, None)

    def test_state_only(self):
        assert parse_location("Texas") == (None, "TX", None)
        assert parse_location("TX") == (None, "TX", None)

    def test_zip_only(self):
        assert parse_location("75201") == (None, None, "75201")

    def test_trailing_country_stripped(self):
        assert parse_location("Dallas, TX, USA") == ("Dallas", "TX", None)
        assert parse_location("New York, NY, US") == ("New York", "NY", None)

    def test_zip_plus_four(self):
        assert parse_location("New York, NY 10001-1234") == ("New York", "NY", "10001-1234")

    def test_none_and_empty(self):
        assert parse_location(None) == (None, None, None)
        assert parse_location("") == (None, None, None)
        assert parse_location("   ") == (None, None, None)


class TestParseDueDate:
    """Test parsing due date string into datetime object."""

    def test_iso_format(self):
        dt = parse_due_date("2026-11-15T14:30:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 11
        assert dt.day == 15

    def test_us_date_format(self):
        dt = parse_due_date("10/25/2026")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 10
        assert dt.day == 25

    def test_natural_date_format(self):
        dt = parse_due_date("November 1, 2026 5:00 PM")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 11
        assert dt.day == 1
        assert dt.hour == 17

    def test_invalid_and_empty(self):
        assert parse_due_date(None) is None
        assert parse_due_date("") is None
        assert parse_due_date("not-a-date") is None


class TestOrgKey:
    """Test organization deduplication key generation."""

    def test_same_org_same_key(self):
        k1 = org_key(name="Acme Inc.", domain="acme.com", phone="214-555-0100")
        k2 = org_key(name="ACME", domain="www.acme.com", phone="(214) 555-0100")
        assert k1 == k2

    def test_missing_name_returns_none(self):
        assert org_key(name=None) is None
        assert org_key(name="") is None

    def test_returns_64_char_hex(self):
        k = org_key(name="City of Dallas Procurement")
        assert k is not None
        assert len(k) == 64
        assert all(c in "0123456789abcdef" for c in k)


class TestLeadIdentity:
    """Test lead identity_key generation according to D7."""

    def test_opportunity_source_and_external_id(self):
        id_key = lead_identity(kind="opportunity", source_code="bonfire", external_id="BID-12345")
        assert id_key == "src:bonfire:BID-12345"

    def test_opportunity_strips_legacy_prefix(self):
        id_key = lead_identity(kind="opportunity", source_code="nyscr", external_id="nyscr_9988")
        assert id_key == "src:nyscr:9988"

    def test_company_fingerprint(self):
        fp = fingerprint(name="Acme Inc.", phone="214-555-0100")
        id_key = lead_identity(kind="company", fingerprint=fp)
        assert id_key == f"fp:{fp}"

    def test_opportunity_missing_external_id_returns_none(self):
        assert lead_identity(kind="opportunity", source_code="bonfire", external_id=None) is None

    def test_company_missing_fingerprint_returns_none(self):
        assert lead_identity(kind="company", fingerprint=None) is None
