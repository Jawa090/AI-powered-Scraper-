"""Run migrations/seed/tests in an isolated database on the configured PG server."""
import os
import sys
import uuid
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT)]
def main():
    from settings import settings
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    connection = conninfo_to_dict(settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1))
    state_file = ROOT / "docs/audit/integration_database.json"
    if state_file.exists():
        name = json.loads(state_file.read_text())["name"]
    else:
        name = "dataops_implementation_test_" + uuid.uuid4().hex[:10]
        with psycopg.connect(**{**connection, "dbname": "postgres"}, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        state_file.write_text(json.dumps({"name": name}))
    if not name.startswith("dataops_implementation_test_"):
        raise RuntimeError("Refusing to modify a non-test database")
    connection["dbname"] = name
    from sqlalchemy.engine import URL
    url = URL.create("postgresql+psycopg", username=connection.get("user"), password=connection.get("password"),
        host=connection.get("host"), port=int(connection.get("port", 5432)), database=name)
    os.environ.update({"DATABASE_URL": url.render_as_string(hide_password=False), "CHECKPOINT_DB_URL": make_conninfo(**connection),
        "DATAOPS_ENV_FILE": str(ROOT / "Backend/.env.test.example"), "ENVIRONMENT": "test"})
    # Settings requires a URI checkpoint URL, rather than keyword conninfo.
    os.environ["CHECKPOINT_DB_URL"] = url.set(drivername="postgresql").render_as_string(hide_password=False)
    from settings import Settings, _read_env_file
    test_settings = Settings({**_read_env_file(ROOT / "Backend/.env.test.example"),
        "DATABASE_URL": os.environ["DATABASE_URL"], "CHECKPOINT_DB_URL": os.environ["CHECKPOINT_DB_URL"]})
    settings.__dict__.clear()
    settings.__dict__.update(test_settings.__dict__)
    from alembic.config import Config
    from alembic import command
    cfg = Config(str(ROOT / "Backend/alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "Backend/migrations"))
    command.upgrade(cfg, "head")
    from Database.seed import seed
    seed()
    print("Disposable test database migrated and seeded:", name, flush=True)
    if len(sys.argv) > 1:
        # Actual checkpointer tests are initialized against the same isolated database.
        from agents.graph.checkpointer import setup_checkpointer
        setup_checkpointer()
        import pytest
        conftest_args = [] if "--with-conftest" in sys.argv else ["--noconftest"]
        targets = [arg for arg in sys.argv[1:] if arg != "--with-conftest"]
        sys.exit(pytest.main([*conftest_args, "-c", str(ROOT / "Backend/pytest.ini"), "-o", "addopts=", "--tb=short", "-q", *targets]))


if __name__ == '__main__':
    main()
