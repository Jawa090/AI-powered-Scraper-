"""
Database Package - Seed Script
───────────────────────────────
Seeds the reference rows the runtime depends on (departments, users, agents,
sources). Without them, chat sessions and jobs fail with foreign-key errors
on a fresh database.

Idempotent: existing rows are left untouched (ON CONFLICT DO NOTHING).

Usage (from project root, after `alembic upgrade head`):
    python -m Database.seed
"""

from __future__ import annotations

import os
import sys
import json

try:
    import _paths
except ImportError:
    from Backend import _paths

from settings import settings

from sqlalchemy import text
from Database.controller import db
from execution.registry import SCRIPTS_REGISTRY

# IDs mirror the frontend mocks (AI Powered/src/mock/*.ts) and the defaults
# hard-coded in agents/orchestrator.py and scraper_manager.py.
DEPARTMENTS = [
    {"id": "dept-sales-1", "name": "Procurement & Municipal Bids", "code": "PB"},
    {"id": "dept-sales-2", "name": "State Infrastructure & Construction", "code": "IC"},
    {"id": "dept-email-mktg", "name": "Commercial Directory Outreach", "code": "CD"},
    {"id": "dept-research", "name": "State Contracts & Regulatory", "code": "SC"},
    {"id": "dept-biz-dev", "name": "Business Development & Operations", "code": "BD"},
]

USERS = [
    {"id": "usr-ahmed", "email": "ahmed.khan@company.internal", "name": "Ahmed Khan",
     "role": "sales", "role_title": "Senior Outbound Sales Specialist", "department_id": "dept-sales-1"},
    {"id": "usr-sara", "email": "sara.j@company.internal", "name": "Sara Jenkins",
     "role": "email", "role_title": "Email Growth & Campaigns Lead", "department_id": "dept-email-mktg"},
    {"id": "usr-marcus", "email": "marcus.v@company.internal", "name": "Marcus Vance",
     "role": "manager", "role_title": "Director of State RFPs & Infrastructure", "department_id": "dept-sales-2"},
    {"id": "usr-elena", "email": "elena.r@company.internal", "name": "Elena Rostova",
     "role": "admin", "role_title": "Head of Enterprise Intelligence (Admin)", "department_id": "dept-research"},
]

AGENTS = [
    {"id": "agent-sales-1", "department_id": "dept-sales-1",
     "name": "Dallas Bonfire Intelligence Agent", "code": "AGT-BONFIRE"},
    {"id": "agent-sales-2", "department_id": "dept-sales-2",
     "name": "DASNY RFP & Construction Scout", "code": "AGT-DASNY"},
    {"id": "agent-email-mktg", "department_id": "dept-email-mktg",
     "name": "JWiz Commercial Directory Harvester", "code": "AGT-JWIZ"},
    {"id": "agent-research", "department_id": "dept-research",
     "name": "NYSCR State Contract Reporter Agent", "code": "AGT-NYSCR"},
    {"id": "agent-master", "department_id": "dept-biz-dev",
     "name": "DataOps Master Orchestrator", "code": "AGT-ORCH"},
]


def _source_rows():
    for s in SCRIPTS_REGISTRY:
        yield {
            "id": s["id"],
            "name": s["name"],
            "code": s["id"].upper(),
            "version": s["version"],
            "category": s["category"],
            "script_file": s["file"],
            "status": s["status"],
            "description": s["description"],
            "capabilities": json.dumps(s["capabilities"]),
            "default_limit": s["defaultLimit"],
            "success_rate": s["successRate"],
        }


def seed() -> None:
    """Seed all reference data. Idempotent via ON CONFLICT DO NOTHING."""

    with db.transaction() as session:
        # DEPARTMENTS
        added = 0
        for row in DEPARTMENTS:
            result = session.execute(
                text(
                    "INSERT INTO departments (id, name, code, created_at, updated_at) "
                    "VALUES (:id, :name, :code, NOW(), NOW()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": row["id"], "name": row["name"], "code": row["code"]},
            )
            if result.rowcount:
                added += 1
        print(f"departments  +{added} (of {len(DEPARTMENTS)})")

        # USERS
        added = 0
        for row in USERS:
            result = session.execute(
                text(
                    "INSERT INTO users (id, email, name, role, role_title, department_id, created_at, updated_at) "
                    "VALUES (:id, :email, :name, :role, :role_title, :department_id, NOW(), NOW()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                row,
            )
            if result.rowcount:
                added += 1
        print(f"users        +{added} (of {len(USERS)})")

        # AGENTS
        added = 0
        for row in AGENTS:
            result = session.execute(
                text(
                    "INSERT INTO agents (id, department_id, name, code, created_at, updated_at) "
                    "VALUES (:id, :department_id, :name, :code, NOW(), NOW()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                row,
            )
            if result.rowcount:
                added += 1
        print(f"agents       +{added} (of {len(AGENTS)})")

        # SOURCES
        sources = list(_source_rows())
        added = 0
        for row in sources:
            result = session.execute(
                text(
                    "INSERT INTO sources (id, name, code, version, category, script_file, "
                    "status, description, capabilities, default_limit, success_rate, "
                    "created_at, updated_at) "
                    "VALUES (:id, :name, :code, :version, :category, :script_file, "
                    ":status, :description, :capabilities, :default_limit, :success_rate, "
                    "NOW(), NOW()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                row,
            )
            if result.rowcount:
                added += 1
        print(f"sources      +{added} (of {len(sources)})")


if __name__ == "__main__":
    seed()
