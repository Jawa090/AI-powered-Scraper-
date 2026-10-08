"""Bounded audit checks; use only the example test configuration."""
from pathlib import Path
import faulthandler
import json
import os
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATAOPS_ENV_FILE"] = str(ROOT / "Backend/.env.test.example")
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT)]
faulthandler.dump_traceback_later(50, exit=True)

if sys.argv[1] == "db":
    import psycopg
    from settings import load_settings
    config = load_settings()
    try:
        url = config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(url, connect_timeout=3,
                             options="-c default_transaction_read_only=on -c statement_timeout=3000") as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_setting('server_version'), current_setting('transaction_read_only')")
                version, readonly = cursor.fetchone()
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                count = cursor.fetchone()[0]
                print(json.dumps({"connected": True, "server_version": version,
                                  "transaction_read_only": readonly, "public_tables": count}))
    except Exception as exc:
        # Avoid printing connection strings or secrets in diagnostic output.
        print(json.dumps({"connected": False, "error_type": type(exc).__name__,
                          "sqlstate": getattr(exc, "sqlstate", None)}))
        sys.exit(2)
else:
    from langgraph.checkpoint.memory import MemorySaver
    checkpoint = types.ModuleType("agents.graph.checkpointer")
    checkpoint.checkpointer = MemorySaver()
    checkpoint.setup_checkpointer = lambda: None
    sys.modules["agents.graph.checkpointer"] = checkpoint
    import pytest
    class FailureDetails:
        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(self, item, call):
            outcome = yield
            report = outcome.get_result()
            if report.failed and call.excinfo:
                print("\nAUDIT_FAILURE:", item.nodeid, call.excinfo.type.__name__,
                      str(call.excinfo.value))
    target = {"graph": "Backend/tests/unit/test_agent_graph.py",
              "rag": "RAG/tests/test_contract.py"}[sys.argv[1]]
    sys.exit(pytest.main(["--noconftest", "-c", "Backend/pytest.ini", target,
                          "-q", "--tb=no", "-o", "addopts="], plugins=[FailureDetails()]))
