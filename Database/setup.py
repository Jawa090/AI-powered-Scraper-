"""
Database Package - Setup Script
────────────────────────────────
Automated Database Setup for DataOps AI Platform:
1. Connects to PostgreSQL server and creates target database if it doesn't exist.
2. Applies all Alembic migrations (`alembic upgrade head`).
3. Seeds initial reference data (departments, users, agents, sources).

Usage (from project root):
    python -m Database.setup
"""
import sys
from pathlib import Path
from urllib.parse import urlparse

DATABASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DATABASE_DIR.parent

try:
    import _paths
except ImportError:
    from Backend import _paths

from settings import settings
import psycopg
from alembic.config import Config
from alembic import command
from Database.seed import seed

clean_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
parsed = urlparse(clean_url)

user = parsed.username
if not user:
    raise ValueError("DATABASE_URL is missing username component")
password = parsed.password or ""
host = parsed.hostname
if not host:
    raise ValueError("DATABASE_URL is missing host component")
port = parsed.port
if not port:
    raise ValueError("DATABASE_URL is missing port component")
target_db = parsed.path.lstrip("/")
if not target_db:
    raise ValueError("DATABASE_URL is missing database name component")

print("=" * 60)
print("  DataOps AI Database Setup")
print(f"  Host: {host}:{port} | User: {user} | Database: {target_db}")
print("=" * 60)

# Step 1: Connect to maintenance database 'postgres' to create the target database
print("\n[Step 1/3] Ensuring database exists...")
maintenance_url = f"postgresql://{user}:{password}@{host}:{port}/postgres"

try:
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if not cur.fetchone():
                print(f"  Creating database '{target_db}'...")
                cur.execute(f'CREATE DATABASE "{target_db}"')
                print(f"  [OK] Database '{target_db}' created successfully.")
            else:
                print(f"  [OK] Database '{target_db}' already exists.")
except Exception as e:
    print(f"  [ERROR] Error connecting to PostgreSQL: {e}")
    print("\nPlease verify:")
    print("  1. PostgreSQL service is running.")
    print("  2. Username and password in Backend/.env are correct.")
    sys.exit(1)

# Step 2: Run Alembic migrations
print("\n[Step 2/3] Running database migrations (alembic upgrade head)...")
try:
    alembic_cfg = Config(str(PROJECT_ROOT / "Backend" / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "Backend" / "migrations"))
    command.upgrade(alembic_cfg, "head")
    print("  [OK] Database schema migrations applied successfully.")
except Exception as e:
    print(f"  [ERROR] Error applying migrations: {e}")
    sys.exit(1)

# Step 3: Setup LangGraph checkpointer tables
print("\n[Step 3/4] Initializing LangGraph checkpointer tables...")
try:
    from agents.graph.checkpointer import setup_checkpointer
    setup_checkpointer()
    print("  [OK] LangGraph checkpointer tables initialized successfully.")
except Exception as e:
    print(f"  [WARNING] LangGraph checkpointer setup skipped or failed: {e}")

# Step 4: Seed initial data
print("\n[Step 4/4] Seeding initial data (departments, users, agents, sources)...")
try:
    seed()
    print("  [OK] Initial reference data seeded successfully.")
except Exception as e:
    print(f"  [ERROR] Error during seeding: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("  Setup complete! You can now start the server with:")
print("     python run_server.py")
print("=" * 60)
