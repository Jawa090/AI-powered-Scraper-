# AI-Powered Scraper — Complete Codebase Analysis

## 1. Project Overview

This is a **DataOps Autonomous Intelligence Platform** — a full-stack application that:
- Scrapes government procurement portals and commercial directories for business leads
- Stores extracted data in PostgreSQL
- Provides an AI-powered conversational agent for users to request, search, and manage scraped data
- Serves a React + TypeScript frontend dashboard

**Tech Stack:**
| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + TailwindCSS |
| Backend API | FastAPI (Python 3.x) + Uvicorn |
| Database | PostgreSQL + SQLAlchemy 2.x ORM + Alembic migrations |
| Scraping | Selenium WebDriver + Requests + BeautifulSoup |
| AI/LLM | OpenAI-compatible endpoints (Gemini, DeepSeek, NVIDIA NIM) |
| Auth | None (hardcoded user bypass) |

---

## 2. Architecture Diagram

```mermaid
flowchart TD
    subgraph Frontend["Frontend (React + Vite)"]
        UI[React Pages & Components]
        CTX[DataOpsContext + AuthContext]
        API[api.service.ts]
        AGT[agent.service.ts]
    end

    subgraph Backend["Backend (FastAPI)"]
        APP[app.py - FastAPI Routes]
        SM[ScraperManager]
        ORCH[AgentOrchestrator]

        subgraph Execution["Execution Layer"]
            REG[Script Registry]
            DISP[Dispatcher]
            EXEC[JobExecutor]
        end

        subgraph Services["Service Layer"]
            JS[JobService]
            DS[DatasetService]
            LS[LeadService]
            OS[OrgService]
            CS[ContactService]
            SRS[ScrapeRunService]
        end

        subgraph Repos["Repository Layer"]
            BR[BaseRepository]
            JR[JobRepository]
            LR[LeadRepository]
            OR[OrgRepository]
        end

        subgraph Agents["Agent System"]
            INT[IntentEngine]
            QP[QueryParser]
            DAC[DataAvailabilityChecker]
            COLLAB[CollaborationEngine]
            WF[WorkflowPlanner]
            subgraph Specialized["Specialized Agents"]
                SA[SalesAgent]
                DA[DataAgent]
                EA[EmailAgent]
                GA[GrowthAgent]
                RA[ResearchAgent]
                DBA[DatabaseAgent]
                SCA[ScraperAgent]
            end
        end

        subgraph LLM["LLM Layer"]
            LLMF[FallbackLLMProvider]
            OAI[OpenAICompatibleProvider]
        end
    end

    subgraph Scrapers["Scraper Engines"]
        BF[DallasBonfireScraper]
        DSN[DasnyScraper]
        JW[JWiz Extractor]
        NY[NYSCRScraper]
    end

    subgraph DB["PostgreSQL"]
        TABLES[19 Tables]
    end

    UI --> API --> APP
    UI --> AGT --> APP
    APP --> SM --> EXEC --> DISP --> Scrapers
    APP --> ORCH --> Agents
    ORCH --> Services --> Repos --> DB
    EXEC --> Services
    Agents --> LLM
    Agents --> Services
    Scrapers --> DB
```

---

## 3. Data Flow

### 3.1 Scraper Execution Flow

```
User clicks "Run Script" in UI
  → POST /api/scripts/run { scriptId: "bonfire", parameters: { limit: 20 } }
  → app.py: run_script()
  → ScraperManager.create_job()
  → JobExecutor.submit_job()
      1. Validates script_id against SCRIPTS_REGISTRY
      2. Creates Job (Queued) + ScrapeRun (Pending) + Dataset (Running) in PostgreSQL
      3. Spawns daemon thread → _worker()
          a. Transitions Job → Running, ScrapeRun → Running
          b. dispatch_scraper() calls correct adapter (execute_bonfire/jwiz/dasny/nyscr)
          c. Scraper runs headless Chrome / HTTP requests
          d. Raw records returned
          e. standardize_records() normalizes heterogeneous output
          f. validate_records() rejects malformed records
          g. LeadService.ingest_lead_atomic() persists:
             Organization → Contact → Email → Phone → Lead → DatasetRecord
          h. Transitions Job → Completed, ScrapeRun → Completed, Dataset → Completed
```

### 3.2 AI Chat Flow

```
User sends message in Agent chat UI
  → POST /api/bot/chat { sessionId, message, currentRequirement }
  → AgentOrchestrator.handle_message()
      1. Get or create AgentSession in DB
      2. Persist user message as AgentMessage
      3. QueryParser.parse() → NormalizedQuery (category, location, quantity)
      4. Persist Query record
      5. DataAvailabilityChecker.evaluate() → USE_DATABASE / NEED_FETCH / NEED_CLARIFICATION
      6. Update/create Requirement record
      7. IntentEngine.parse() → StructuredIntent
      8. WorkflowPlanner.plan() → WorkflowPlan
      9. Route to appropriate handler:
         - Combined (DB + Scraper) → WorkflowCollaborationEngine
         - Dataset query → DatabaseAgent.search_leads()
         - Scraper trigger → ScraperAgent via JobExecutor
         - Sales/Email/Growth → Specialized agent
      10. Persist assistant AgentMessage
      11. Return structured BotChatResponse
```

### 3.3 Confirm & Generate Flow

```
User clicks "Confirm & Generate" in chat
  → POST /api/bot/confirm-and-generate { sessionId, requirement, preferredScriptId }
  → AgentOrchestrator.confirm_and_generate()
      1. Validate requirement + resolve script
      2. ScraperManager.create_job() → Job dispatched in background
      3. Return jobId to frontend for polling
```

---

## 4. Control Flow — Key Decision Points

### 4.1 Script Selection (registry.py: `recommend_scraper()`)
```
If text mentions "bonfire"/"city hall" → bonfire
If text mentions "dasny"/"dormitory" → dasny
If text mentions "nyscr"/"contract reporter" → nyscr
If text mentions "jwiz"/"directory" → jwiz
If text is procurement/RFP/bid:
    Dallas/Texas location → bonfire
    Otherwise → dasny
Default → jwiz
```

### 4.2 Agent Selection (registry.py: `select_agent()`)
```
Priority: sales → data → email → growth → research
Each agent's can_handle() is evaluated in order.
First match wins. No match → NEED_CLARIFICATION.
```

### 4.3 Orchestrator Routing (orchestrator.py)
```
1. Combined route (DB + scraper compare) → WorkflowCollaborationEngine
2. Dataset query route → DatabaseAgent
3. Scraper trigger route → ScraperAgent
4. Sales/email/collaboration route → Specialized agent
5. Default fallback → Simple response with suggestions
```

---

## 5. Database Schema (19 Tables)

| Table | Purpose | Key Relationships |
|---|---|---|
| `departments` | Organizational units | → users, agents, sessions, datasets, jobs, leads |
| `users` | Platform users | → department, leads, datasets, jobs |
| `agents` | AI agent definitions | → department, sessions, actions |
| `agent_sessions` | Chat sessions | → agent, department, messages, requirements, queries |
| `agent_messages` | Chat history | → session |
| `requirements` | Data requirement tracking | → session, department, dataset |
| `queries` | Normalized query records | → session, user, source, scrape_runs, jobs |
| `sources` | Scraper engine definitions | → scrape_runs, jobs, organizations |
| `scrape_runs` | Individual scrape executions | → source, job, query, organizations, leads |
| `jobs` | Background execution jobs | → source, department, user, dataset, query, scrape_runs |
| `datasets` | Collections of scraped data | → department, user, records, leads, jobs |
| `dataset_records` | Links leads to datasets | → dataset, organization, contact, lead |
| `organizations` | Scraped companies | → source, scrape_run, contacts, emails, phones, locations, leads |
| `contacts` | Scraped people | → organization, source, scrape_run, emails, phones, leads |
| `emails` | Email addresses | → organization, contact, source |
| `phones` | Phone numbers | → organization, contact, source |
| `locations` | Physical addresses | → organization, source |
| `leads` | Sales pipeline records | → organization, contact, dataset, department, user, source, scrape_run, actions |
| `agent_actions` | Agent audit trail | → session, agent, user, lead |

---

## 6. Vulnerabilities & Security Issues

### 🔴 CRITICAL

| # | Issue | Location | Description |
|---|---|---|---|
| V1 | **Hardcoded DB password committed to VCS** | [.env](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/.env#L11) | `DATABASE_URL=postgresql+psycopg://postgres:1234@localhost:5432/dataops` — The actual `.env` file with the real password `1234` is tracked in git. The `.gitignore` has `.env.*` but also `!.env.example`, and the `.env` itself appears to be committed. |
| V2 | **No authentication at all** | [app.py](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/app.py) | Zero auth middleware. Every API endpoint is completely open — no JWT, no session cookies, no API keys. Anyone with network access can trigger scrapers, read all leads, and impersonate any user. |
| V3 | **CORS wildcard in production** | [app.py:44-57](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/app.py#L44-L57) | If `CORS_ORIGINS` is unset, the fallback is `["*"]` — any origin can make authenticated requests with `allow_credentials=True`. This is a dangerous combination per CORS spec. |
| V4 | **Hardcoded user identity everywhere** | [scraper_manager.py:158-159](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/scraper_manager.py#L158-L159), [contract.py:27-28](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/contract.py#L27-L28) | `department_id="dept-sales-1"`, `created_by="usr-ahmed"` are hardcoded defaults. Every job looks like it was created by "Ahmed Khan". No real user context propagation. |
| V5 | **SQL injection via unvalidated filter keys** | [base.py (repositories):76-88](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/repositories/base.py#L76-L88) | `BaseRepository.list()` accepts a `filters` dict and uses `getattr(self.model, column_name)` to build WHERE clauses. If an attacker controls filter keys, they could access relationship attributes or ORM internals. While SQLAlchemy parameterizes values, the column name lookup itself is unvalidated against a whitelist. |
| V6 | **SQL injection in setup_db.py** | [setup_db.py:60](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/setup_db.py#L60) | `cur.execute(f'CREATE DATABASE "{target_db}"')` — the database name is formatted into SQL via f-string. If `DATABASE_URL` is attacker-controlled, this is a direct SQL injection vector. |

### 🟠 HIGH

| # | Issue | Location | Description |
|---|---|---|---|
| V7 | **No rate limiting** | [app.py](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/app.py) | No rate limiting on any endpoint. The `/api/bot/chat` and `/api/scripts/run` endpoints can be abused to: (a) flood the LLM API, (b) spawn unlimited scraper threads, (c) fill the database. |
| V8 | **Unbounded thread spawning** | [executor.py:120-127](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/executor.py#L120-L127) | `threading.Thread(daemon=True)` is created for each job with no concurrency limit. An attacker could POST `/api/scripts/run` thousands of times to exhaust system resources (threads, memory, Chrome processes). |
| V9 | **LLM API key exposure risk** | [agents/llm/factory.py](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/agents/llm/factory.py) | While keys are masked in health checks, the `OpenAICompatibleProvider` stores the raw API key in memory and passes it in HTTP headers. If `exc_info=True` logging (used in [app.py:116](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/app.py#L116)) captures provider errors, keys could leak to log files. |
| V10 | **Frontend login bypass** | [App.tsx:36](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/AI%20Powered/src/App.tsx#L36) | `const [isLoggedIn, setIsLoggedIn] = useState(true);` — Login is permanently bypassed. The Login page exists but is never shown. |
| V11 | **`on_event("startup")` deprecated** | [app.py:60](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/app.py#L60) | `@app.on_event("startup")` is deprecated in FastAPI. Should use `lifespan` context manager instead. |

### 🟡 MEDIUM

| # | Issue | Location | Description |
|---|---|---|---|
| V12 | **Path traversal via job_id/script_id** | [app.py:268](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/app.py#L268) | Path parameters like `{job_id}` are passed directly to DB lookups. While SQLAlchemy parameterizes them, the string pattern `f"job-{int(time.time())}-{uuid.uuid4().hex[:4]}"` means IDs are predictable within a time window. |
| V13 | **No input sanitization on lead metadata** | [lead_service.py:250](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/services/lead_service.py#L250) | `lead_metadata` is stored as raw JSONB with no schema validation. Scrapers could inject arbitrary data structures. |
| V14 | **Selenium WebDriver left open on crash** | [dispatcher.py:57-90](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/dispatcher.py#L57-L90) | While `try/finally` blocks call `scraper.close()`, if the thread is killed by the OS or the process crashes, Chrome processes are orphaned. |
| V15 | **No HTTPS enforcement** | [run_server.py:14](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/run_server.py#L14) | Server binds on `0.0.0.0:8000` with plain HTTP. No TLS configuration. API keys, credentials, and scraped PII flow in cleartext. |

---

## 7. Bugs & Code Issues

### 🔴 Functional Bugs

| # | Bug | Location | Description |
|---|---|---|---|
| B1 | **Telemetry callback signature mismatch** | [dispatcher.py:137](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/dispatcher.py#L137) | `telemetry(35, ..., records_found=0)` passes `records_found` as kwarg, but `TelemetryCallback` type hint is `Callable[[int, str, str, str], None]` — only 4 positional args. The actual closure in [executor.py:153](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/executor.py#L153) accepts `records_found` as an optional kwarg, so it works at runtime, but the type contract is wrong. |
| B2 | **`source_id` FK violation potential** | [executor.py:95-96](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/executor.py#L95-L96) | `source_id=script_id` — Job's `source_id` FK points to `sources.id`, but `script_id` values are "bonfire", "dasny", etc. These only work if `seed.py` has been run to create Source rows with `id=script_id`. If seed data is missing, this causes an FK violation crash. |
| B3 | **Race condition in job active tracking** | [executor.py:38-50](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/executor.py#L38-L50) | `_active_jobs` is protected by a lock, but `get_active_job_for_script()` iterates the dict while other threads may modify it (the `for j_id, s_id in self._active_jobs.items()` is inside the lock, which is correct — but the result is stale by the time the caller uses it). |
| B4 | **Duration calculation timezone mismatch** | [job_service.py:196](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/services/job_service.py#L196) | `(now - existing.started_at).total_seconds()` — `now` is `datetime.now(timezone.utc)` but `existing.started_at` may be timezone-naive depending on the PostgreSQL driver, leading to incorrect duration or `TypeError`. |
| B5 | **`expire_on_commit=False` risks stale data** | [connection.py:65](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/database/connection.py#L65) | `expire_on_commit=False` means ORM objects retain their in-memory state after commit. In multi-threaded contexts (scraper worker threads), this can serve stale attribute values if another thread modifies the same row. |

### 🟠 Logic Issues

| # | Issue | Location | Description |
|---|---|---|---|
| B6 | **Duplicate dataset creation** | [executor.py:70-84, 192-208](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/executor.py#L70-L84) | Dataset is created both in `submit_job()` (line 74) and again checked/created in `_worker()` (line 197). While idempotent, the double-creation logic is fragile and confusing. |
| B7 | **JWiz pagination yields wrong max_pages** | [dispatcher.py:119](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/execution/dispatcher.py#L119) | `max_pages = max(1, (limit + 99) // 100)` — For `limit=25`, this gives `max_pages=1` which is fine, but for `limit=150`, it gives `max_pages=2` instead of the expected `2` (correct by coincidence). The real issue: if JWiz returns fewer than 100 results per page, the loop may under-fetch. |
| B8 | **Hardcoded "Sales 1" department** | [scraper_manager.py:197,224,276](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/scraper_manager.py#L197) | Multiple serialization methods hardcode `"departmentName": "Sales 1"` and `"assignedToName": "Ahmed Khan"` instead of resolving from the database. |
| B9 | **Lead search location always "USA"** | [scraper_manager.py:269](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/scraper_manager.py#L269) | `_serialize_db_lead()` hardcodes `"location": "USA"` instead of reading from the organization's locations relationship. |
| B10 | **Orchestrator is 2294 lines — God Object** | [orchestrator.py](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/agents/orchestrator.py) | At 121KB and 2294 lines, the orchestrator is a massive monolith containing routing logic, response formatting, requirement management, and collaboration coordination all in one class. This makes it extremely difficult to test, maintain, or modify safely. |

---

## 8. Design Observations

### ✅ Strengths

1. **No synthetic data policy** — The codebase explicitly avoids fabricating phone/email data when scraping returns None. This is well-documented and consistently enforced across all dispatcher adapters.

2. **Clean layered architecture** — Repositories → Services → Execution → API follows proper separation of concerns. Repos only flush; Services own commits.

3. **Script registry as whitelist** — Only 4 registered scrapers can execute. No arbitrary file path execution is possible.

4. **Interrupted job recovery** — On server restart, stale Running/Queued jobs are marked Failed ([app.py:60-85](file:///c:/Users/adil.zia/Desktop/Tasks/Task2/AI-powered-Scraper-/Backend/app.py#L60-L85)).

5. **LLM provider fallback chain** — Graceful degradation across Gemini → DeepSeek → NVIDIA NIM with proper status tracking.

6. **Comprehensive ORM model design** — 19 well-normalized tables with proper FK relationships, cascades, and indexes.

7. **Record validation before persistence** — `validate_records()` rejects malformed emails/URLs before database writes.

### ⚠️ Weaknesses

1. **Zero authentication** — Most critical gap. No JWT, OAuth, session management, or API key auth exists anywhere.

2. **No test suite** — The `tests/` directory is completely empty (only `__pycache__`).

3. **45 chunk files in root** — `chunk_1.txt` through `chunk_45.txt` are large text files (~1.5MB total) in the project root with no clear purpose and no `.gitignore` exclusion.

4. **No logging to persistent storage** — Logging goes to stdout only. No log rotation, no structured JSON logging, no centralized log aggregation.

5. **No API versioning** — All endpoints are under `/api/` with no version prefix.

6. **No pagination on list endpoints** — `/api/jobs`, `/api/datasets`, `/api/leads` return all records (up to internal limits) with no cursor/offset pagination exposed to the frontend.

7. **Custom routing instead of React Router** — Frontend uses `window.history.pushState` and string matching instead of a proper router library, making deep linking fragile.

---

## 9. File Inventory Summary

| Directory | Files | Purpose |
|---|---|---|
| `Backend/` | 14 root files | API server, scraper engines, setup scripts |
| `Backend/database/` | 4 + 19 model files | ORM layer |
| `Backend/repositories/` | 15 files | Data access layer |
| `Backend/services/` | 10 files | Business logic layer |
| `Backend/execution/` | 5 files | Job execution pipeline |
| `Backend/agents/` | ~30+ files across 9 subdirs | AI agent system |
| `AI Powered/src/` | ~40+ files | React frontend |
| Root | 45 chunk files + config | Misc data dumps + project config |

**Total estimated lines of code: ~15,000+ (Backend) + ~5,000+ (Frontend)**
