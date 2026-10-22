"""Person-name normalization shared by parser, store, and exports.

Normalization is intentionally conservative: case, accents, punctuation, and
whitespace are ignored, and a leading honorific may be dropped, but token
order and suffix tokens are retained.  This prevents merely similar names
("Anna Lee" vs "Ann A. Lee", or "John Smith" vs "John Smith Jr.") from being
treated as the same individual solely because they look alike.
"""
from __future__ import annotations

import re
import unicodedata

_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "doctor"}


def normalize_person_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).casefold()
    tokens = text.split()
    while tokens and tokens[0] in _HONORIFICS:
        tokens.pop(0)
    return " ".join(tokens)
