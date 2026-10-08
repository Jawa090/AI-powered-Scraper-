"""Read-only connection diagnostics, never prints a DSN/password."""
import json
import sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "Backend"), str(Path(__file__).resolve().parents[2])]
import psycopg
from settings import settings
try:
    with psycopg.connect(settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1),
                         connect_timeout=5, options="-c default_transaction_read_only=on") as conn:
        version = conn.execute("SELECT current_setting('server_version')").fetchone()[0]
        tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()
        print(json.dumps({"connected": True, "version": version, "tables": [r[0] for r in tables]}))
except Exception as exc:
    message = str(exc).lower()
    reason = next((word for word in ["password authentication failed", "connection refused", "does not exist", "timeout", "permission denied"] if word in message), "connection unavailable")
    print(json.dumps({"connected": False, "error": type(exc).__name__, "reason": reason}))
