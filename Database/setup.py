"""Create the configured database, migrate and seed. Importing does no work."""
from pathlib import Path
try:
    import _paths
except ImportError:
    from Backend import _paths


def setup_database():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    from alembic.config import Config
    from alembic import command
    from settings import settings
    from Database.seed import seed
    url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    connection = conninfo_to_dict(url)
    target = connection.pop("dbname")
    with psycopg.connect(**connection, dbname="postgres", autocommit=True, connect_timeout=5) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "Backend/alembic.ini"))
    cfg.set_main_option("script_location", str(root / "Backend/migrations"))
    command.upgrade(cfg, "head")
    from agents.graph.checkpointer import setup_checkpointer
    setup_checkpointer()
    seed()


if __name__ == "__main__":
    setup_database()
    print("Database migrations and reference seed completed.")
