"""
Backend/tests/unit/test_settings.py — Unit tests for Settings configuration validation.
Complies with P1.1.
"""
import pytest

from Backend.settings import ConfigError, Settings


def get_valid_config() -> dict:
    """Returns a complete, valid configuration dictionary."""
    return {
        "DATABASE_URL": "postgresql+psycopg://postgres:1234@localhost:5432/dataops",
        "CHECKPOINT_DB_URL": "postgresql://postgres:1234@localhost:5432/dataops",
        "ENVIRONMENT": "development",
        "LOG_LEVEL": "INFO",
        "CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
        "API_HOST": "0.0.0.0",
        "API_PORT": "8000",
        "AUTH_ADMIN_USERNAME": "Admin",
        "AUTH_ADMIN_PASSWORD": "AdminPassword123",
        "AUTH_USER_USERNAME": "User123",
        "AUTH_USER_PASSWORD": "UserPassword123",
        "JWT_SECRET": "a_very_secret_key_that_is_at_least_32_characters_long",
        "JWT_EXPIRE_HOURS": "12",
        "LLM_PROVIDER": "gemini",
        "LLM_MODEL": "gemini-3.8-flash",
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "",
        "LLM_THINKING_LEVEL": "high",
        "LLM_TIMEOUT_S": "60",
        "LLM_MAX_RETRIES": "1",
        "AUTO_SCRAPE": "false",
        "MAX_TOOL_STEPS": "6",
        "RECURSION_LIMIT": "25",
        "HISTORY_TOKEN_BUDGET": "6000",
        "SUMMARY_TRIGGER_MESSAGES": "30",
        "SCRAPES_PER_HOUR": "10",
        "FRESHNESS_DAYS": "30",
        "LANGGRAPH_STRICT_MSGPACK": "true",
        "RAG_SERVICE_URL": "",
        "RAG_SERVICE_TOKEN": "",
        "RAG_TIMEOUT_S": "10",
        "RAG_TOP_K": "5",
        "NYSCR_USERNAME": "testuser",
        "NYSCR_PASSWORD": "testpass",
        "SELENIUM_MODE": "local",
        "SELENIUM_REMOTE_URL": "",
        "SCRAPER_MODE": "live",
        "WORKER_POLL_SECONDS": "2",
        "JOB_STALE_SECONDS": "300",
        "CAPTCHA_WAIT_SECONDS": "300",
        "CHECKPOINT_RETENTION_DAYS": "30",
        "SENTRY_DSN": "",
        "SENTRY_TRACES_SAMPLE_RATE": "0.1",
    }


@pytest.mark.unit
def test_valid_settings_succeeds():
    cfg = get_valid_config()
    s = Settings(cfg)
    assert s.DATABASE_URL == "postgresql+psycopg://postgres:1234@localhost:5432/dataops"
    assert s.API_PORT == 8000
    assert not hasattr(s, 'AUTO_SCRAPE')
    assert s.JWT_EXPIRE_HOURS == 8
    assert s.LANGGRAPH_STRICT_MSGPACK is True
    assert len(s.CORS_ORIGINS) == 2


@pytest.mark.unit
def test_missing_database_url():
    cfg = get_valid_config()
    cfg["DATABASE_URL"] = ""
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "DATABASE_URL" in str(exc_info.value)


@pytest.mark.unit
def test_wrong_type_port():
    cfg = get_valid_config()
    cfg["API_PORT"] = "not_a_number"
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "API_PORT" in str(exc_info.value)


@pytest.mark.unit
def test_openai_compatible_requires_base_url():
    cfg = get_valid_config()
    cfg["LLM_PROVIDER"] = "openai_compatible"
    cfg["LLM_BASE_URL"] = ""
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "LLM_BASE_URL: required when LLM_PROVIDER is 'openai_compatible'" in str(exc_info.value)


@pytest.mark.unit
def test_remote_selenium_requires_url():
    cfg = get_valid_config()
    cfg["SELENIUM_MODE"] = "remote"
    cfg["SELENIUM_REMOTE_URL"] = ""
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "SELENIUM_REMOTE_URL: required when SELENIUM_MODE is 'remote'" in str(exc_info.value)


@pytest.mark.unit
def test_scraper_mode_fixture_outside_test_fails():
    cfg = get_valid_config()
    cfg["ENVIRONMENT"] = "development"
    cfg["SCRAPER_MODE"] = "fixture"
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "SCRAPER_MODE: 'fixture' mode is only allowed when ENVIRONMENT='test'" in str(exc_info.value)


@pytest.mark.unit
def test_rag_url_requires_token():
    cfg = get_valid_config()
    cfg["RAG_SERVICE_URL"] = "http://rag-service:8001"
    cfg["RAG_SERVICE_TOKEN"] = ""
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "RAG_SERVICE_TOKEN: required when RAG_SERVICE_URL is set" in str(exc_info.value)


@pytest.mark.unit
def test_jwt_secret_too_short():
    cfg = get_valid_config()
    cfg["JWT_SECRET"] = "short_secret_under_32_chars"
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "JWT_SECRET" in str(exc_info.value)


@pytest.mark.unit
def test_identical_admin_and_user_usernames():
    cfg = get_valid_config()
    cfg["AUTH_ADMIN_USERNAME"] = "AdminUser"
    cfg["AUTH_USER_USERNAME"] = "adminuser"
    with pytest.raises(ConfigError) as exc_info:
        Settings(cfg)
    assert "must differ" in str(exc_info.value)


@pytest.mark.unit
def test_nyscr_credentials_loaded_and_aliased():
    cfg = get_valid_config()
    cfg["NYSCR_USERNAME"] = "testuser"
    cfg["NYSCR_PASSWORD"] = "testpass"
    cfg["NYSCR_USERNAME_2"] = "seconduser"
    cfg["NYSCR_PASSWORD_2"] = "secondpass"
    s = Settings(cfg)
    assert s.NYSCR_USERNAME == "testuser"
    assert s.NYSCR_PASSWORD == "testpass"
    assert s.ny_USERNAME == "testuser"
    assert s.ny_PASSWORD == "testpass"
    assert s.NYSCR_USERNAME_2 == "seconduser"
    assert s.NYSCR_PASSWORD_2 == "secondpass"
    assert s.ny_USERNAME_2 == "seconduser"
    assert s.ny_PASSWORD_2 == "secondpass"


@pytest.mark.unit
def test_nyscr_credentials_fallback_to_secondary():
    cfg = get_valid_config()
    cfg["NYSCR_USERNAME"] = ""
    cfg["NYSCR_PASSWORD"] = ""
    cfg["NYSCR_USERNAME_2"] = "fallbackuser"
    cfg["NYSCR_PASSWORD_2"] = "fallbackpass"
    s = Settings(cfg)
    assert s.NYSCR_USERNAME == "fallbackuser"
    assert s.NYSCR_PASSWORD == "fallbackpass"


@pytest.mark.unit
def test_db_connection_info_extracted_from_database_url():
    cfg = get_valid_config()
    cfg["DATABASE_URL"] = "postgresql+psycopg://myuser:mypass@myhost:5433/mydb"
    cfg["CHECKPOINT_DB_URL"] = "postgresql://myuser:mypass@myhost:5433/mydb"
    s = Settings(cfg)
    assert s.DB_USER == "myuser"
    assert s.DB_PASSWORD == "mypass"
    assert s.DB_HOST == "myhost"
    assert s.DB_PORT == 5433
    assert s.DB_NAME == "mydb"


@pytest.mark.unit
def test_db_url_constructed_from_components():
    cfg = get_valid_config()
    cfg["DATABASE_URL"] = ""
    cfg["CHECKPOINT_DB_URL"] = ""
    cfg["DB_USER"] = "postgres"
    cfg["DB_PASSWORD"] = "secret123"
    cfg["DB_HOST"] = "localhost"
    cfg["DB_PORT"] = "5432"
    cfg["DB_NAME"] = "dataops"
    s = Settings(cfg)
    assert s.DATABASE_URL == "postgresql+psycopg://postgres:secret123@localhost:5432/dataops"
    assert s.CHECKPOINT_DB_URL == "postgresql://postgres:secret123@localhost:5432/dataops"
    assert s.DB_USER == "postgres"
    assert s.DB_PASSWORD == "secret123"
    assert s.POSTGRES_USER == "postgres"
    assert s.POSTGRES_PASSWORD == "secret123"
    assert s.POSTGRES_DB == "dataops"


@pytest.mark.unit
def test_db_url_constructed_from_postgres_prefixed_components():
    cfg = get_valid_config()
    cfg["DATABASE_URL"] = ""
    cfg["CHECKPOINT_DB_URL"] = ""
    cfg["POSTGRES_USER"] = "pguser"
    cfg["POSTGRES_PASSWORD"] = "pgpass"
    cfg["POSTGRES_DB"] = "pgdatabase"
    s = Settings(cfg)
    assert s.DATABASE_URL == "postgresql+psycopg://pguser:pgpass@localhost:5432/pgdatabase"
    assert s.CHECKPOINT_DB_URL == "postgresql://pguser:pgpass@localhost:5432/pgdatabase"
    assert s.DB_USER == "pguser"
    assert s.DB_PASSWORD == "pgpass"
    assert s.DB_NAME == "pgdatabase"


@pytest.mark.unit
def test_db_url_construction_escapes_special_characters():
    cfg = get_valid_config()
    cfg["DATABASE_URL"] = ""
    cfg["CHECKPOINT_DB_URL"] = ""
    cfg["DB_USER"] = "admin"
    cfg["DB_PASSWORD"] = "p@ss#word!123"
    cfg["DB_HOST"] = "db.internal"
    cfg["DB_PORT"] = "5432"
    cfg["DB_NAME"] = "app_db"
    s = Settings(cfg)
    assert s.DATABASE_URL == "postgresql+psycopg://admin:p%40ss%23word%21123@db.internal:5432/app_db"
    assert s.CHECKPOINT_DB_URL == "postgresql://admin:p%40ss%23word%21123@db.internal:5432/app_db"
    assert s.DB_PASSWORD == "p@ss#word!123"


@pytest.mark.unit
def test_ny_prefixed_credentials_fallback():
    cfg = get_valid_config()
    cfg["NYSCR_USERNAME"] = ""
    cfg["NYSCR_PASSWORD"] = ""
    cfg["ny_USERNAME"] = "ny_user"
    cfg["ny_PASSWORD"] = "ny_pass"
    s = Settings(cfg)
    assert s.NYSCR_USERNAME == "ny_user"
    assert s.NYSCR_PASSWORD == "ny_pass"
    assert s.ny_USERNAME == "ny_user"
    assert s.ny_PASSWORD == "ny_pass"


@pytest.mark.unit
def test_load_settings_prioritizes_root_env(monkeypatch, tmp_path):
    import Backend.settings as s_mod
    backend_dir = tmp_path / "Backend"
    backend_dir.mkdir()
    
    # Base example config so required fields are present
    base_lines = [f"{k}={v}" for k, v in get_valid_config().items()]
    example_text = "\n".join(base_lines) + "\n"
    (backend_dir / ".env.example").write_text(example_text, encoding="utf-8")

    root_env = tmp_path / ".env"
    root_env.write_text(
        "DATABASE_URL=postgresql+psycopg://rootusr:rootpass@localhost:5432/rootdb\n"
        "NYSCR_USERNAME=RootUser\n"
        "NYSCR_PASSWORD=RootPassword123\n",
        encoding="utf-8"
    )
    backend_env = backend_dir / ".env"
    backend_env.write_text(
        "DATABASE_URL=postgresql+psycopg://backendusr:backendpass@localhost:5432/backenddb\n"
        "NYSCR_USERNAME=BackendUser\n"
        "NYSCR_PASSWORD=BackendPassword123\n",
        encoding="utf-8"
    )
    monkeypatch.setattr(s_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(s_mod, "BACKEND_DIR", backend_dir)
    monkeypatch.delenv("DATAOPS_ENV_FILE", raising=False)
    monkeypatch.delenv("NYSCR_USERNAME", raising=False)
    monkeypatch.delenv("NYSCR_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    s = s_mod.load_settings()
    assert s.NYSCR_USERNAME == "RootUser"
    assert s.NYSCR_PASSWORD == "RootPassword123"
    assert "rootdb" in s.DATABASE_URL
