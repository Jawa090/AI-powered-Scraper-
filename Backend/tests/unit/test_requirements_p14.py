"""Unit test suite for Phase P14 Requirements Split, Locking, and Dependency Validation.

Validates:
1. Production requirements.txt contains all required libraries (pgvector, httpx, python-dateutil).
2. Production requirements.txt strictly excludes forbidden dependencies (rq, redis, passlib, webdriver-manager, testcontainers).
3. Production requirements are strictly pinned (==).
4. Development requirements (requirements-dev.txt) include testing and dev tools (pytest, testcontainers, ruff, mypy).
5. Backend/requirements.txt is synchronized with root requirements.txt.
6. Core required production packages are importable and functional in the Python runtime.
"""

import importlib
import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_REQ_PATH = REPO_ROOT / "requirements.txt"
PROD_IN_PATH = REPO_ROOT / "requirements.in"
DEV_REQ_PATH = REPO_ROOT / "requirements-dev.txt"
DEV_IN_PATH = REPO_ROOT / "requirements-dev.in"
BACKEND_REQ_PATH = REPO_ROOT / "Backend" / "requirements.txt"

FORBIDDEN_PROD_PACKAGES = [
    "rq",
    "redis",
    "passlib",
    "webdriver-manager",
    "webdriver_manager",
    "testcontainers",
]

REQUIRED_PROD_PACKAGES = [
    "pgvector",
    "httpx",
    "python-dateutil",
]

ADDITIONAL_CORE_PROD_PACKAGES = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "sqlalchemy",
    "psycopg",
    "alembic",
    "selenium",
    "langgraph",
    "langchain-core",
    "langchain-google-genai",
    "langchain-openai",
    "sentry-sdk",
    "pyjwt",
    "phonenumbers",
]

DEV_TOOL_PACKAGES = [
    "pytest",
    "testcontainers",
    "ruff",
    "mypy",
]


def parse_package_names(req_path: Path) -> dict[str, str]:
    """Parse requirements file into mapping of package_name -> pinned_version/spec."""
    assert req_path.exists(), f"File {req_path} does not exist"
    packages: dict[str, str] = {}
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        # Split environment markers if any (e.g. package==1.0 ; sys_platform == 'win32')
        base_req = line.split(";")[0].strip()
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)(.*)$", base_req)
        if match:
            pkg_name = match.group(1).lower().replace("_", "-")
            spec = match.group(2).strip()
            packages[pkg_name] = spec
    return packages


@pytest.mark.unit
def test_requirements_files_exist():
    """Verify all requirements specification and lock files exist."""
    assert PROD_REQ_PATH.exists(), f"Missing {PROD_REQ_PATH}"
    assert PROD_IN_PATH.exists(), f"Missing {PROD_IN_PATH}"
    assert DEV_REQ_PATH.exists(), f"Missing {DEV_REQ_PATH}"
    assert DEV_IN_PATH.exists(), f"Missing {DEV_IN_PATH}"
    assert BACKEND_REQ_PATH.exists(), f"Missing {BACKEND_REQ_PATH}"


@pytest.mark.unit
def test_backend_requirements_synchronized():
    """Verify Backend/requirements.txt matches root requirements.txt exactly."""
    root_content = PROD_REQ_PATH.read_text(encoding="utf-8").strip()
    backend_content = BACKEND_REQ_PATH.read_text(encoding="utf-8").strip()
    assert root_content == backend_content, "Backend/requirements.txt does not match root requirements.txt"


@pytest.mark.unit
def test_zero_forbidden_dependencies_in_production():
    """Verify zero forbidden dependencies in production requirements.txt and requirements.in."""
    prod_packages = parse_package_names(PROD_REQ_PATH)
    in_packages = parse_package_names(PROD_IN_PATH)

    for forbidden in FORBIDDEN_PROD_PACKAGES:
        norm_forbidden = forbidden.lower().replace("_", "-")
        assert (
            norm_forbidden not in prod_packages
        ), f"Forbidden package '{forbidden}' found in production requirements.txt"
        assert (
            norm_forbidden not in in_packages
        ), f"Forbidden package '{forbidden}' found in production requirements.in"


@pytest.mark.unit
def test_all_required_dependencies_in_production():
    """Verify all required libraries (pgvector, httpx, python-dateutil) exist in production."""
    prod_packages = parse_package_names(PROD_REQ_PATH)
    in_packages = parse_package_names(PROD_IN_PATH)

    for required in REQUIRED_PROD_PACKAGES:
        norm_req = required.lower().replace("_", "-")
        assert (
            norm_req in prod_packages
        ), f"Required package '{required}' missing from production requirements.txt"
        assert (
            norm_req in in_packages
        ), f"Required package '{required}' missing from production requirements.in"


@pytest.mark.unit
def test_additional_core_packages_in_production():
    """Verify all additional core architecture packages are present in production requirements."""
    prod_packages = parse_package_names(PROD_REQ_PATH)
    for core_pkg in ADDITIONAL_CORE_PROD_PACKAGES:
        norm_core = core_pkg.lower().replace("_", "-")
        assert (
            norm_core in prod_packages
        ), f"Core architecture package '{core_pkg}' missing from requirements.txt"


@pytest.mark.unit
def test_production_dependencies_strictly_pinned():
    """Verify every dependency in requirements.txt is strictly pinned with '=='."""
    prod_packages = parse_package_names(PROD_REQ_PATH)
    unpinned = []
    for pkg, spec in prod_packages.items():
        if not spec.startswith("=="):
            unpinned.append((pkg, spec))
    assert not unpinned, f"Unpinned packages found in requirements.txt: {unpinned}"


@pytest.mark.unit
def test_development_tools_present_in_dev_requirements():
    """Verify dev/testing tools (pytest, testcontainers, ruff, mypy) are in requirements-dev.txt."""
    dev_packages = parse_package_names(DEV_REQ_PATH)
    for dev_tool in DEV_TOOL_PACKAGES:
        norm_tool = dev_tool.lower().replace("_", "-")
        assert (
            norm_tool in dev_packages
        ), f"Dev tool '{dev_tool}' missing from requirements-dev.txt"


@pytest.mark.unit
def test_clean_imports_of_required_production_libraries():
    """Verify clean import of all required production libraries."""
    modules_to_test = [
        ("pgvector", "pgvector"),
        ("httpx", "httpx"),
        ("dateutil", "python-dateutil"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pydantic", "pydantic"),
        ("sqlalchemy", "sqlalchemy"),
        ("psycopg", "psycopg"),
        ("alembic", "alembic"),
        ("selenium", "selenium"),
        ("langgraph", "langgraph"),
        ("langchain_core", "langchain-core"),
        ("langchain_google_genai", "langchain-google-genai"),
        ("langchain_openai", "langchain-openai"),
        ("phonenumbers", "phonenumbers"),
        ("jwt", "pyjwt"),
        ("sentry_sdk", "sentry-sdk"),
    ]

    import_failures = []
    for module_name, package_name in modules_to_test:
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
            import_failures.append((package_name, module_name, str(e)))

    assert not import_failures, f"Failed to cleanly import required libraries: {import_failures}"
