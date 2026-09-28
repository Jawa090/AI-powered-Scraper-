"""
Phase 1 Verification Script
Run from Backend/ directory.
"""
import sys
import os
import re
import inspect

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"

results = []

def check(label, condition, msg_pass="", msg_fail=""):
    if condition:
        tag = PASS
        print(f"{PASS} {label}: {msg_pass or 'OK'}")
        results.append((True, label))
    else:
        tag = FAIL
        print(f"{FAIL} {label}: {msg_fail or 'FAILED'}")
        results.append((False, label))

print("=" * 60)
print("PHASE 1 VERIFICATION")
print("=" * 60)

# ─── SECTION A: Registry ────────────────────────────────────
print("\n=== A. SCRIPTS_REGISTRY ===")
try:
    from execution.registry import SCRIPTS_REGISTRY, get_registered_script
    check("registry import", True, f"{len(SCRIPTS_REGISTRY)} scripts: {[s['id'] for s in SCRIPTS_REGISTRY]}")
    check("registry has 4 scripts", len(SCRIPTS_REGISTRY) == 4)
    for sid in ["bonfire", "dasny", "jwiz", "nyscr"]:
        check(f"registry has '{sid}'", any(s["id"] == sid for s in SCRIPTS_REGISTRY))
except Exception as e:
    check("registry import", False, msg_fail=str(e))

with open("scraper_manager.py") as f:
    sm_src = f.read()
check("scraper_manager no own SCRIPTS_REGISTRY list", "SCRIPTS_REGISTRY = [" not in sm_src,
      "scraper_manager does not define its own list",
      "scraper_manager STILL defines SCRIPTS_REGISTRY = [...]")

with open("app.py") as f:
    app_src = f.read()
check("app.py imports SCRIPTS_REGISTRY from execution.registry",
      "from execution.registry import SCRIPTS_REGISTRY" in app_src)

# ─── SECTION B: Dead code ───────────────────────────────────
print("\n=== B. DEAD CODE REMOVAL ===")
dead_methods = ["_run_job_thread", "_execute_bonfire", "_execute_jwiz",
                "_execute_dasny", "_execute_nyscr", "_standardize_records"]
for m in dead_methods:
    has_def = bool(re.search(rf"def {re.escape(m)}\s*\(", sm_src))
    check(f"scraper_manager: {m} not defined", not has_def,
          f"correctly absent", f"ACTIVE dead def found!")

# ─── SECTION C: No JSON fallback ────────────────────────────
print("\n=== C. NO JSON FILE FALLBACK ===")
for fname in ["scraper_manager.py"]:
    with open(fname) as f:
        s = f.read()
    has_json = any(kw in s for kw in ["json.load", "json.dump", "jobs.json", "datasets.json", "leads.json"])
    check(f"{fname}: no JSON file I/O", not has_json)

# ─── SECTION D: No synthetic data in active path ────────────
print("\n=== D. NO SYNTHETIC DATA IN ACTIVE PATH ===")
try:
    import execution.dispatcher as disp_mod
    disp_src = inspect.getsource(disp_mod)
    check("dispatcher: no 555 phone numbers", "555" not in disp_src)
    check("dispatcher: no example.com", "example.com" not in disp_src)
    check("dispatcher: no rfp-bids@dasny.org", "rfp-bids@dasny.org" not in disp_src)
    check("dispatcher: no procurement@nyscr", "procurement@nyscr" not in disp_src)
    check("dispatcher: no hardcoded +1 (214)", "+1 (214)" not in disp_src)
except Exception as e:
    check("dispatcher synthetic data check", False, msg_fail=str(e))

# ─── SECTION E: validate_records ────────────────────────────
print("\n=== E. validate_records FUNCTION ===")
try:
    from execution.dispatcher import validate_records

    # Valid record
    v, rej, reasons = validate_records([
        {"title": "Test RFP", "organization_name": "ACME", "email": "test@real.com", "website": "https://real.com"}
    ], "bonfire")
    check("validate_records: valid record accepted", len(v) == 1 and rej == 0, f"1 valid, 0 rejected")

    # Missing title and org name → rejected
    v2, rej2, _ = validate_records([{"email": "a@b.com"}], "jwiz")
    check("validate_records: missing title+org rejected", rej2 == 1, "correctly rejected")

    # Bad email → cleared to None
    v3, rej3, _ = validate_records([{"title": "T", "email": "not-an-email"}], "dasny")
    check("validate_records: bad email cleared to None", len(v3) == 1 and v3[0]["email"] is None)

    # Bad URL → cleared to None
    v4, _, _ = validate_records([{"title": "T2", "website": "ftp://bad"}], "nyscr")
    check("validate_records: bad website cleared to None", len(v4) == 1 and v4[0]["website"] is None)

    # No fabrication: None phone accepted as-is
    v5, _, _ = validate_records([{"title": "T3", "phone": None}], "jwiz")
    check("validate_records: None phone accepted", len(v5) == 1 and v5[0]["phone"] is None)

except Exception as e:
    check("validate_records tests", False, msg_fail=str(e))
    import traceback; traceback.print_exc()

# ─── SECTION F: NYSCR credential preflight ──────────────────
print("\n=== F. NYSCR CREDENTIAL PREFLIGHT ===")
try:
    from execution.dispatcher import execute_nyscr
    src_nyscr = inspect.getsource(execute_nyscr)
    check("execute_nyscr: NYSCR_USERNAME check", "NYSCR_USERNAME" in src_nyscr)
    check("execute_nyscr: NYSCR_PASSWORD check", "NYSCR_PASSWORD" in src_nyscr)
    check("execute_nyscr: raises RuntimeError when blocked", "RuntimeError" in src_nyscr)
    check("execute_nyscr: uses NYSCRScraper (not NyscrScraper)", "NYSCRScraper" in src_nyscr and "NyscrScraper" not in src_nyscr)
    # Test actual preflight: ensure NYSCR_USERNAME not set → raises RuntimeError
    os.environ.pop("NYSCR_USERNAME", None)
    os.environ.pop("NYSCR_PASSWORD", None)
    def fake_telemetry(progress, step, msg, level="info", records_found=None): pass
    try:
        execute_nyscr({}, fake_telemetry)
        check("execute_nyscr: raises when no credentials", False, msg_fail="Did NOT raise — should have raised RuntimeError!")
    except RuntimeError as blocked:
        check("execute_nyscr: raises RuntimeError when no credentials", True, f"'{str(blocked)[:60]}...'")
    except Exception as other:
        check("execute_nyscr: raises when no credentials", False, msg_fail=f"Wrong exception type: {type(other).__name__}: {other}")
except Exception as e:
    check("execute_nyscr preflight test", False, msg_fail=str(e))

# ─── SECTION G: Executor validation wiring ──────────────────
print("\n=== G. EXECUTOR USES VALIDATED LEADS ===")
try:
    from execution import executor as exec_mod
    exec_src = inspect.getsource(exec_mod)
    check("executor: imports validate_records", "validate_records" in exec_src)
    check("executor: calls validate_records in _worker", "validate_records(" in exec_src)
    check("executor: uses validated_leads", "validated_leads" in exec_src)
    check("executor: ingest_lead_atomic uses validated_leads", "for lead_item in validated_leads" in exec_src)
except Exception as e:
    check("executor validation wiring", False, msg_fail=str(e))

# ─── SECTION H: Orchestrator ────────────────────────────────
print("\n=== H. ORCHESTRATOR ===")
try:
    with open("agents/orchestrator.py") as f:
        orch_src = f.read()
    # Check for correct deferred import
    check("orchestrator: imports SCRIPTS_REGISTRY from execution.registry",
          "from execution.registry import SCRIPTS_REGISTRY" in orch_src,
          msg_fail="deferred import may still reference scraper_manager")
    check("orchestrator: does NOT import SCRIPTS_REGISTRY from scraper_manager",
          "from scraper_manager import SCRIPTS_REGISTRY" not in orch_src)
    # Check that no direct scraper calls exist
    check("orchestrator: no direct DallasBonfireScraper calls",
          "DallasBonfireScraper" not in orch_src)
    check("orchestrator: no direct DasnyScraper calls",
          "DasnyScraper" not in orch_src)
    check("orchestrator: no direct NYSCRScraper calls",
          "NYSCRScraper" not in orch_src)
    # Job status handling
    check("orchestrator: handles Failed status", "failed" in orch_src.lower())
    check("orchestrator: handles Running status", "running" in orch_src.lower())
    check("orchestrator: handles Completed status", "completed" in orch_src.lower())
except Exception as e:
    check("orchestrator check", False, msg_fail=str(e))

# ─── SECTION I: Scraper engine imports ──────────────────────
print("\n=== I. SCRAPER ENGINE IMPORTS ===")
for engine, module, cls in [
    ("bonfire", "dallas_bonfire_scraper", "DallasBonfireScraper"),
    ("dasny", "dasny_scraper", "DasnyScraper"),
    ("nyscr", "final_scraper", "NYSCRScraper"),
]:
    try:
        m = __import__(module)
        c = getattr(m, cls)
        check(f"{engine}: {cls} importable", True)
    except Exception as e:
        check(f"{engine}: {cls} importable", False, msg_fail=str(e))

try:
    import jwiz
    required = ["HTTPClient", "build_search_url", "find_result_cards",
                "extract_company_name", "extract_phone", "extract_email"]
    missing = [fn for fn in required if not hasattr(jwiz, fn)]
    check("jwiz: all required functions present", not missing,
          f"all {len(required)} functions found",
          f"missing: {missing}")
except Exception as e:
    check("jwiz import", False, msg_fail=str(e))

# ─── SECTION J: Job lifecycle in JobService ─────────────────
print("\n=== J. JOB LIFECYCLE ===")
try:
    with open("services/job_service.py") as f:
        js_src = f.read()
    check("job_service: create() → Queued", '"Queued"' in js_src)
    check("job_service: start() → Running", '"Running"' in js_src)
    check("job_service: complete() → Completed", '"Completed"' in js_src)
    check("job_service: fail() → Failed", '"Failed"' in js_src)
    check("job_service: fail() records error_message", "error_message" in js_src)
except Exception as e:
    check("job_service lifecycle", False, msg_fail=str(e))

# ─── SECTION K: Database connectivity ───────────────────────
print("\n=== K. DATABASE CONNECTIVITY ===")
try:
    from database.connection import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as session:
        result = session.execute(text("SELECT 1")).scalar()
    check("PostgreSQL: SELECT 1", result == 1, f"result = {result}")
except Exception as e:
    check("PostgreSQL connectivity", False, msg_fail=str(e))

# ─── SECTION L: FastAPI app import ──────────────────────────
print("\n=== L. FASTAPI APP ===")
try:
    import app as app_mod
    check("app.py: imports successfully", True)
    route_paths = [r.path for r in app_mod.app.routes]
    required_routes = ["/api/bot/chat", "/api/jobs", "/api/leads", "/api/datasets",
                       "/api/scripts", "/health", "/health/ready"]
    for route in required_routes:
        check(f"route {route} exists", route in route_paths)
except Exception as e:
    check("app.py import", False, msg_fail=str(e))
    import traceback; traceback.print_exc()

# ─── SUMMARY ─────────────────────────────────────────────────
print()
print("=" * 60)
passed = sum(1 for ok, _ in results if ok)
failed = sum(1 for ok, _ in results if not ok)
print(f"RESULTS: {passed} PASSED, {failed} FAILED out of {len(results)} checks")
if failed:
    print("\nFailed checks:")
    for ok, label in results:
        if not ok:
            print(f"  - {label}")
print("=" * 60)
