"""
scripts/audit_patterns.py — Audits codebase against architecture rules.

Usage:
    python scripts/audit_patterns.py [--only config|db]
"""
import sys
import re
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Patterns for config audit: banned direct os.getenv / load_dotenv outside settings.py
CONFIG_PATTERNS = [
    (r"\bos\.getenv\(", "os.getenv() used directly; use settings.<KEY> instead"),
    (r"\bos\.environ\.get\(", "os.environ.get() used directly; use settings.<KEY> instead"),
    (r"\bload_dotenv\(", "load_dotenv() used directly; use settings instead"),
]

# Patterns for DB audit: banned db singleton usage outside Database/
DB_PATTERNS = [
    (r"\bdb\.session\b", "db.session used directly; use session passed to caller/service"),
    (r"\bdb\.transaction\(", "db.transaction() used directly; manage transactions via session_scope or route"),
    (r"\bfrom\s+Database\s+import\s+db\b", "from Database import db; use get_db or session_scope"),
    (r"\bfrom\s+Database\.repositories\b", "Direct repository import outside Database; use Repositories(session)"),
]

EXCLUDE_DIRS = {"tests", "fixtures", "fakes", "baseline", "history", ".pytest_cache", "__pycache__", "node_modules", ".git", ".venv", "venv", "_unused_scripts"}
EXCLUDE_FILES = {"settings.py", "probe_apis.py", "audit_patterns.py"}


def audit_config():
    hits = []
    scan_dirs = [ROOT / "Backend", ROOT / "Database"]
    compiled = [(re.compile(p), msg) for p, msg in CONFIG_PATTERNS]

    for d in scan_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.name in EXCLUDE_FILES:
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                for i, line in enumerate(lines, 1):
                    # Ignore comment lines
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for reg, msg in compiled:
                        if reg.search(line):
                            hits.append((p.relative_to(ROOT), i, line.strip(), msg))
            except Exception as e:
                print(f"Error reading {p}: {e}", file=sys.stderr)
    return hits


def audit_db():
    hits = []
    scan_dirs = [ROOT / "Backend"]
    compiled = [(re.compile(p), msg) for p, msg in DB_PATTERNS]

    for d in scan_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.name in EXCLUDE_FILES:
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for reg, msg in compiled:
                        if reg.search(line):
                            hits.append((p.relative_to(ROOT), i, line.strip(), msg))
            except Exception as e:
                print(f"Error reading {p}: {e}", file=sys.stderr)
    return hits


def main():
    parser = argparse.ArgumentParser(description="Audit codebase for architectural pattern violations.")
    parser.add_argument("--only", choices=["config", "db"], help="Run only specific audit check.")
    args = parser.parse_args()

    total_hits = 0

    if not args.only or args.only == "config":
        print("=" * 60)
        print("AUDIT: Configuration Patterns (Direct env access)")
        print("=" * 60)
        config_hits = audit_config()
        if config_hits:
            print(f"FAILED: Found {len(config_hits)} violation(s):")
            for path, line_no, line, msg in config_hits:
                print(f"  {path}:{line_no}: {line}  -->  {msg}")
            total_hits += len(config_hits)
        else:
            print("PASSED: 0 violations found.")

    if not args.only or args.only == "db":
        print("=" * 60)
        print("AUDIT: Database Patterns (Singleton / Direct repo access)")
        print("=" * 60)
        db_hits = audit_db()
        if db_hits:
            print(f"FAILED: Found {len(db_hits)} violation(s):")
            for path, line_no, line, msg in db_hits:
                print(f"  {path}:{line_no}: {line}  -->  {msg}")
            total_hits += len(db_hits)
        else:
            print("PASSED: 0 violations found.")

    sys.exit(1 if total_hits > 0 else 0)


if __name__ == "__main__":
    main()
