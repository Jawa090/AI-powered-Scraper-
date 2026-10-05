"""
RAG Migration Script
Applies Alembic migrations for schema 'rag'.
Usage: python -m RAG.migrate
"""
import os
import sys
from pathlib import Path


def run_migrations():
    print("=" * 60)
    print("  RAG Schema Migration (Schema: rag)")
    print("=" * 60)
    rag_dir = Path(__file__).resolve().parent
    alembic_ini = rag_dir / "alembic.ini"
    
    if alembic_ini.exists():
        try:
            from alembic.config import Config
            from alembic import command
            cfg = Config(str(alembic_ini))
            # Set script location dynamically to resolve absolute path
            cfg.set_main_option("script_location", str(rag_dir / "alembic"))
            command.upgrade(cfg, "head")
            print("  [OK] RAG migrations applied successfully.")
        except Exception as e:
            print(f"  [ERROR] Error applying RAG migrations: {e}")
            sys.exit(1)
    else:
        print(f"  [ERROR] alembic.ini not found at {alembic_ini}")
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
