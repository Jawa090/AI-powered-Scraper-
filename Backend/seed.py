"""
seed.py
───────
Seeds the reference rows the runtime depends on (departments, users, agents,
sources). Without them, chat sessions and jobs fail with foreign-key errors
on a fresh database.

Idempotent: existing rows are left untouched.

Usage (from Backend/, after `alembic upgrade head`):
    python seed.py
"""

from __future__ import annotations

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection import SessionLocal
from database.models.agent import Agent
from database.models.department import Department
from database.models.source import Source
from database.models.user import User
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
            "capabilities": s["capabilities"],
            "default_limit": s["defaultLimit"],
            "success_rate": s["successRate"],
        }


def seed() -> None:
    # Order matters: departments before users/agents (foreign keys).
    plan = [
        (Department, DEPARTMENTS),
        (User, USERS),
        (Agent, AGENTS),
        (Source, list(_source_rows())),
    ]
    with SessionLocal() as db:
        for model, rows in plan:
            added = 0
            for row in rows:
                if db.get(model, row["id"]) is None:
                    db.add(model(**row))
                    added += 1
            db.flush()
            print(f"{model.__tablename__:<12} +{added} (of {len(rows)})")
        db.commit()


if __name__ == "__main__":
    seed()
