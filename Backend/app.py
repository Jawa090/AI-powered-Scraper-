"""
FastAPI Server for DataOps Autonomous Intelligence Platform
Wraps 4 scraping engines, manages background job queues, provides REST APIs,
and connects seamlessly with the frontend AI Agent Bot.

Layer 13: Production Readiness, API Hardening & Health Monitoring.
"""

import logging
import os
import sys
import time

# Ensure project root is in path so `from Database import db` works
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load .env file so all env vars (DB, LLM keys, NYSCR creds, etc.) are available
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from fastapi import Depends
from services.auth import get_current_user, require_admin, enforce_scrape_limit
from Database.models.user import User

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
# from sqlalchemy import text

# from database.connection import SessionLocal
from scraper_manager import scraper_manager
from execution.registry import SCRIPTS_REGISTRY

from routes.admin import router as admin_router

from utils.logging_config import setup_structured_logging, request_id_var
setup_structured_logging()

import sentry_sdk
if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

logger = logging.getLogger("dataops_backend")

import asyncio
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start a background task to fail jobs whose heartbeat is > 5 min old."""
    async def reap_stale_jobs():
        while True:
            try:
                from Database.models.dataset import Dataset
                from Database.models.job import Job
                from services.job_service import JobService
                from Database import db
                
                with db.transaction():
                    now = datetime.now(timezone.utc)
                    cutoff = now - timedelta(minutes=5)
                    stale = (
                        db.session.query(Job)
                        .filter(Job.status.in_(["Queued", "Running"]))
                        .filter((Job.heartbeat_at == None) | (Job.heartbeat_at < cutoff))
                        .all()
                    )
                    
                    if stale:
                        service = JobService()
                        for job in stale:
                            if job.status == "Queued" and job.created_at >= cutoff:
                                continue
                            
                            service.fail(job.id, error_message="Job stalled (heartbeat timeout)", commit=False)
                            if job.dataset_id:
                                ds = db.session.get(Dataset, job.dataset_id)
                                if ds is not None and ds.status == "Running":
                                    ds.status = "Failed"
                        logger.info("Reaped %d stalled job(s)", len(stale))
            except Exception as e:
                logger.warning("Error in stale job reaper: %s", e)
            
            await asyncio.sleep(60)

    task = asyncio.create_task(reap_stale_jobs())
    yield
    task.cancel()

app = FastAPI(
    title="DataOps AI Extraction Backend",
    description="FastAPI service connecting DASNY, NYSCR, JWiz, and Dallas Bonfire scrapers with the AI Agent.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration (Environment-configurable for production with dev fallback)
# In production, set CORS_ORIGINS="https://your-domain.com" explicitly
CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS")
ALLOWED_ORIGINS = (
    [o.strip() for o in CORS_ORIGINS_ENV.split(",") if o.strip()]
    if CORS_ORIGINS_ENV
    else ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ─────────────────────────────────────────────────────
app.include_router(admin_router)

import uuid

@app.middleware("http")
async def context_injection_middleware(request: Request, call_next):
    # Generate and set request ID
    req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    req_id_token = request_id_var.set(req_id)
    
    response = await call_next(request)
    
    # Inject into response headers
    response.headers["x-request-id"] = req_id
    
    request_id_var.reset(req_id_token)
    return response

# Session cleanup middleware — ensures the scoped_session is removed after
# every request so stale sessions never leak across requests on the same thread.
@app.middleware("http")
async def db_session_cleanup(request: Request, call_next):
    response = await call_next(request)
    try:
        from Database.controller import db as _db
        if _db.SessionFactory is not None:
            _db.SessionFactory.remove()
    except Exception:
        pass  # Don't let cleanup failure break the response
    return response


# ---------------------------------------------------------------------------
# Global Exception Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Controlled, frontend-friendly validation error formatting without leaking internals."""
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        errors.append(f"{loc}: {err.get('msg', 'Invalid value')}")
    logger.warning("Validation error on %s: %s", request.url.path, errors)
    from fastapi.encoders import jsonable_encoder
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "; ".join(errors) or "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Centralized safety net preventing stack traces or secrets from leaking in responses."""
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal server error occurred.",
            },
        },
    )


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health/llm")
def llm_health():
    """Return LLM provider configuration status (never exposes keys)."""
    from agents.llm.chat_models import llm_health_check
    return llm_health_check()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class RunScriptRequest(BaseModel):
    scriptId: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="ID of script to run: bonfire, dasny, jwiz, or nyscr",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom parameters (limit, keyword, location, etc.)",
    )


class BotChatRequest(BaseModel):
    sessionId: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Session identifier",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User message text",
    )
    currentRequirement: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional current requirement state",
    )


class BotConfirmRequest(BaseModel):
    sessionId: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Session identifier",
    )
    requirement: Dict[str, Any] = Field(
        ...,
        description="Requirement dictionary",
    )
    preferredScriptId: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional preferred script identifier",
    )


# ---------------------------------------------------------------------------
# Health & Readiness Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health_check():
    """Liveness probe: confirms application process is running."""
    return {
        "status": "healthy",
        "service": "DataOps AI Backend",
        "timestamp": time.time(),
        "registeredScripts": len(SCRIPTS_REGISTRY),
    }


@app.get("/health/ready", tags=["Health"])
def readiness_check():
    """Readiness probe: verifies active PostgreSQL connectivity."""
    try:
        from Database import db
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "timestamp": time.time(),
        }
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Readiness check database failure: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database service unavailable",
        )


# ---------------------------------------------------------------------------
# Script Management Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/scripts", tags=["Scripts"])
def list_scripts(current_user: User = Depends(get_current_user)):
    """Returns all 4 registered scraping scripts with live metadata."""
    return {"scripts": scraper_manager.get_scripts()}


@app.get("/api/scripts/{script_id}", tags=["Scripts"])
def get_script_detail(script_id: str, current_user: User = Depends(get_current_user)):
    script = scraper_manager.get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' not found.")
    return {"script": script}


@app.post("/api/scripts/run", tags=["Scripts"])
def run_script(req: RunScriptRequest, current_user: User = Depends(require_admin), _: None = Depends(enforce_scrape_limit)):
    """Triggers any of the 4 scripts in the background and returns a jobId."""
    script = scraper_manager.get_script(req.scriptId)
    if not script:
        raise HTTPException(status_code=404, detail=f"Unknown script '{req.scriptId}'")

    import uuid
    job_id = scraper_manager.create_job(
        script_id=req.scriptId,
        parameters=req.parameters,
        created_by=current_user.id,
        department_id="dept-sales-1",
        query_id="",
        idempotency_key=str(uuid.uuid4())
    )
    return {
        "success": True,
        "message": f"Execution started for {script['name']}",
        "jobId": job_id,
        "scriptId": req.scriptId,
    }


# ---------------------------------------------------------------------------
# Job Execution & Progress Tracking
# ---------------------------------------------------------------------------

@app.get("/api/jobs", tags=["Jobs"])
def list_jobs(current_user: User = Depends(get_current_user)):
    """Returns list of all scraper jobs (both active and completed)."""
    return {"jobs": scraper_manager.get_jobs()}


@app.get("/api/jobs/{job_id}", tags=["Jobs"])
def get_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Returns real-time status, progress, records count, and logs for a job."""
    job = scraper_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"job": job}


# ---------------------------------------------------------------------------
# Leads and Datasets
# ---------------------------------------------------------------------------

@app.get("/api/datasets", tags=["Datasets"])
def list_datasets(current_user: User = Depends(get_current_user)):
    """Returns datasets created from scraper runs."""
    return {"datasets": scraper_manager.get_datasets()}


@app.get("/api/leads", tags=["Leads"])
def list_leads(
    current_user: User = Depends(get_current_user),
    datasetId: Optional[str] = Query(None, description="Filter by dataset ID"),
    query: Optional[str] = Query(None, description="Search keyword"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Returns leads and opportunities extracted by scrapers."""
    result = scraper_manager.get_leads(dataset_id=datasetId, query=query, page=page, page_size=page_size)
    # Maintain existing shape for frontend compatibility while adding pagination fields
    return {
        "leads": result["items"],
        "total": result["total"],
        "page": result["page"],
        "pageSize": result["pageSize"],
    }


# ---------------------------------------------------------------------------
# AI Agent Bot Integration Endpoints — Layer 5 & 12: routed through AgentOrchestrator
# ---------------------------------------------------------------------------

from agents.graph.runner import run_turn

@app.post("/api/bot/chat", tags=["AI Bot"])
def bot_chat(req: BotChatRequest, current_user: User = Depends(get_current_user)):
    """
    Multi-turn conversational agent endpoint (LangGraph v2).
    """
    return run_turn(current_user, req.sessionId, req.message)


@app.post("/api/bot/confirm-and-generate", tags=["AI Bot"])
def bot_confirm_and_generate(req: BotConfirmRequest, current_user: User = Depends(get_current_user)):
    """
    Called when the user confirms or rejects a scrape proposal.
    Resumes the LangGraph interrupt.
    """
    from agents.graph.graph import get_compiled_graph
    from langgraph.types import Command
    from agents.graph.runner import to_api_response, _get_lock

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": req.sessionId}, "recursion_limit": 25}
    decision = {"decision": "approve", "edits": None, "text": "User clicked Confirm & Generate Data."}

    with _get_lock(req.sessionId):
        out = graph.invoke(Command(resume=decision), config)
        state_dict = graph.get_state(config).values
        job_id = state_dict.get("job_id")
        
        return {
            "success": bool(job_id),
            "jobId": job_id or f"job-{req.sessionId}",
            "scriptId": req.preferredScriptId or "auto",
            "datasetId": f"ds-{req.sessionId}",
            "message": "Scraper initialized successfully." if job_id else "No job was generated."
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
