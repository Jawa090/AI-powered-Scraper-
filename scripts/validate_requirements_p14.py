#!/usr/bin/env python3
"""Standalone Phase P14 Dependency & Requirements Validation Script.

Checks:
1. Production requirements file existence and synchronization.
2. Complete exclusion of forbidden packages (rq, redis, passlib, webdriver-manager, testcontainers).
3. Presence of required packages (pgvector, httpx, python-dateutil).
4. Strict pinning (==) of all production dependencies.
5. Presence of dev tools (pytest, testcontainers, ruff, mypy) in requirements-dev.txt.
6. Clean Python imports of core production libraries.
"""

import importlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
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

DEV_TOOLS = [
    "pytest",
    "testcontainers",
    "ruff",
    "mypy",
]

CORE_IMPORT_MODULES = [
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


def parse_packages(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    pkgs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        base_req = line.split(";")[0].strip()
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)(.*)$", base_req)
        if match:
            pkg_name = match.group(1).lower().replace("_", "-")
            spec = match.group(2).strip()
            pkgs[pkg_name] = spec
    return pkgs


def main() -> int:
    print("=" * 70)
    print("PHASE P14: REQUIREMENTS SPLIT & DEPENDENCY VALIDATION")
    print("=" * 70)
    failures = 0

    # 1. Existence and sync check
    print("\n[1/6] Checking requirements file existence & synchronization...")
    for p in [PROD_REQ_PATH, PROD_IN_PATH, DEV_REQ_PATH, DEV_IN_PATH, BACKEND_REQ_PATH]:
        if not p.exists():
            print(f"  FAIL: File not found: {p}")
            failures += 1
        else:
            print(f"  OK: Found {p.name}")

    if PROD_REQ_PATH.exists() and BACKEND_REQ_PATH.exists():
        if PROD_REQ_PATH.read_text(encoding="utf-8").strip() != BACKEND_REQ_PATH.read_text(encoding="utf-8").strip():
            print("  FAIL: Backend/requirements.txt is out of sync with root requirements.txt")
            failures += 1
        else:
            print("  OK: Backend/requirements.txt is synchronized with root requirements.txt")

    prod_pkgs = parse_packages(PROD_REQ_PATH)
    in_pkgs = parse_packages(PROD_IN_PATH)
    dev_pkgs = parse_packages(DEV_REQ_PATH)

    # 2. Forbidden dependencies check
    print("\n[2/6] Checking for forbidden production dependencies...")
    for forbidden in FORBIDDEN_PROD_PACKAGES:
        norm = forbidden.lower().replace("_", "-")
        in_prod = norm in prod_pkgs
        in_in = norm in in_pkgs
        if in_prod or in_in:
            print(f"  FAIL: Forbidden package detected: '{forbidden}' (prod: {in_prod}, in: {in_in})")
            failures += 1
        else:
            print(f"  OK: Forbidden package '{forbidden}' is strictly excluded")

    # 3. Required production dependencies
    print("\n[3/6] Checking for required production dependencies...")
    for required in REQUIRED_PROD_PACKAGES:
        norm = required.lower().replace("_", "-")
        if norm in prod_pkgs and norm in in_pkgs:
            print(f"  OK: Required package '{required}' present: {prod_pkgs[norm]}")
        else:
            print(f"  FAIL: Required package '{required}' missing from prod requirements")
            failures += 1

    # 4. Strict pinning
    print("\n[4/6] Checking pinning format (==) for production dependencies...")
    unpinned = [pkg for pkg, spec in prod_pkgs.items() if not spec.startswith("==")]
    if unpinned:
        print(f"  FAIL: Unpinned packages found in requirements.txt: {unpinned}")
        failures += 1
    else:
        print(f"  OK: All {len(prod_pkgs)} production packages are strictly pinned (==)")

    # 5. Dev tools in requirements-dev.txt
    print("\n[5/6] Checking dev & testing tools in requirements-dev.txt...")
    for tool in DEV_TOOLS:
        norm = tool.lower().replace("_", "-")
        if norm in dev_pkgs:
            print(f"  OK: Dev tool '{tool}' present: {dev_pkgs[norm]}")
        else:
            print(f"  FAIL: Dev tool '{tool}' missing from requirements-dev.txt")
            failures += 1

    # 6. Clean import verification
    print("\n[6/6] Verifying clean runtime imports of core production modules...")
    for mod_name, pkg_name in CORE_IMPORT_MODULES:
        try:
            importlib.import_module(mod_name)
            print(f"  OK: Imported '{mod_name}' ({pkg_name}) cleanly")
        except Exception as e:
            print(f"  FAIL: Failed importing '{mod_name}' ({pkg_name}): {e}")
            failures += 1

    print("\n" + "=" * 70)
    if failures == 0:
        print("RESULT: SUCCESS - All Phase P14 Dependency Criteria Satisfied!")
        print("=" * 70)
        return 0
    else:
        print(f"RESULT: FAILED with {failures} error(s)")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
