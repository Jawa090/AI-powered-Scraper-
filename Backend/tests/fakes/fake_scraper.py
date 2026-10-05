"""Fake scraper implementation for offline testing."""
import json
from pathlib import Path
from typing import Iterator, Dict, Any

FIXTURES_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "fake" / "records.json"


class FakeScraper:
    """Yields mock records from fixtures for offline tests."""

    def __init__(self, ctx=None):
        self.ctx = ctx
        self.is_closed = False

    def scrape(self, params: Dict[str, Any] = None) -> Iterator[Dict[str, Any]]:
        if not FIXTURES_PATH.exists():
            return
        data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
        limit = (params or {}).get("limit", len(data))
        for item in data[:limit]:
            if self.ctx and hasattr(self.ctx, "should_cancel") and self.ctx.should_cancel():
                break
            yield item

    def to_standard(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw

    def close(self):
        self.is_closed = True
