"""
tests/unit/test_rag_isolation.py — RAG isolation test (P17.1)
Rule 11: Backend/ and Database/ never import RAG; RAG/ never imports Backend/Database.
"""
import ast
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent.parent
_backend = _root / "Backend"
_database = _root / "Database"
_rag = _root / "RAG"


def _find_imports(directory: Path, forbidden_modules: set) -> list:
    """Find imports of forbidden modules in a directory."""
    violations = []
    if not directory.exists():
        return violations

    for pyfile in directory.rglob("*.py"):
        if "__pycache__" in str(pyfile):
            continue
        try:
            source = pyfile.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(pyfile))
        except (SyntaxError, ValueError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in forbidden_modules:
                        violations.append(
                            f"{pyfile.relative_to(_root)}:{node.lineno} imports {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in forbidden_modules:
                    violations.append(
                        f"{pyfile.relative_to(_root)}:{node.lineno} imports from {node.module}"
                    )
    return violations


class TestRagIsolation:
    def test_backend_does_not_import_rag(self):
        """Backend/ should never import RAG/ directly."""
        violations = _find_imports(_backend, {"RAG"})
        assert not violations, "Backend imports RAG:\n" + "\n".join(violations)

    def test_database_does_not_import_rag(self):
        """Database/ should never import RAG/ directly."""
        violations = _find_imports(_database, {"RAG"})
        assert not violations, "Database imports RAG:\n" + "\n".join(violations)

    def test_rag_does_not_import_backend_or_database(self):
        """RAG/ should never import Backend/ or Database/ directly."""
        violations = _find_imports(_rag, {"Backend", "Database"})
        assert not violations, "RAG imports Backend/Database:\n" + "\n".join(violations)
