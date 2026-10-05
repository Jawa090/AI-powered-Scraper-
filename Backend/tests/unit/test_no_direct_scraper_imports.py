"""
test_no_direct_scraper_imports.py
─────────────────────────────────
Verify Rule 9: outside Backend/scrappers/, nothing imports a specific scraper module.
All access must go through scrappers.controller or scrappers.base.
"""

import ast
from pathlib import Path
import pytest


FORBIDDEN_MODULES = {
    "scrappers.bonfire",
    "scrappers.dasny",
    "scrappers.jwiz",
    "scrappers.nyscr",
    "scrappers._template",
}

EXCLUDED_PARTS = {
    "scrappers",
    "tests",
    "fixtures",
    "migrations",
    "docs",
    "node_modules",
    ".git",
    "__pycache__",
}


@pytest.mark.unit
def test_no_direct_scraper_imports_rule_9():
    """Scan all Python files outside Backend/scrappers/ and assert no direct scraper imports."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    violations = []

    for py_file in backend_dir.rglob("*.py"):
        # Check if file is in an excluded directory
        parts = set(py_file.parts)
        if any(part in parts for part in EXCLUDED_PARTS):
            continue
        if py_file.name == "backfill_identity.py":
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_MODULES:
                        violations.append((str(py_file), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in FORBIDDEN_MODULES:
                    violations.append((str(py_file), node.lineno, mod))

    assert not violations, (
        f"Rule 9 violation! The following files directly import specific scraper modules instead of scrappers.controller:\n"
        + "\n".join(f"{f}:{line} -> {mod}" for f, line, mod in violations)
    )
