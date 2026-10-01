"""
Database Package - Check Script
────────────────────────────────
Database state and route inspection utility.

Usage (from project root):
    python -m Database.check
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Backend"))

from Database import db

print("=== DATABASE TABLE INSPECTION ===")
tables_q = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
tables = db._fetch_all(tables_q)
print(f"Tables in 'public' schema: {[t['table_name'] for t in tables]}")

for table in ["jobs", "leads", "datasets", "scrape_runs", "agent_sessions"]:
    try:
        count = db._fetch_one(f"SELECT COUNT(*) FROM {table}")['count']
        print(f"  {table}: {count} rows")
    except Exception as e:
        print(f"  {table}: ERROR — {e}")

print()
print("=== FASTAPI ROUTES ===")
import app as app_mod
for r in app_mod.app.routes:
    if hasattr(r, "path"):
        methods = getattr(r, "methods", None)
        print(f"  {methods} {r.path}")
