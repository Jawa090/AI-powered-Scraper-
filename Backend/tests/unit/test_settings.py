"""
Backend/tests/unit/test_settings.py — Unit tests for Settings configuration validation.
Complies with P1.1.
"""
import pytest
from Backend.settings import Settings, ConfigError


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
    assert s.AUTO_SCRAPE is False
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
