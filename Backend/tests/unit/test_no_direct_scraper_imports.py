"""
tests/unit/test_no_direct_scraper_imports.py — Modularity test (P17.1)
Ensures no file outside Backend/scrappers/ imports a specific scraper module.
"""
import ast
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent.parent
_backend = _root / "Backend"

ALLOWED_DIRS = {"scrappers", "tests", "fixtures", "fakes"}
ALLOWED_FILES = {"backfill_identity.py"}

SCRAPER_MODULES = {"bonfire", "dasny", "jwiz", "nyscr"}


def _scraper_import_in_file(filepath: Path) -> list:
    """Find imports of specific scraper modules in a Python file."""
    violations = []
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, ValueError):
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            # Check if importing from scrappers.<specific_scraper>
            if len(parts) >= 2 and parts[0] == "scrappers" and parts[1] in SCRAPER_MODULES:
                violations.append(
                    f"{filepath.relative_to(_root)}:{node.lineno} imports scrappers.{parts[1]}"
                )
    return violations


class TestNoDirectScraperImports:
    def test_no_scraper_imports_outside_scrappers_dir(self):
        """Rule 9: Outside Backend/scrappers/, nothing imports a specific scraper module."""
        violations = []
        for pyfile in _backend.rglob("*.py"):
            # Skip allowed directories
            rel_parts = pyfile.relative_to(_backend).parts
            if any(part in ALLOWED_DIRS for part in rel_parts):
                continue
            if pyfile.name in ALLOWED_FILES:
                continue
            violations.extend(_scraper_import_in_file(pyfile))

        assert not violations, "Direct scraper imports found:\n" + "\n".join(violations)
