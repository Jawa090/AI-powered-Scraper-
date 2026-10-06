"""
test_docker_manifests.py
────────────────────────
Unit tests verifying Docker containerization manifests, compose configuration,
Dockerfile specifications, and .dockerignore rules per Phase P14 requirements.
"""
from pathlib import Path
import re
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@pytest.fixture
def compose_config():
    compose_path = ROOT_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml not found in repository root"
    with open(compose_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def root_dockerfile_content():
    dockerfile_path = ROOT_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Root Dockerfile not found"
    return dockerfile_path.read_text(encoding="utf-8")


@pytest.fixture
def rag_dockerfile_content():
    rag_dockerfile_path = ROOT_DIR / "RAG" / "Dockerfile"
    assert rag_dockerfile_path.exists(), "RAG/Dockerfile not found"
    return rag_dockerfile_path.read_text(encoding="utf-8")


@pytest.fixture
def dockerignore_patterns():
    dockerignore_path = ROOT_DIR / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore not found"
    lines = dockerignore_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


class TestDockerCompose:
    """Verify docker-compose.yml architecture and service contracts."""

    def test_services_present(self, compose_config):
        services = compose_config.get("services", {})
        expected = ["postgres", "migrate", "api", "worker", "rag", "chrome"]
        for svc in expected:
            assert svc in services, f"Required service '{svc}' missing from docker-compose.yml"

    def test_forbidden_services_absent(self, compose_config):
        services = compose_config.get("services", {})
        assert "redis" not in services, "Redis service must NOT be in docker-compose.yml (violates D5)"
        assert "browserless" not in services, "browserless must NOT be in docker-compose.yml"
        compose_str = str(compose_config)
        assert "browserless/chrome" not in compose_str, "browserless/chrome image is forbidden"

    def test_postgres_service(self, compose_config):
        pg = compose_config["services"]["postgres"]
        assert pg.get("image") == "pgvector/pgvector:pg15"
        assert "healthcheck" in pg
        assert "pg_isready" in str(pg["healthcheck"].get("test", []))
        assert "postgres_data" in str(pg.get("volumes", []))

    def test_migrate_service(self, compose_config):
        migrate = compose_config["services"]["migrate"]
        assert migrate.get("restart") == "no"
        cmd = migrate.get("command", [])
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        assert "python Database/setup.py" in cmd_str
        assert "python -m RAG.migrate" in cmd_str
        deps = migrate.get("depends_on", {})
        assert "postgres" in deps
        assert deps["postgres"].get("condition") == "service_healthy"

    def test_api_service(self, compose_config):
        api = compose_config["services"]["api"]
        assert api.get("build", {}).get("dockerfile") == "Dockerfile"
        assert "Backend/.env" in str(api.get("env_file", []))
        cmd = api.get("command", [])
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        assert "--reload" not in cmd_str, "Production API service must NOT use --reload"
        assert "uvicorn" in cmd_str
        assert "--app-dir" in cmd_str and "/app/Backend" in cmd_str
        deps = api.get("depends_on", {})
        assert "postgres" in deps and deps["postgres"].get("condition") == "service_healthy"
        assert "migrate" in deps and deps["migrate"].get("condition") == "service_completed_successfully"

    def test_worker_service(self, compose_config):
        worker = compose_config["services"]["worker"]
        cmd = worker.get("command", [])
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        assert "python -m worker" in cmd_str or ["python", "-m", "worker"] == cmd
        env = worker.get("environment", [])
        env_dict = {item.split("=")[0]: item.split("=")[1] for item in env if "=" in item} if isinstance(env, list) else env
        assert env_dict.get("SELENIUM_MODE") == "remote"
        assert "chrome:4444" in env_dict.get("SELENIUM_REMOTE_URL", "")
        deps = worker.get("depends_on", {})
        assert "chrome" in deps
        assert "migrate" in deps and deps["migrate"].get("condition") == "service_completed_successfully"

    def test_rag_service(self, compose_config):
        rag = compose_config["services"]["rag"]
        assert "./RAG" in rag.get("build", {}).get("context", "")
        cmd = rag.get("command", [])
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        assert "python -m RAG" in cmd_str or ["python", "-m", "RAG"] == cmd
        assert "RAG/.env" in str(rag.get("env_file", []))
        deps = rag.get("depends_on", {})
        assert "postgres" in deps
        assert "migrate" in deps and deps["migrate"].get("condition") == "service_completed_successfully"

    def test_chrome_service(self, compose_config):
        chrome = compose_config["services"]["chrome"]
        assert chrome.get("image") == "selenium/standalone-chrome:4.18.1"
        assert chrome.get("shm_size") == "2g"
        ports = str(chrome.get("ports", []))
        assert "4444" in ports
        assert "7900" in ports


class TestRootDockerfile:
    """Verify root Dockerfile specifications."""

    def test_base_image(self, root_dockerfile_content):
        assert "FROM python:3.11-slim" in root_dockerfile_content

    def test_non_root_user(self, root_dockerfile_content):
        assert "useradd -u 1000" in root_dockerfile_content
        assert "appuser" in root_dockerfile_content
        assert "USER appuser" in root_dockerfile_content
        assert "chown -R appuser:appuser /app" in root_dockerfile_content

    def test_pythonpath(self, root_dockerfile_content):
        assert "PYTHONPATH=/app:/app/Backend" in root_dockerfile_content

    def test_healthcheck(self, root_dockerfile_content):
        assert "HEALTHCHECK" in root_dockerfile_content
        assert "http://localhost:8000/health" in root_dockerfile_content

    def test_cmd(self, root_dockerfile_content):
        cmd_pattern = r'CMD\s*\[\s*"uvicorn"\s*,\s*"app:app"\s*,\s*"--app-dir"\s*,\s*"/app/Backend"\s*,\s*"--host"\s*,\s*"0\.0\.0\.0"\s*,\s*"--port"\s*,\s*"8000"\s*\]'
        assert re.search(cmd_pattern, root_dockerfile_content), "CMD must match required uvicorn command"


class TestRAGDockerfile:
    """Verify RAG standalone Dockerfile specifications."""

    def test_base_image(self, rag_dockerfile_content):
        assert "FROM python:3.11-slim" in rag_dockerfile_content

    def test_non_root_user(self, rag_dockerfile_content):
        assert "useradd -u 1000" in rag_dockerfile_content
        assert "USER appuser" in rag_dockerfile_content
        assert "chown -R appuser:appuser /app" in rag_dockerfile_content

    def test_cmd(self, rag_dockerfile_content):
        assert 'CMD ["python", "-m", "RAG"]' in rag_dockerfile_content


class TestDockerIgnore:
    """Verify .dockerignore exclusions."""

    def test_mandatory_exclusions(self, dockerignore_patterns):
        required_patterns = [
            ".env*",
            ".venv/",
            "node_modules/",
            "__pycache__/",
            "_unused_scripts/",
            "docs/baseline/",
        ]
        for pattern in required_patterns:
            assert pattern in dockerignore_patterns, f"Mandatory pattern '{pattern}' missing from .dockerignore"

    def test_scraper_outputs_excluded(self, dockerignore_patterns):
        has_csv = any(".csv" in p for p in dockerignore_patterns)
        has_output = any("output" in p for p in dockerignore_patterns)
        assert has_csv, "*.csv scraper outputs must be excluded"
        assert has_output, "scraper outputs directories must be excluded"


class TestRequirementsSplit:
    """Verify requirements.txt and requirements-dev.txt clean separation."""

    def test_prod_requirements_in(self):
        req_in = (ROOT_DIR / "requirements.in").read_text(encoding="utf-8")
        assert "pgvector" in req_in
        assert "httpx" in req_in
        assert "python-dateutil" in req_in

        forbidden = ["redis", "rq", "passlib", "webdriver-manager", "testcontainers"]
        for pkg in forbidden:
            assert pkg not in req_in, f"Forbidden package '{pkg}' found in prod requirements.in"

    def test_dev_requirements_in(self):
        dev_in = (ROOT_DIR / "requirements-dev.in").read_text(encoding="utf-8")
        assert "pytest" in dev_in
        assert "testcontainers" in dev_in
        assert "ruff" in dev_in
        assert "mypy" in dev_in
