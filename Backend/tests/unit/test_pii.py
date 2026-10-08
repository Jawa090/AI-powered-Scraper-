"""
tests/unit/test_pii.py — PII masking tests (P16.6, P17.1)
"""
import sys
from pathlib import Path

# Ensure Backend is on sys.path
_backend = str(Path(__file__).resolve().parent.parent.parent)
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from utils.pii import mask_email, mask_phone, mask_text


class TestMaskEmail:
    def test_normal_email(self):
        assert mask_email("john.doe@acme.com") == "j***@acme.com"

    def test_single_char_local(self):
        assert mask_email("j@acme.com") == "*@acme.com"

    def test_empty(self):
        assert mask_email("") == ""

    def test_no_at_sign(self):
        assert mask_email("notanemail") == "notanemail"


class TestMaskPhone:
    def test_us_phone(self):
        result = mask_phone("+12145550100")
        assert result.startswith("+1")
        assert result.endswith("0100")
        assert "***" in result

    def test_short_phone(self):
        assert mask_phone("12345") == "12345"

    def test_empty(self):
        assert mask_phone("") == ""


class TestMaskText:
    def test_masks_email_in_text(self):
        text = "Contact john.doe@acme.com for details"
        result = mask_text(text)
        assert "john.doe@acme.com" not in result
        assert "j***@acme.com" in result

    def test_masks_phone_in_text(self):
        text = "Call 214-555-0100 now"
        result = mask_text(text)
        assert "214-555-0100" not in result

    def test_masks_both(self):
        text = "Email alice@example.com or call 214-555-0100"
        result = mask_text(text)
        assert "alice@example.com" not in result
        assert "214-555-0100" not in result

    def test_none_input(self):
        assert mask_text(None) == ""

    def test_empty_input(self):
        assert mask_text("") == ""

    def test_no_pii(self):
        text = "This has no PII data"
        assert mask_text(text) == text
