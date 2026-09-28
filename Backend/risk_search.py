"""
Global risk search for Phase 1 production concerns.
Run from Backend/ directory.
"""
import sys
import os
import re

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=== GLOBAL RISK SEARCH: PRODUCTION PATH FILES ===")
print()

all_py = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "migrations", "postman"]]
    for f in files:
        if f.endswith(".py") and not f.startswith("phase1_") and not f.startswith("check_") and not f.startswith("risk_"):
            all_py.append(os.path.join(root, f))

print(f"Auditing {len(all_py)} Python files...")
print()

risks = {
    "TODO": [],
    "FIXME": [],
    "NyscrScraper": [],
    "SCRIPTS_REGISTRY = [": [],
    "jobs.json": [],
    "datasets.json": [],
    "leads.json": [],
    "data/jobs": [],
    "data/datasets": [],
    "data/leads": [],
    "555-": [],
    "555-0": [],
    "example.com": [],
    "rfp-bids@dasny.org": [],
    "procurement@nyscr": [],
    "fallback": [],
}

for filepath in all_py:
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for lineno, line in enumerate(lines, 1):
            lower = line.lower()
            for pattern, hits in risks.items():
                if pattern.lower() in lower:
                    hits.append(f"  {filepath}:{lineno}: {line.rstrip()[:120]}")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")

any_warn = False
for pattern, hits in risks.items():
    if hits:
        filtered = [h for h in hits if "phase1_verify" not in h and "check_db" not in h and "risk_" not in h]
        if filtered:
            any_warn = True
            print(f"[WARN] {repr(pattern)} found in {len(filtered)} location(s):")
            for h in filtered[:5]:
                print(h)
            if len(filtered) > 5:
                print(f"  ... and {len(filtered) - 5} more")
            print()

if not any_warn:
    print("[CLEAN] All checks passed - no production risk patterns found.")
