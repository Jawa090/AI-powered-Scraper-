"""
RAG Migration Script
Applies Alembic migrations or schema initialization for schema 'rag'.
Usage: python -m RAG.migrate
"""
import os
import sys
from pathlib import Path


def run_migrations():
    print("=" * 60)
    print("  RAG Schema Migration")
    print("=" * 60)
    rag_dir = Path(__file__).resolve().parent
    alembic_ini = rag_dir / "alembic.ini"
    if alembic_ini.exists():
        try:
            from alembic.config import Config
            from alembic import command
            cfg = Config(str(alembic_ini))
            command.upgrade(cfg, "head")
            print("  [OK] RAG migrations applied successfully.")
        except Exception as e:
            print(f"  [ERROR] Error applying RAG migrations: {e}")
            sys.exit(1)
    else:
        print("  [INFO] No RAG alembic.ini found; verifying schema initialization...")
        db_url = os.environ.get("RAG_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if db_url:
            clean_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
            try:
                import psycopg
                with psycopg.connect(clean_url, autocommit=True) as conn:
                    with conn.cursor() as cur:
                        cur.execute("CREATE SCHEMA IF NOT EXISTS rag;")
                        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                        print("  [OK] Schema 'rag' and extension 'vector' ensured.")
            except Exception as e:
                print(f"  [WARNING] Unable to connect to DB for RAG schema init: {e}")
        else:
            print("  [INFO] RAG_DATABASE_URL not set; skipping direct schema check.")


if __name__ == "__main__":
    run_migrations()
