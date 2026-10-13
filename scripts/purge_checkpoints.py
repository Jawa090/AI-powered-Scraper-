"""
scripts/purge_checkpoints.py
────────────────────────────
Purge old LangGraph checkpoints older than specified retention days.
Complies with Phase P11.2.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure Backend is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Backend"))

import psycopg
from settings import settings


def purge_checkpoints(older_than_days: int) -> int:
    """Purge checkpoints older than specified retention threshold."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    cutoff_iso = cutoff.isoformat()

    with psycopg.connect(settings.CHECKPOINT_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Delete writes belonging to old checkpoints
            cur.execute(
                """
                DELETE FROM checkpoint_writes
                WHERE checkpoint_id IN (
                    SELECT checkpoint_id FROM checkpoints
                    WHERE (metadata->>'ts')::timestamptz < %s::timestamptz
                );
                """,
                (cutoff_iso,),
            )
            writes_deleted = cur.rowcount

            # Delete old checkpoints
            cur.execute(
                """
                DELETE FROM checkpoints
                WHERE (metadata->>'ts')::timestamptz < %s::timestamptz;
                """,
                (cutoff_iso,),
            )
            checkpoints_deleted = cur.rowcount

    print(
        f"Purged {checkpoints_deleted} checkpoint(s) and {writes_deleted} write(s) "
        f"older than {older_than_days} days (cutoff: {cutoff_iso})."
    )
    return checkpoints_deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge old LangGraph checkpoints from PostgreSQL.")
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=getattr(settings, "CHECKPOINT_RETENTION_DAYS", 30),
        help="Delete checkpoints older than this many days (default: CHECKPOINT_RETENTION_DAYS)",
    )
    args = parser.parse_args()
    purge_checkpoints(args.older_than_days)


if __name__ == "__main__":
    main()
