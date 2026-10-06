"""
scripts/merge_duplicates.py
───────────────────────────
Merge duplicate organizations and leads by their deduplication keys.
Implements Phase P4.3:
- Group by dedup_key / identity_key; the survivor is the oldest (by created_at, then id).
- Re-point FKs: leads, contacts, emails, phones, locations, dataset_records, query_results, lead_sources, agent_actions.
- Delete the losers.
- Write merge_log.csv.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "Backend"))

import _paths
from Database.controller import engine, session_scope
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("merge_duplicates")


def merge_duplicates(*, dry_run: bool = True, log_path: str = "merge_log.csv") -> int:
    logger.info("Starting duplicate merge (dry_run=%s)", dry_run)
    merge_entries: List[Dict[str, Any]] = []

    counts = {
        "org_groups": 0,
        "org_losers_merged": 0,
        "lead_groups": 0,
        "lead_losers_merged": 0,
        "fks_repointed": 0,
    }

    with session_scope() as session:
        # -------------------------------------------------------------
        # 1. Merge Duplicate Organizations (by dedup_key)
        # -------------------------------------------------------------
        org_dups = session.execute(text("""
            SELECT dedup_key, COUNT(*)
            FROM organizations
            WHERE dedup_key IS NOT NULL AND dedup_key != ''
            GROUP BY dedup_key
            HAVING COUNT(*) > 1
        """)).fetchall()

        counts["org_groups"] = len(org_dups)
        logger.info("Found %d duplicate organization groups", len(org_dups))

        for dedup_key, _ in org_dups:
            orgs = session.execute(text("""
                SELECT id, name, created_at
                FROM organizations
                WHERE dedup_key = :key
                ORDER BY created_at ASC NULLS LAST, id ASC
            """), {"key": dedup_key}).fetchall()

            if len(orgs) <= 1:
                continue

            survivor = orgs[0]
            survivor_id = survivor[0]
            survivor_name = survivor[1]

            for loser in orgs[1:]:
                loser_id = loser[0]
                loser_name = loser[1]
                counts["org_losers_merged"] += 1

                merge_entries.append({
                    "entity_type": "organization",
                    "dedup_key": dedup_key,
                    "survivor_id": survivor_id,
                    "survivor_name": survivor_name,
                    "loser_id": loser_id,
                    "loser_name": loser_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                # Re-point foreign keys
                # leads
                r = session.execute(text("""
                    UPDATE leads SET organization_id = :survivor_id
                    WHERE organization_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # contacts
                r = session.execute(text("""
                    UPDATE contacts SET organization_id = :survivor_id
                    WHERE organization_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # emails
                r = session.execute(text("""
                    UPDATE emails SET organization_id = :survivor_id
                    WHERE organization_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # phones
                r = session.execute(text("""
                    UPDATE phones SET organization_id = :survivor_id
                    WHERE organization_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # locations
                r = session.execute(text("""
                    UPDATE locations SET organization_id = :survivor_id
                    WHERE organization_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # dataset_records
                r = session.execute(text("""
                    UPDATE dataset_records SET organization_id = :survivor_id
                    WHERE organization_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # Delete loser organization
                session.execute(text("""
                    DELETE FROM organizations WHERE id = :loser_id
                """), {"loser_id": loser_id})

        # -------------------------------------------------------------
        # 2. Merge Duplicate Leads (by identity_key)
        # -------------------------------------------------------------
        lead_dups = session.execute(text("""
            SELECT identity_key, COUNT(*)
            FROM leads
            WHERE identity_key IS NOT NULL AND identity_key != ''
            GROUP BY identity_key
            HAVING COUNT(*) > 1
        """)).fetchall()

        counts["lead_groups"] = len(lead_dups)
        logger.info("Found %d duplicate lead groups", len(lead_dups))

        for identity_key, _ in lead_dups:
            leads = session.execute(text("""
                SELECT id, title, created_at
                FROM leads
                WHERE identity_key = :key
                ORDER BY created_at ASC NULLS LAST, id ASC
            """), {"key": identity_key}).fetchall()

            if len(leads) <= 1:
                continue

            survivor = leads[0]
            survivor_id = survivor[0]
            survivor_title = survivor[1]

            for loser in leads[1:]:
                loser_id = loser[0]
                loser_title = loser[1]
                counts["lead_losers_merged"] += 1

                merge_entries.append({
                    "entity_type": "lead",
                    "dedup_key": identity_key,
                    "survivor_id": survivor_id,
                    "survivor_name": survivor_title,
                    "loser_id": loser_id,
                    "loser_name": loser_title,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                # Re-point dataset_records (handle conflict if survivor already in dataset)
                session.execute(text("""
                    DELETE FROM dataset_records
                    WHERE lead_id = :loser_id
                      AND dataset_id IN (
                          SELECT dataset_id FROM dataset_records WHERE lead_id = :survivor_id
                      )
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                r = session.execute(text("""
                    UPDATE dataset_records SET lead_id = :survivor_id
                    WHERE lead_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # Re-point query_results (handle conflict if survivor already in query)
                session.execute(text("""
                    DELETE FROM query_results
                    WHERE lead_id = :loser_id
                      AND query_id IN (
                          SELECT query_id FROM query_results WHERE lead_id = :survivor_id
                      )
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                r = session.execute(text("""
                    UPDATE query_results SET lead_id = :survivor_id
                    WHERE lead_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # Re-point lead_sources (handle conflict if survivor already has source)
                session.execute(text("""
                    DELETE FROM lead_sources
                    WHERE lead_id = :loser_id
                      AND source_code IN (
                          SELECT source_code FROM lead_sources WHERE lead_id = :survivor_id
                      )
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                r = session.execute(text("""
                    UPDATE lead_sources SET lead_id = :survivor_id
                    WHERE lead_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # Re-point agent_actions
                r = session.execute(text("""
                    UPDATE agent_actions SET lead_id = :survivor_id
                    WHERE lead_id = :loser_id
                """), {"survivor_id": survivor_id, "loser_id": loser_id})
                counts["fks_repointed"] += r.rowcount or 0

                # Delete loser lead
                session.execute(text("""
                    DELETE FROM leads WHERE id = :loser_id
                """), {"loser_id": loser_id})

        # -------------------------------------------------------------
        # 3. Clean duplicate child entities (emails, phones, locations, contacts)
        # to ensure unique constraints can be safely created in c2
        # -------------------------------------------------------------
        # Deduplicate emails by (normalized_email, coalesce(organization_id,''), coalesce(contact_id,''))
        session.execute(text("""
            DELETE FROM emails
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM emails
                GROUP BY normalized_email, COALESCE(organization_id, ''), COALESCE(contact_id, '')
            )
        """))

        # Deduplicate phones by (normalized_phone, coalesce(organization_id,''), coalesce(contact_id,''))
        session.execute(text("""
            DELETE FROM phones
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM phones
                GROUP BY normalized_phone, COALESCE(organization_id, ''), COALESCE(contact_id, '')
            )
        """))

        # Deduplicate contacts by (coalesce(organization_id,''), normalized_full_name)
        session.execute(text("""
            DELETE FROM contacts
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM contacts
                GROUP BY COALESCE(organization_id, ''), normalized_full_name
            )
        """))

        # Deduplicate locations by (organization_id, coalesce(city,''), coalesce(state,''))
        session.execute(text("""
            DELETE FROM locations
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM locations
                GROUP BY organization_id, COALESCE(city, ''), COALESCE(state, '')
            )
        """))

        if dry_run:
            logger.info("DRY-RUN: Rolling back all changes. No database rows modified.")
            session.rollback()
        else:
            session.commit()
            logger.info("APPLY: Successfully committed duplicate merge to database.")

    # Write merge_log.csv
    try:
        csv_file = Path(log_path)
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "entity_type",
                    "dedup_key",
                    "survivor_id",
                    "survivor_name",
                    "loser_id",
                    "loser_name",
                    "timestamp",
                ],
            )
            writer.writeheader()
            for entry in merge_entries:
                writer.writerow(entry)
        logger.info("Wrote %d merge operations to %s", len(merge_entries), log_path)
    except Exception as e:
        logger.error("Failed writing merge_log.csv: %s", e)

    logger.info("=" * 50)
    logger.info("DUPLICATE MERGE SUMMARY:")
    for k, v in counts.items():
        logger.info("  %-25s: %s", k, v)
    logger.info("=" * 50)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate organizations and leads.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--dry-run", dest="dry_run", action="store_true", default=True, help="Simulate merge (default)")
    group.add_argument("--apply", dest="dry_run", action="store_false", help="Commit merge to database")
    parser.add_argument("--log", dest="log_path", default="merge_log.csv", help="Path to merge_log.csv output")

    args = parser.parse_args()
    sys.exit(merge_duplicates(dry_run=args.dry_run, log_path=args.log_path))


if __name__ == "__main__":
    main()
