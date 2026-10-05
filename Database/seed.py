"""
Database Package - Seed Script
───────────────────────────────
Seeds the reference rows the runtime depends on.
"""

from __future__ import annotations

import os
import sys

try:
    import _paths
except ImportError:
    from Backend import _paths

from settings import settings

from sqlalchemy import text
from Database.controller import session_scope
from services.auth import sync_env_users
from execution.registry import SCRIPTS_REGISTRY

def sync_sources(session) -> None:
    added = 0
    for s in SCRIPTS_REGISTRY:
        capabilities_json = s["capabilities"]
        result = session.execute(
            text(
                "INSERT INTO sources (id, name, code, version, category, script_file, "
                "status, description, capabilities, default_limit, success_rate, "
                "created_at, updated_at) "
                "VALUES (:id, :name, :code, :version, :category, :script_file, "
                ":status, :description, :capabilities, :default_limit, :success_rate, "
                "NOW(), NOW()) "
                "ON CONFLICT (id) DO UPDATE SET "
                "name=EXCLUDED.name, code=EXCLUDED.code, version=EXCLUDED.version, "
                "category=EXCLUDED.category, script_file=EXCLUDED.script_file, "
                "status=EXCLUDED.status, description=EXCLUDED.description, "
                "capabilities=EXCLUDED.capabilities, default_limit=EXCLUDED.default_limit, "
                "success_rate=EXCLUDED.success_rate"
            ),
            {
                "id": s["id"],
                "name": s["name"],
                "code": s["id"].upper(),
                "version": s["version"],
                "category": s["category"],
                "script_file": s["file"],
                "status": s["status"],
                "description": s["description"],
                "capabilities": repr(capabilities_json).replace("'", '"'), # Or properly use json dumps if needed
                "default_limit": s["defaultLimit"],
                "success_rate": s["successRate"],
            }
        )
        if result.rowcount:
            added += 1
    print(f"sources      upserted {added}")

def seed() -> None:
    """Seed all reference data."""
    with session_scope() as session:
        sync_env_users(session)
        
        # We need a dept-default for env users, the migration already inserts it, 
        # but let's be sure it's there via sync_env_users or manual insert
        session.execute(text("INSERT INTO departments (id, name, code, created_at, updated_at) VALUES ('dept-default', 'Default', 'DEFAULT', NOW(), NOW()) ON CONFLICT (id) DO NOTHING"))
        
        import json
        
        # Sources
        added = 0
        for s in SCRIPTS_REGISTRY:
            result = session.execute(
                text(
                    "INSERT INTO sources (id, name, code, version, category, script_file, "
                    "status, description, capabilities, default_limit, success_rate, "
                    "created_at, updated_at) "
                    "VALUES (:id, :name, :code, :version, :category, :script_file, "
                    ":status, :description, :capabilities, :default_limit, :success_rate, "
                    "NOW(), NOW()) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "name=EXCLUDED.name, code=EXCLUDED.code, version=EXCLUDED.version, "
                    "category=EXCLUDED.category, script_file=EXCLUDED.script_file, "
                    "status=EXCLUDED.status, description=EXCLUDED.description, "
                    "capabilities=EXCLUDED.capabilities, default_limit=EXCLUDED.default_limit, "
                    "success_rate=EXCLUDED.success_rate"
                ),
                {
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
            )
            if result.rowcount:
                added += 1
        print(f"sources      upserted {added}")

if __name__ == "__main__":
    seed()
