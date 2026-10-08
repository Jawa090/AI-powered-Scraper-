"""
FastAPI Server for DataOps Autonomous Intelligence Platform
Wraps 4 scraping engines, manages background job queues, provides REST APIs,
and connects seamlessly with the frontend AI Agent Bot.

Layer 13: Production Readiness, API Hardening & Health Monitoring.
"""
import logging
import time

import _paths
from settings import settings

from fastapi import FastAPI, HTTPException, Request, Query, Depends
from fastapi.security import HTTPBearer
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes.admin import router as admin_router

from utils.logging_config import setup_structured_logging, request_id_var
setup_structured_logging()

import sentry_sdk
from utils.pii import mask_text as _mask_pii_text

def _mask_sentry_pii(event, hint):
    from utils.pii import mask_payload
    return mask_payload(event)

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        send_default_pii=False,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        before_send=_mask_sentry_pii,
        max_request_body_size="never",
        include_local_variables=False,
    )

logger = logging.getLogger("dataops_backend")

import asyncio
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from Database.seed import seed
    seed()
    from agents.graph.checkpointer import setup_checkpointer
    setup_checkpointer()
    from services.worker_runtime import start_local_supervisor
    worker_supervisor = start_local_supervisor()

    yield
    worker_supervisor.set()

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
from routes.rag_proxy import router as rag_proxy_router
from routes.scripts import router as scripts_router
from routes.jobs import router as jobs_router
from routes.datasets import router as datasets_router
from routes.leads import router as leads_router

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin_router)
app.include_router(bot_router)
app.include_router(rag_proxy_router)
app.include_router(scripts_router)
app.include_router(jobs_router)
app.include_router(datasets_router)
app.include_router(leads_router)

import uuid

@app.middleware("http")
async def context_injection_middleware(request: Request, call_next):
    # Generate and set request ID
    req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    req_id_token = request_id_var.set(req_id)
    
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers['x-request-id'] = req_id
        logger.info('request_complete', extra={'path': request.url.path, 'status': response.status_code,
            'duration_ms': round((time.perf_counter() - started)*1000, 2)})
        return response
    finally:
        request_id_var.reset(req_id_token)



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
                "details": [{"type": err.get("type"), "loc": list(err.get("loc", [])), "message": err.get("msg")} for err in exc.errors()],
            },
        },
    )


from agents.llm.chat_model import LLMUnavailable


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    content = exc.detail if isinstance(exc.detail, dict) and 'error' in exc.detail else {'detail': exc.detail}
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


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
def llm_health(probe: bool = Query(False, description="Run probe call"), credentials=Depends(HTTPBearer(auto_error=False))):
    """Return LLM provider configuration status (never exposes keys)."""
    from agents.llm.chat_model import llm_health_check
    if probe:
        from services.auth import get_current_user
        from Database.controller import session_scope
        if not credentials:
            raise HTTPException(401, 'Authentication is required for a provider probe.')
        with session_scope() as db:
            if get_current_user(credentials, db).role != 'admin':
                raise HTTPException(403, 'Administrator access is required.')
    return llm_health_check(probe_mode=probe)



# ---------------------------------------------------------------------------
# Health & Readiness Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health_check():
    """Liveness probe: confirms application process is running."""
    from scrappers.controller import scraper_ids
    return {
        "status": "healthy",
        "service": "DataOps AI Backend",
        "timestamp": time.time(),
        "registeredScripts": len(scraper_ids()),
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



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
