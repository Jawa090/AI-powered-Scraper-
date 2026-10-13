"""Read-only, offline audit probes. Uses test settings and mocks all persistence.

Run from the repository root with an interpreter containing project dependencies.
This is an audit harness, not the application's acceptance test suite.
"""
from __future__ import annotations

import ast
import contextlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import types
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATAOPS_ENV_FILE"] = str(ROOT / "Backend/.env.test.example")
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT)]


def main():
    result = {"runtime": sys.version, "scope": "Offline test configuration; no application database writes, live AI calls, or live scraping"}
    paths = []
    for folder in ["Backend", "Database", "RAG", "scripts"]:
        paths.extend((ROOT / folder).rglob("*.py"))
    paths.extend(ROOT.glob("*.py"))
    errors = []
    imports = []
    for path in sorted(set(paths)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (SyntaxError, UnicodeError) as exc:
            errors.append({"file": str(path.relative_to(ROOT)), "error": str(exc)})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                if module.startswith(("execution.", "agents.llm.", "Database.repositories.")):
                    check = ROOT / "Backend" / (module.replace(".", "/") + ".py")
                    if module.startswith("Database."):
                        check = ROOT / (module.replace(".", "/") + ".py")
                    imports.append({"file": str(path.relative_to(ROOT)), "line": node.lineno, "module": module, "target_exists": check.exists() or check.with_suffix("").is_dir()})
    result["syntax"] = {"files": len(set(paths)), "errors": errors}
    result["missing_internal_imports"] = [item for item in imports if not item["target_exists"]]
    result["direct_repository_imports_outside_database"] = [item for item in imports if item["module"].startswith("Database.repositories.") and not item["file"].startswith("Database") and "tests" not in item["file"]]

    # Avoid import-time connection-pool threads. The graph uses an in-memory saver.
    from langgraph.checkpoint.memory import MemorySaver
    checkpoint = types.ModuleType("agents.graph.checkpointer")
    checkpoint.checkpointer = MemorySaver()
    checkpoint.setup_checkpointer = lambda: None
    sys.modules["agents.graph.checkpointer"] = checkpoint

    graph_mod = importlib.import_module("agents.graph.graph")
    search_mod = importlib.import_module("agents.graph.nodes.auto_search")
    proposal_mod = importlib.import_module("agents.graph.nodes.auto_propose")
    confirm_mod = importlib.import_module("agents.graph.nodes.confirmation")
    final_mod = importlib.import_module("agents.graph.nodes.finalize")
    runner_mod = importlib.import_module("agents.graph.runner")
    from agents.llm.chat_model import LLMUnavailable
    from langchain_core.messages import ToolMessage, HumanMessage
    from scrappers.controller import validate_params, check_ready
    from services.auth import create_access_token, hash_password, verify_password, sync_env_users
    from settings import settings, load_settings
    from Database.normalize import lead_identity, fingerprint
    import jwt

    slots = {"category": "roofing", "city": "Dallas", "us_state": "TX", "quantity": 50,
             "required_fields": {"has_email": True, "has_phone": True}, "fresh_within_days": 7, "source": "jwiz"}
    leads = [types.SimpleNamespace(id=f"audit-{n}", organization=None, contact=None, title="Roofing", status="New") for n in range(20)]
    repos = MagicMock()
    repos.leads.search_leads.return_value = (leads, 50)
    with patch.object(search_mod, "session_scope", return_value=contextlib.nullcontext(MagicMock())), patch.object(search_mod, "Repositories", return_value=repos):
        search = search_mod.auto_search({"slots": slots, "turn_id": "audit-turn"})
    result["search_probe"] = {"requested": 50, "repository_arguments": repos.leads.search_leads.call_args.kwargs,
                              "last_search": search["last_search"], "reply": search["messages"][-1].content}
    with patch.object(search_mod, "session_scope", side_effect=RuntimeError("synthetic database failure")):
        failure_search = search_mod.auto_search({"slots": slots, "turn_id": "audit-turn"})
    result["database_failure_probe"] = failure_search["last_search"]

    proposal = proposal_mod.auto_propose({"slots": {"category": "construction bids", "city": "Albany", "us_state": "NY", "quantity": 10}, "session_id": "audit", "query_id": "audit"})
    result["unready_source_proposal"] = {"source": proposal["pending_proposal"]["source"], "ready": check_ready("nyscr")[0]}
    result["bonfire_wrong_city_probe"] = validate_params("bonfire", {"city": "Houston", "us_state": "TX", "limit": 5}).model_dump()
    graph = graph_mod.build_agent_graph(checkpointer_instance=MemorySaver())
    result["graph_edges"] = [{"source": edge.source, "target": edge.target} for edge in graph.get_graph().edges]

    with patch.object(confirm_mod, "get_chat_model", side_effect=LLMUnavailable("not_configured")):
        fallback = confirm_mod.ask_confirmation({"pending_proposal": {"source": "jwiz", "args": {"quantity": 10}}})
    result["confirmation_ai_outage"] = fallback["pending_proposal"]["question"]
    with patch.object(runner_mod, "invoke_structured", side_effect=LLMUnavailable("not_configured")):
        result["approval_ai_outage"] = runner_mod.classify_confirmation("yes", {"question": "Proceed?"})
    with patch.object(final_mod, "get_chat_model", side_effect=LLMUnavailable("not_configured")), patch.object(final_mod, "save_turn"):
        result["finalization_ai_outage"] = final_mod.finalize({"messages": [ToolMessage(content="synthetic result", tool_call_id="audit")]})["messages"][-1].content
    with patch.object(confirm_mod, "interrupt", return_value={"decision": "modify", "edits": "only 20", "text": "only 20"}):
        result["confirmation_modify_probe"] = confirm_mod.await_confirmation({"pending_proposal": {"source": "jwiz", "args": {"quantity": 50}}})

    token = create_access_token(types.SimpleNamespace(id="audit-user", role="user"))
    claims = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    result["jwt_lifetime_hours"] = (claims["exp"] - claims["iat"]) / 3600
    hashed = hash_password("audit-password")
    result["password_hash_roundtrip"] = verify_password("audit-password", hashed) and not verify_password("wrong", hashed)
    session = MagicMock()
    session.get.return_value = None
    sync_env_users(session)
    result["builtin_account_hashes"] = [{"role": call.args[0].role, "auth_source": call.args[0].auth_source, "has_hash": bool(call.args[0].password_hash)} for call in session.add.call_args_list]
    fp = fingerprint("Acme", "acme.example", "+12125551234", "hello@acme.example")
    result["company_identity_probe"] = {"source_a": lead_identity("company", "a", "123", fp), "source_b": lead_identity("company", "b", "456", fp)}

    # API schema inspection runs without lifespan, requests, or a database.
    app_mod = importlib.import_module("app")
    schema = app_mod.app.openapi()
    result["api_paths"] = sorted(schema["paths"])
    result["llm_health_security"] = schema["paths"]["/health/llm"]["get"].get("security", [])
    try:
        importlib.import_module("Database.seed")
        result["seed_import"] = "ok"
    except Exception as exc:
        result["seed_import"] = f"{type(exc).__name__}: {exc}"

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "postgresql+psycopg://audit:audit@invalid:1/environment_override"
    try:
        result["environment_override_honored"] = load_settings().DATABASE_URL.endswith("environment_override")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

    packages = {}
    for name in ["pytest", "fastapi", "sqlalchemy", "langgraph", "psycopg", "pytz"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    result["installed_packages"] = packages
    result["pytz_in_production_requirements"] = "pytz==" in (ROOT / "requirements.txt").read_text(encoding="utf-8")
    output = ROOT / "docs/audit/verification.json"
    output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
