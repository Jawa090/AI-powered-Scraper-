"""
agents/graph/utils.py
─────────────────────
Shared utility functions for the agent graph layer.
"""

from __future__ import annotations

from typing import Any


def normalize_content(content: Any) -> str:
    """Normalise AIMessage.content which can be a list of content-block dicts
    (common with Gemini models) into a plain string.

    Examples of list-form content from Gemini:
        [{"type": "text", "text": "Hello!", "extras": {...}}]
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text", ""))
            else:
                parts.append(str(part))
        return " ".join(p for p in parts if p)
    return str(content) if content else ""
