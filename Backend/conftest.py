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

import _paths
BACKEND_DIR = _paths.BACKEND_DIR
PROJECT_ROOT = _paths.PROJECT_ROOT

# Set DATAOPS_ENV_FILE to test env
test_env_path = Path(os.environ.get("DATAOPS_ENV_FILE", str(BACKEND_DIR / ".env.test")))
if not test_env_path.exists():
    test_env_path = BACKEND_DIR / ".env.test.example"

os.environ.setdefault("DATAOPS_ENV_FILE", str(test_env_path))

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
    """Never run a mutating test suite against a non-test database."""
    from settings import settings
    from sqlalchemy.engine import make_url
    assert settings.ENVIRONMENT == 'test', 'Tests require ENVIRONMENT=test'
    assert 'test' in (make_url(settings.DATABASE_URL).database or '').lower(), 'Refusing non-test database'
    from alembic.config import Config
    from alembic import command
    config = Config(str(BACKEND_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND_DIR / 'migrations'))
    command.upgrade(config, 'head')
    from Database.seed import seed
    seed()
    # The allocated test DB may survive earlier runs with different credentials.
    # Reset only its test accounts; production seeding deliberately preserves them.
    from Database.controller import session_scope
    from Database.models.user import User
    from services.auth import hash_password
    with session_scope() as db:
        for uid, username, password in [
            ('usr-env-admin', settings.AUTH_ADMIN_USERNAME, settings.AUTH_ADMIN_PASSWORD),
            ('usr-env-user', settings.AUTH_USER_USERNAME, settings.AUTH_USER_PASSWORD),
        ]:
            account = db.get(User, uid)
            account.username, account.password_hash, account.status = username, hash_password(password), 'Active'
    from agents.graph.checkpointer import setup_checkpointer
    setup_checkpointer()
    yield

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
    from Database.controller import session_scope
    from Database.models.user import User
    from services.auth import create_access_token
    with session_scope() as db:
        return create_access_token(db.get(User, 'usr-env-admin'))


@pytest.fixture
def user_token():
    """Generates a valid Bearer token for a standard user."""
    from Database.controller import session_scope
    from Database.models.user import User
    from services.auth import create_access_token
    with session_scope() as db:
        return create_access_token(db.get(User, 'usr-env-user'))


@pytest.fixture
def login(client):
    """Helper fixture to log in or obtain token."""
    def _login(username: str, password: str) -> str:
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200, f'Login failed: {res.status_code}'
        return res.json()['accessToken']
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
            username=username or u_id,
            status="Active",
            name=name or username or "Test User",
            email=email or f"{u_id}@example.com",
            role=role,
            department_id="dept-default",
        )
        db_session.add(user)
        db_session.flush()
        return user

    return _make_user
