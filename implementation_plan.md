# AI-Powered Scraper — Implementation Plan

This document outlines a comprehensive, prioritized implementation plan to resolve all critical security vulnerabilities, functional bugs, logic issues, and design flaws identified in the codebase audit. 

## Phase 1: Security & Authentication (Critical & High Priority)

**Goal:** Secure the application boundaries, remove hardcoded credentials, and prevent SQL injection.

| Task | Target Files | Implementation Details |
|---|---|---|
| **1.1. Remove Hardcoded DB Secrets** | `Backend/.env`, `Backend/.gitignore` | 1. Remove `.env` from git tracking (`git rm --cached Backend/.env`).<br>2. Update `.gitignore` to explicitly ignore `.env`.<br>3. Rotate the database password immediately.<br>4. Provide a sanitized `.env.example`. |
| **1.2. Implement Authentication Middleware** | `Backend/app.py`, `Frontend/App.tsx` | 1. Implement JWT-based authentication in FastAPI (e.g., using `fastapi-users` or basic custom JWT middleware).<br>2. Secure all `/api/` endpoints with `Depends(get_current_user)`.<br>3. Remove frontend `isLoggedIn = true` bypass and implement actual login screen. |
| **1.3. Secure CORS Configuration** | `Backend/app.py` | 1. Change `ALLOWED_ORIGINS` fallback from `["*"]` to `[]` or explicit localhost ports when running in production.<br>2. Document how to set `CORS_ORIGINS` properly in `.env`. |
| **1.4. Fix SQL Injection Vectors** | `Database/repositories/base.py`, `Backend/setup_db.py` | 1. In `base.py:list()`, validate `column_name` against `self.model.__table__.columns.keys()` before `getattr()`.<br>2. In `setup_db.py`, use parameterized queries or SQLAlchemy management functions instead of f-strings for database names. |
| **1.5. LLM API Key Security** | `Backend/agents/llm/factory.py` | 1. Ensure keys are not stored in raw class attributes where `exc_info=True` might log them.<br>2. Mask keys in logs explicitly. |

## Phase 2: Threading, Performance & DB Concurrency (High & Medium Priority)

**Goal:** Prevent server crashes, memory leaks, and race conditions during high-volume scraper job execution.

| Task | Target Files | Implementation Details |
|---|---|---|
| **2.1. Thread Pool & Rate Limiting** | `Backend/execution/executor.py`, `Backend/app.py` | 1. Replace unbounded `threading.Thread` with `concurrent.futures.ThreadPoolExecutor(max_workers=N)`.<br>2. Implement basic rate limiting (e.g., using `slowapi`) on `/api/scripts/run` to prevent queue flooding. |
| **2.2. Fix DB Race Conditions & Stale Data** | `Database/connection.py`, `Backend/execution/executor.py` | 1. Remove `expire_on_commit=False` in `connection.py` or scope it strictly to read-only queries.<br>2. In `executor.py`, fix the lock on `_active_jobs` to safely iterate and return the active job without race conditions. |
| **2.3. Scraper Cleanup (Orphaned Chrome)** | `Backend/execution/dispatcher.py` | 1. Wrap entire thread execution in a robust `try...finally`.<br>2. Add a global `atexit` or `lifespan` handler to force-kill lingering Chromium processes on app shutdown. |
| **2.4. Fix Telemetry Signature Mismatch** | `Backend/execution/dispatcher.py` | 1. Correct the `TelemetryCallback` type alias to accept `records_found` as a named argument, matching its usage. |
| **2.5. Timezone Calculation Fix** | `Backend/services/job_service.py` | 1. Standardize all `datetime.now()` calls to use `timezone.utc`.<br>2. Ensure PostgreSQL columns are `TIMESTAMP WITH TIME ZONE`. |

## Phase 3: Logic Fixes & Refactoring (Medium Priority)

**Goal:** Fix business logic errors and decompose monolithic classes for better maintainability.

| Task | Target Files | Implementation Details |
|---|---|---|
| **3.1. Decompose Orchestrator (God Object)** | `Backend/agents/orchestrator.py` | 1. Split `AgentOrchestrator` (2294 lines) into separate modules: `QueryRouter`, `SessionManager`, `ResponseFormatter`.<br>2. Use a Factory pattern to route to specialized agents rather than keeping routing logic centralized. |
| **3.2. Fix `source_id` FK Violation** | `Backend/execution/executor.py` | 1. Ensure `script_id` is mapped to a valid `Source` record ID before job creation, or auto-seed the database if missing. |
| **3.3. Remove Hardcoded Logic** | `Backend/scraper_manager.py` | 1. Remove hardcoded "Sales 1" and "Ahmed Khan" identities. Retrieve real `Department` and `User` contexts from the authenticated JWT token.<br>2. Read "location" dynamically from relationships instead of hardcoding "USA". |
| **3.4. Fix JWiz Pagination Logic** | `Backend/execution/dispatcher.py` | 1. Fix the pagination math. Use a `while` loop that checks the number of results returned per page, breaking if it's less than expected, rather than pre-calculating `max_pages`. |
| **3.5. Resolve Duplicate Dataset Creation** | `Backend/execution/executor.py` | 1. Ensure dataset creation only happens once in `submit_job()` and is simply retrieved by `_worker()`. |

## Phase 4: API & Frontend Polish

**Goal:** Improve API usability and frontend stability.

| Task | Target Files | Implementation Details |
|---|---|---|
| **4.1. Replace Startup Event** | `Backend/app.py` | 1. Replace `@app.on_event("startup")` with a `lifespan` context manager as per modern FastAPI best practices. |
| **4.2. API Versioning & Pagination** | `Backend/app.py` | 1. Add `/v1/` prefix to all routes.<br>2. Add cursor or offset pagination parameters to list endpoints (`/jobs`, `/leads`, `/datasets`). |
| **4.3. Frontend Routing & Auth Enforcement** | `AI Powered/src/*` | 1. Introduce `react-router-dom` for reliable browser history.<br>2. Implement proper routing guards (`<ProtectedRoute>`) enforcing valid authentication tokens. |
| **4.4. Cleanup Chunks** | Root Directory | 1. Delete `chunk_*.txt` files if they are just data dumps, or move them to a `data/` or `logs/` directory and add to `.gitignore`. |

---
**Execution Strategy:**
Start with Phase 1 immediately to secure the system boundaries. Proceed to Phase 2 to ensure stability under load. Finally, implement Phase 3 and 4 to ensure the codebase remains maintainable as the project grows.
