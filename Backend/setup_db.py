"""
setup_db.py
───────────
Automated Database Setup for DataOps AI Platform:
1. Connects to PostgreSQL server and creates the 'dataops' database if it doesn't exist.
2. Applies all Alembic migrations (`alembic upgrade head`).
3. Seeds initial reference data (departments, users, agents, sources).
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Set working directory to Backend/
backend_dir = Path(__file__).resolve().parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=backend_dir / ".env")

import psycopg
from alembic.config import Config
from alembic import command
from seed import seed

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found in .env file.")
    sys.exit(1)

# Extract connection parameters from DATABASE_URL
# Strip driver prefix for psycopg connection if needed
clean_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
parsed = urlparse(clean_url)

user = parsed.username or "postgres"
password = parsed.password or ""
host = parsed.hostname or "localhost"
port = parsed.port or 5432
target_db = (parsed.path or "/dataops").lstrip("/")

print(f"============================================================")
print(f"  DataOps AI Database Setup")
print(f"  Host: {host}:{port} | User: {user} | Database: {target_db}")
print(f"============================================================")

# Step 1: Connect to maintenance database 'postgres' to create the target database
print("\n[Step 1/3] Ensuring database exists...")
maintenance_url = f"postgresql://{user}:{password}@{host}:{port}/postgres"

try:
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if not cur.fetchone():
                print(f"  Creating database '{target_db}'...")
                # Note: database names cannot be parameterized in CREATE DATABASE
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
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("  [OK] Database schema migrations applied successfully.")
except Exception as e:
    print(f"  [ERROR] Error applying migrations: {e}")
    sys.exit(1)

# Step 3: Seed initial data
print("\n[Step 3/3] Seeding initial data (departments, users, agents, sources)...")
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
