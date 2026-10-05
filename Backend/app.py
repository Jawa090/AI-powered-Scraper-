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

import _paths
from settings import settings

from fastapi import Depends
from services.auth import get_current_user, require_admin
from Database.models.user import User

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from scraper_manager import scraper_manager
from execution.registry import SCRIPTS_REGISTRY

from routes.admin import router as admin_router

from utils.logging_config import setup_structured_logging, request_id_var
setup_structured_logging()

import sentry_sdk
import re

def _mask_sentry_pii(event, hint):
    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    PHONE_REGEX = re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b")
    if "message" in event and isinstance(event["message"], str):
        event["message"] = EMAIL_REGEX.sub("[EMAIL_MASKED]", event["message"])
        event["message"] = PHONE_REGEX.sub("[PHONE_MASKED]", event["message"])
    return event

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        send_default_pii=False,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        before_send=_mask_sentry_pii,
    )

logger = logging.getLogger("dataops_backend")

import asyncio
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from Database.controller import session_scope
    from services.auth import sync_env_users
    
    with session_scope() as session:
        sync_env_users(session)

    try:
        from agents.graph.checkpointer import setup_checkpointer
        setup_checkpointer()
    except Exception as e:
        logger.warning("Checkpointer setup warning: %s", e)

    yield

    try:
        from agents.graph.checkpointer import pool
        pool.close()
    except Exception:
        pass

app = FastAPI(
    title="DataOps AI Extraction Backend",
    description="FastAPI service connecting DASNY, NYSCR, JWiz, and Dallas Bonfire scrapers with the AI Agent.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ─────────────────────────────────────────────────────
from routes.auth import router as auth_router
from routes.admin import router as admin_router
from routes.bot import router as bot_router

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin_router)
app.include_router(bot_router)

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


from agents.llm.chat_model import LLMUnavailable


@app.exception_handler(LLMUnavailable)
async def llm_unavailable_exception_handler(request: Request, exc: LLMUnavailable):
    """Handles LLM unavailable errors conforming to Decision D4 (HTTP 503)."""
    logger.error("LLM unavailable (%s): %s", exc.reason, exc.detail)
    return exc.to_response()


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
def llm_health(probe: bool = Query(False, description="Run probe call")):
    """Return LLM provider configuration status (never exposes keys)."""
    from agents.llm.chat_model import llm_health_check
    return llm_health_check(probe_mode=probe)


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
        from Database.controller import session_scope
        from sqlalchemy import text
        with session_scope() as session:
            session.execute(text("SELECT 1"))
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


# ---------------------------------------------------------------------------
# Job Execution & Progress Tracking
# ---------------------------------------------------------------------------

@app.get("/api/jobs", tags=["Jobs"])
def list_jobs(current_user: User = Depends(get_current_user)):
    """Returns list of all scraper jobs (both active and completed)."""
    return {"jobs": scraper_manager.get_jobs(current_user)}


@app.get("/api/jobs/{job_id}", tags=["Jobs"])
def get_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Returns real-time status, progress, records count, and logs for a job."""
    job = scraper_manager.get_job(job_id, current_user)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"job": job}


@app.post("/api/jobs/{job_id}/cancel", tags=["Jobs"])
def cancel_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Cancels a job if it belongs to the user or if the user is an admin."""
    job = scraper_manager.get_job(job_id, current_user)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    
    from Database.controller import session_scope
    from Database.models.job import Job
    with session_scope() as session:
        db_job = session.get(Job, job_id)
        if db_job.status in ["Queued", "Running", "WaitingForUser"]:
            db_job.status = "Cancelled"
            session.commit()
            return {"message": "Job cancelled successfully."}
        return {"message": "Job cannot be cancelled in its current state."}


# ---------------------------------------------------------------------------
# Leads and Datasets
# ---------------------------------------------------------------------------

@app.get("/api/datasets", tags=["Datasets"])
def list_datasets(current_user: User = Depends(get_current_user)):
    """Returns datasets created from scraper runs."""
    return {"datasets": scraper_manager.get_datasets(current_user)}


@app.get("/api/leads", tags=["Leads"])
def list_leads(
    current_user: User = Depends(get_current_user),
    datasetId: Optional[str] = Query(None, description="Filter by dataset ID"),
    query: Optional[str] = Query(None, description="Search keyword"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Returns leads and opportunities extracted by scrapers."""
    result = scraper_manager.get_leads(current_user, dataset_id=datasetId, query=query, page=page, page_size=page_size)
    return {
        "leads": result["items"],
        "total": result["total"],
        "page": result["page"],
        "pageSize": result["pageSize"],
    }


@app.get("/api/leads/export.csv", tags=["Leads"])
def export_leads_csv(
    current_user: User = Depends(get_current_user),
    datasetId: Optional[str] = Query(None, description="Filter by dataset ID"),
    query: Optional[str] = Query(None, description="Search keyword"),
):
    """Streams leads as a CSV export scoped per D9."""
    import csv
    import io
    from fastapi.responses import StreamingResponse
    from Database.controller import session_scope
    from Database.models.lead import Lead
    from Database.models.organization import Organization
    from Database.models.contact import Contact
    from Database.models.dataset import DatasetRecord
    from services.visibility import apply_lead_scope
    from routes.serializers import serialize_lead
    from sqlalchemy import select, or_
    from sqlalchemy.orm import selectinload

    with session_scope() as session:
        stmt = select(Lead).options(
            selectinload(Lead.organization).selectinload(Organization.locations),
            selectinload(Lead.organization).selectinload(Organization.emails),
            selectinload(Lead.organization).selectinload(Organization.phones),
            selectinload(Lead.contact).selectinload(Contact.emails),
            selectinload(Lead.contact).selectinload(Contact.phones),
        )
        stmt = apply_lead_scope(stmt, current_user)

        if datasetId:
            stmt = stmt.join(DatasetRecord, DatasetRecord.lead_id == Lead.id)
            stmt = stmt.where(DatasetRecord.dataset_id == datasetId)

        if query:
            q = f"%{query}%"
            stmt = stmt.outerjoin(Organization, Lead.organization_id == Organization.id)
            stmt = stmt.outerjoin(Contact, Lead.contact_id == Contact.id)
            stmt = stmt.where(or_(
                Contact.full_name.ilike(q),
                Organization.name.ilike(q),
                Lead.title.ilike(q),
                Lead.notes.ilike(q),
            ))

        db_leads = list(session.scalars(stmt.order_by(Lead.created_at.desc())).all())
        serialized_items = [serialize_lead(l) for l in db_leads]

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Name", "Company", "Title", "Email", "Phone",
            "Location", "City", "State", "Source Code", "Due At",
            "Status", "Website", "Industry", "Created At"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for item in serialized_items:
            writer.writerow([
                item.get("id") or "",
                item.get("name") or "",
                item.get("company") or "",
                item.get("title") or "",
                item.get("email") or "",
                item.get("phone") or "",
                item.get("location") or "",
                item.get("city") or "",
                item.get("state") or "",
                item.get("sourceCode") or "",
                item.get("dueAt") or "",
                item.get("status") or "",
                item.get("website") or "",
                item.get("industry") or "",
                item.get("createdAt") or "",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
