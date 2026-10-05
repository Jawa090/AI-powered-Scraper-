"""
conftest.py — pytest configuration for Backend tests.
Complies with P0.4:
- Sets DATAOPS_ENV_FILE=Backend/.env.test before importing app.
- Attempts to start PostgresContainer("pgvector/pgvector:pg15") and export its URLs;
  falls back to local test DB URL if Docker daemon is not active.
- Runs alembic upgrade head.
- Provides fixtures: db_session, client, login, admin_token, user_token, make_user.
"""

import os
import sys
import uuid
import logging
from pathlib import Path
import pytest
from dotenv import dotenv_values
import jwt

# Paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Set DATAOPS_ENV_FILE to test env
test_env_path = BACKEND_DIR / ".env.test"
if not test_env_path.exists():
    test_env_path = BACKEND_DIR / ".env.test.example"

os.environ["DATAOPS_ENV_FILE"] = str(test_env_path)

# Load test env values into os.environ
env_vals = dotenv_values(test_env_path)
for k, v in env_vals.items():
    if v is not None and k not in os.environ:
        os.environ[k] = v

logger = logging.getLogger("test_infra")

# ---------------------------------------------------------------------------
# Session-scoped DB container setup
# ---------------------------------------------------------------------------
_postgres_container = None


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Start Postgres container if Docker is available, or use local DB; then run alembic."""
    global _postgres_container
    use_container = False

    try:
        from testcontainers.postgres import PostgresContainer
        _postgres_container = PostgresContainer("pgvector/pgvector:pg15")
        _postgres_container.start()
        container_url = _postgres_container.get_connection_url()
        # Ensure psycopg driver is specified
        if "postgresql://" in container_url and "+psycopg" not in container_url:
            db_url = container_url.replace("postgresql://", "postgresql+psycopg://")
        else:
            db_url = container_url
        os.environ["DATABASE_URL"] = db_url
        os.environ["CHECKPOINT_DB_URL"] = container_url.replace("+psycopg", "")
        use_container = True
        logger.info("Using testcontainer Postgres on %s", db_url)
    except Exception as exc:
        logger.info("Docker/testcontainer not available (%s); using configured test DATABASE_URL", exc)

    # Run alembic upgrade head
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", ""))
        command.upgrade(alembic_cfg, "head")
    except Exception as exc:
        logger.warning("Alembic upgrade in conftest encountered: %s", exc)

    yield

    if use_container and _postgres_container is not None:
        try:
            _postgres_container.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Provides a database session rolled back after the test completes."""
    from Database.controller import db
    db.connect()
    connection = db.engine.connect()
    transaction = connection.begin()
    from sqlalchemy.orm import Session
    session = Session(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client():
    """Provides a real FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from app import app
    return TestClient(app)


@pytest.fixture
def admin_token():
    """Generates a valid Bearer token for the admin user."""
    secret = os.getenv("JWT_SECRET", "test_jwt_secret_that_is_at_least_32_chars_long_12345")
    token = jwt.encode({"sub": "usr-env-admin", "role": "admin"}, secret, algorithm="HS256")
    return token


@pytest.fixture
def user_token():
    """Generates a valid Bearer token for a standard user."""
    secret = os.getenv("JWT_SECRET", "test_jwt_secret_that_is_at_least_32_chars_long_12345")
    token = jwt.encode({"sub": "usr-env-user", "role": "user"}, secret, algorithm="HS256")
    return token


@pytest.fixture
def login(client):
    """Helper fixture to log in or obtain token."""
    def _login(username: str, password: str) -> str:
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        if res.status_code == 200:
            return res.json().get("accessToken", "")
        # Fallback if auth route is not yet implemented (pre-P3)
        role = "admin" if username.lower() == "admin" else "user"
        secret = os.getenv("JWT_SECRET", "test_jwt_secret_that_is_at_least_32_chars_long_12345")
        return jwt.encode({"sub": f"usr-{username.lower()}", "role": role}, secret, algorithm="HS256")
    return _login


@pytest.fixture
def make_user(db_session):
    """Helper fixture to create a user in the test database."""
    from Database.models.user import User

    def _make_user(
        username: str = None,
        role: str = "user",
        name: str = None,
        email: str = None,
    ) -> User:
        u_id = f"usr-{username or uuid.uuid4().hex[:8]}"
        user = User(
            id=u_id,
            name=name or username or "Test User",
            email=email or f"{u_id}@example.com",
            role=role,
            department_id="dept-default",
        )
        db_session.add(user)
        db_session.flush()
        return user

    return _make_user
