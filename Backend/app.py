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
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from database.connection import SessionLocal
from scraper_manager import scraper_manager
from execution.registry import SCRIPTS_REGISTRY
from agents.orchestrator import agent_orchestrator

# Configure production logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dataops_backend")

app = FastAPI(
    title="DataOps AI Extraction Backend",
    description="FastAPI service connecting DASNY, NYSCR, JWiz, and Dallas Bonfire scrapers with the AI Agent.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration (Environment-configurable for production with dev fallback)
CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS")
ALLOWED_ORIGINS = (
    [o.strip() for o in CORS_ORIGINS_ENV.split(",") if o.strip()]
    if CORS_ORIGINS_ENV
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def fail_interrupted_jobs() -> None:
    """
    Jobs run on in-process threads, so anything still Queued/Running when the
    server starts was killed by the previous shutdown. Close those out as
    Failed instead of leaving them "Running" forever.
    """
    from database.models.dataset import Dataset  # noqa: PLC0415
    from database.models.job import Job  # noqa: PLC0415
    from services.job_service import JobService  # noqa: PLC0415

    try:
        with SessionLocal() as db:
            stale = db.query(Job).filter(Job.status.in_(["Queued", "Running"])).all()
            service = JobService(db)
            for job in stale:
                service.fail(job.id, "Interrupted: server restarted before the job finished", commit=False)
                if job.dataset_id:
                    ds = db.get(Dataset, job.dataset_id)
                    if ds is not None and ds.status == "Running":
                        ds.status = "Failed"
            db.commit()
            if stale:
                logger.info("Marked %d interrupted job(s) as Failed", len(stale))
    except Exception as exc:  # never block startup on housekeeping
        logger.warning("Could not reconcile interrupted jobs: %s", exc)


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
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "; ".join(errors) or "Request validation failed.",
                "details": exc.errors(),
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
    history: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional conversation history",
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
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
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
def list_scripts():
    """Returns all 4 registered scraping scripts with live metadata."""
    return {"scripts": scraper_manager.get_scripts()}


@app.get("/api/scripts/{script_id}", tags=["Scripts"])
def get_script_detail(script_id: str):
    script = scraper_manager.get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' not found.")
    return {"script": script}


@app.post("/api/scripts/run", tags=["Scripts"])
def run_script(req: RunScriptRequest):
    """Triggers any of the 4 scripts in the background and returns a jobId."""
    script = scraper_manager.get_script(req.scriptId)
    if not script:
        raise HTTPException(status_code=404, detail=f"Unknown script '{req.scriptId}'")

    job_id = scraper_manager.create_job(req.scriptId, req.parameters)
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
def list_jobs():
    """Returns list of all scraper jobs (both active and completed)."""
    return {"jobs": scraper_manager.get_jobs()}


@app.get("/api/jobs/{job_id}", tags=["Jobs"])
def get_job(job_id: str):
    """Returns real-time status, progress, records count, and logs for a job."""
    job = scraper_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"job": job}


# ---------------------------------------------------------------------------
# Leads and Datasets
# ---------------------------------------------------------------------------

@app.get("/api/datasets", tags=["Datasets"])
def list_datasets():
    """Returns datasets created from scraper runs."""
    return {"datasets": scraper_manager.get_datasets()}


@app.get("/api/leads", tags=["Leads"])
def list_leads(
    datasetId: Optional[str] = Query(None, description="Filter by dataset ID"),
    query: Optional[str] = Query(None, description="Search keyword"),
):
    """Returns leads and opportunities extracted by scrapers."""
    leads = scraper_manager.get_leads(dataset_id=datasetId, query=query)
    return {"leads": leads, "total": len(leads)}


# ---------------------------------------------------------------------------
# AI Agent Bot Integration Endpoints — Layer 5 & 12: routed through AgentOrchestrator
# ---------------------------------------------------------------------------

@app.post("/api/bot/chat", tags=["AI Bot"])
def bot_chat(req: BotChatRequest):
    """
    Multi-turn conversational agent endpoint.
    Delegates fully to AgentOrchestrator which handles:
      - Query normalization
      - DB-first data availability decision
      - Task decomposition & Multi-Agent Collaboration (Layer 12)
      - Specialized Agent execution (Sales, Data, Research, Email, Growth)
      - Session & message persistence
      - Requirement tracking
    Response is fully compatible with the React frontend BotChatResponse contract.
    """
    return agent_orchestrator.handle_message(
        session_id=req.sessionId,
        message=req.message,
        current_requirement=req.currentRequirement,
    )


@app.post("/api/bot/confirm-and-generate", tags=["AI Bot"])
def bot_confirm_and_generate(req: BotConfirmRequest):
    """
    Called when the user clicks 'Confirm & Generate Data' in the bot UI.
    Delegates to AgentOrchestrator.confirm_and_generate which enforces the
    execution boundary (Orchestrator → Job Service → Execution Layer → Scraper).
    """
    return agent_orchestrator.confirm_and_generate(
        session_id=req.sessionId,
        requirement_data=req.requirement,
        preferred_script_id=req.preferredScriptId,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
