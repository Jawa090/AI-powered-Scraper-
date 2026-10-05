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
