"""
Database state and route check.
Run from Backend/ directory.
"""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection import SessionLocal
from sqlalchemy import text

print("=== DATABASE TABLE INSPECTION ===")
with SessionLocal() as db:
    tables_q = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
    tables = db.execute(text(tables_q)).fetchall()
    print(f"Tables in 'public' schema: {[t[0] for t in tables]}")

    for table in ["jobs", "leads", "datasets", "scrape_runs", "agent_sessions"]:
        try:
            count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
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
