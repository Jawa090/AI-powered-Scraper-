"""API probe script for P0.2.

Validates required imports, prints versions of key packages,
and fails loudly if any import is missing.
"""
import sys
import importlib.metadata

REQUIRED_IMPORTS = [
    ("langgraph.types", ["interrupt", "Command"]),
    ("langgraph.prebuilt", ["ToolNode", "InjectedState"]),
    ("langchain_core.tools", ["InjectedToolCallId"]),
    ("langchain_core.messages", ["trim_messages", "RemoveMessage", "ToolMessage"]),
    ("langgraph.checkpoint.postgres", ["PostgresSaver"]),
    ("langgraph.checkpoint.memory", ["InMemorySaver"]),
    ("psycopg_pool", ["ConnectionPool"]),
    ("psycopg.rows", ["dict_row"]),
    ("sqlalchemy.dialects.postgresql", ["insert"]),
    ("pgvector.sqlalchemy", ["Vector"]),
    ("httpx", None),
    ("jwt", None),
    ("langchain_google_genai", ["ChatGoogleGenerativeAI"]),
]

PACKAGES_TO_REPORT = [
    "langgraph",
    "langgraph-checkpoint",
    "langgraph-checkpoint-postgres",
    "langchain",
    "langchain-core",
    "langchain-google-genai",
    "psycopg",
    "psycopg-pool",
    "SQLAlchemy",
    "pgvector",
    "httpx",
    "PyJWT",
    "pydantic",
    "fastapi",
    "alembic",
    "pytest",
]


def check_packages():
    print("=" * 60)
    print("INSTALLED PACKAGE VERSIONS")
    print("=" * 60)
    for pkg in PACKAGES_TO_REPORT:
        try:
            ver = importlib.metadata.version(pkg)
            print(f"  {pkg:32} {ver}")
        except importlib.metadata.PackageNotFoundError:
            print(f"  {pkg:32} NOT INSTALLED")


def check_imports():
    print("=" * 60)
    print("PROBING REQUIRED IMPORTS")
    print("=" * 60)
    errors = []
    for mod_name, symbols in REQUIRED_IMPORTS:
        try:
            mod = __import__(mod_name, fromlist=symbols or [])
            if symbols:
                for sym in symbols:
                    if not hasattr(mod, sym):
                        errors.append(f"Missing symbol '{sym}' from module '{mod_name}'")
                    else:
                        print(f"  [OK] from {mod_name} import {sym}")
            else:
                print(f"  [OK] import {mod_name}")
        except Exception as exc:
            errors.append(f"Failed to import '{mod_name}': {exc}")
            print(f"  [FAIL] import {mod_name}: {exc}")

    print("=" * 60)
    if errors:
        print(f"PROBE FAILED: {len(errors)} error(s) encountered:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("ALL REQUIRED IMPORTS VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    check_packages()
    print()
    check_imports()
