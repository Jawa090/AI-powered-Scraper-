"""
RAG Service Isolation Test
Implements P10.7:
Scan the AST of Backend/ and Database/ for imports of RAG,
and of RAG/ for imports of Backend or Database -> none allowed.
"""
import ast
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "node_modules",
    "dist",
    "build",
}


def _get_imports(file_path: Path):
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.lineno, node.module))
    return imports


@pytest.mark.unit
def test_rag_isolation():
    """Verify that Backend and Database do not import RAG, and RAG does not import Backend/Database."""
    backend_dir = PROJECT_ROOT / "Backend"
    database_dir = PROJECT_ROOT / "Database"
    rag_dir = PROJECT_ROOT / "RAG"

    violations = []

    # 1. Check Backend/ and Database/ for imports of RAG
    for search_dir in (backend_dir, database_dir):
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            parts = set(py_file.parts)
            if any(p in parts for p in EXCLUDED_PARTS):
                continue
            for lineno, mod in _get_imports(py_file):
                if mod == "RAG" or mod.startswith("RAG."):
                    violations.append(f"{py_file}:{lineno} -> {mod} (Backend/Database cannot import RAG)")

    # 2. Check RAG/ for imports of Backend or Database
    if rag_dir.exists():
        for py_file in rag_dir.rglob("*.py"):
            parts = set(py_file.parts)
            if any(p in parts for p in EXCLUDED_PARTS):
                continue
            for lineno, mod in _get_imports(py_file):
                if (
                    mod == "Backend"
                    or mod.startswith("Backend.")
                    or mod == "Database"
                    or mod.startswith("Database.")
                ):
                    violations.append(f"{py_file}:{lineno} -> {mod} (RAG cannot import Backend or Database)")

    assert not violations, "RAG isolation violations detected:\n" + "\n".join(violations)
