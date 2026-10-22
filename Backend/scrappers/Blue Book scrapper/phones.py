"""US (NANP) phone normalization, validation and extraction from text.

Repo B's precision rules are retained (exclude Blue Book's own support
number, exclude fax, never trust a bare digit-string scan of a whole page).
v2 adds: E.164 + pretty forms, extension handling, NANP area/exchange
validation, and per-number provenance/confidence handled by the parsers.
"""
from __future__ import annotations

import re

# Blue Book's own sales/support lines appear in global page furniture and
# must never be attributed to a listed company (the listed company could, in
# principle, be Blue Book itself, but avoiding false attribution wins).
BLOCKLIST = {"8887201710", "8883032243", "8558052560", "8558536235", "8004312584"}

_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?\(?([2-9]\d{2})\)?[\s.\-]?([2-9]\d{2})[\s.\-]?(\d{4})(?!\d)"
    r"(?:\s*(?:ext\.?|x|extension)\s*(\d{1,6}))?",
    re.I,
)

# A number is only harvested from free text when an explicit label precedes it.
_LABELLED_RE = re.compile(
    r"\b(?:phone|telephone|tel|mobile|cell|office|direct|toll[\s\-]?free|call)\s*[:.\-]?\s*"
    r"((?:\+?1[\s.\-]?)?\(?[2-9]\d{2}\)?[\s.\-]?[2-9]\d{2}[\s.\-]?\d{4}(?:\s*(?:ext\.?|x)\s*\d{1,6})?)",
    re.I,
)


def normalize(raw: str) -> dict | None:
    """-> {'e164': '+1XXXXXXXXXX', 'pretty': '(XXX) XXX-XXXX', 'ext': ''} or None."""
    if raw is None:
        return None
    text = str(raw)
    m = _PHONE_RE.search(text)
    if not m:
        return None
    digits = "".join(m.group(i) for i in (1, 2, 3))
    if digits in BLOCKLIST:
        return None
    ext = m.group(4) or ""
    return {
        "e164": f"+1{digits}",
        "pretty": f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}",
        "ext": ext,
        "digits": digits,
    }


def display(n: dict | None) -> str:
    """Pretty phone including extension, if one was captured."""
    if not n:
        return ""
    return n.get("pretty", "") + (f" ext. {n['ext']}" if n.get("ext") else "")


def find_in_text(text: str) -> list[dict]:
    """All plausible NANP numbers in a text fragment (deduplicated)."""
    out: dict[str, dict] = {}
    for m in _PHONE_RE.finditer(str(text or "")):
        n = normalize(m.group(0))
        if n:
            out.setdefault(n["e164"] + n["ext"], n)
    return list(out.values())


def find_labelled(text: str) -> list[dict]:
    """Numbers explicitly labelled phone/tel/mobile/... in text (Repo B rule)."""
    out: dict[str, dict] = {}
    for m in _LABELLED_RE.finditer(str(text or "")):
        n = normalize(m.group(1))
        if n:
            out.setdefault(n["e164"] + n["ext"], n)
    return list(out.values())


def is_fax_context(*fragments: str) -> bool:
    blob = " ".join(str(f or "") for f in fragments).lower()
    return "fax" in blob
