# PHASE 1 — SCRAPER ARCHITECTURE AUDIT
**Date:** 2026-09-23
**Scope:** Backend only — READ-ONLY audit
**Auditor:** Antigravity IDE Agent
**Repository root:** `AI-powered-Scraper-/Backend/`

---

## 1. High-Level Runtime Architecture

```
React Frontend (AI Powered/)
        |  HTTP POST /api/bot/chat
        |  HTTP POST /api/bot/confirm-and-generate
        |  HTTP GET  /api/scripts, /api/jobs, /api/datasets, /api/leads
        v
[app.py  FastAPI/Uvicorn  Port 8000]  <- entry: run_server.py
          |
          +---> scraper_manager.scraper_manager   (singleton)
          +---> agents.orchestrator.agent_orchestrator  (singleton)
                        |
              [AgentOrchestrator  agents/orchestrator.py  1,230 lines]
                       |                  |
              [QueryParser]      [DataAvailabilityChecker]
              [agents/query/]    [agents/decisions/]
                                          |
                                  DecisionType:
                                    USE_DATABASE
                                    NEED_FETCH
                                    NEED_CLARIFICATION
                       |
              [Multi-Agent Collaboration Layer 12]
              [CollaborationPlanner / CollaborationEngine]
              [agents/collaboration/]
                     |
              [AgentRegistry.select_agent()]
              [Priority: sales->data->email->growth->research]
              [5 Specialized Agents agents/specialized/]
                     |
              [scraper_manager.create_job()]  <- JOB TRIGGER
              [ScraperManager scraper_manager.py]
                     |
              [ExecutionRequest -> job_executor.submit_job()]
              [JobExecutor execution/executor.py daemon thread]
                     |
              [dispatch_scraper() execution/dispatcher.py]
                4 adapters:
                  execute_bonfire() -> DallasBonfireScraper
                  execute_jwiz()    -> jwiz.py functions
                  execute_dasny()   -> DasnyScraper
                  execute_nyscr()   -> NYSCRScraper
                     |
              [Services Layer services/]
              [JobService, DatasetService, LeadService, ScrapeRunService]
                     |
              [PostgreSQL via DATABASE_URL in .env]
              [19 models  database/models/]
```

---

## 2. Entry Points

| File | Role | Active? |
|------|------|---------|
| `run_server.py` | Launches `uvicorn app:app` on port 8000 | YES |
| `app.py` | FastAPI application, all HTTP routes | YES |
| `app.py:__main__` | Secondary uvicorn entry (python app.py) | YES |

---

## 3. Module-by-Module Active Code Map

### 3.1 app.py - FastAPI Application (308 lines)

Active imports at startup:
- from database.connection import SessionLocal
- from scraper_manager import scraper_manager, SCRIPTS_REGISTRY
- from agents.orchestrator import agent_orchestrator

Active routes:

| Route | Method | Handler | Delegates To |
|-------|--------|---------|--------------|
| `/` `/health` `/api/health` | GET | `health_check()` | — |
| `/health/ready` | GET | `readiness_check()` | SessionLocal DB ping |
| `/api/scripts` | GET | `list_scripts()` | `scraper_manager.get_scripts()` |
| `/api/scripts/{id}` | GET | `get_script_detail()` | `scraper_manager.get_script()` |
| `/api/scripts/run` | POST | `run_script()` | `scraper_manager.create_job()` |
| `/api/jobs` | GET | `list_jobs()` | `scraper_manager.get_jobs()` |
| `/api/jobs/{id}` | GET | `get_job()` | `scraper_manager.get_job()` |
| `/api/datasets` | GET | `list_datasets()` | `scraper_manager.get_datasets()` |
| `/api/leads` | GET | `list_leads()` | `scraper_manager.get_leads()` |
| `/api/bot/chat` | POST | `bot_chat()` | `agent_orchestrator.handle_message()` |
| `/api/bot/confirm-and-generate` | POST | `bot_confirm_and_generate()` | `agent_orchestrator.confirm_and_generate()` |

---

### 3.2 scraper_manager.py - ScraperManager (792 lines)

Active singleton: scraper_manager = ScraperManager()
Also exported: SCRIPTS_REGISTRY (list of 4 script dicts, mirrors execution/registry.py)

Active public methods:

| Method | Calls Into |
|--------|-----------|
| `get_scripts()` | Returns SCRIPTS_REGISTRY constant |
| `get_script(id)` | Returns SCRIPTS_REGISTRY entry |
| `get_jobs()` | PostgreSQL via JobService.list_recent() (fallback data/jobs.json) |
| `get_job(id)` | PostgreSQL via JobService.get_by_id() (fallback data/jobs.json) |
| `get_datasets()` | PostgreSQL via DatasetService.list_recent() (fallback data/datasets.json) |
| `get_leads()` | PostgreSQL via LeadService.list() (fallback data/leads.json) |
| `create_job()` | -> ExecutionRequest -> job_executor.submit_job() |

*** DUAL EXECUTION PATH PROBLEM - see Section 7 ***

Legacy methods present but NOT called by the active path:

| Method | Lines | Status | Description |
|--------|-------|--------|-------------|
| `_run_job_thread()` | L358-429 | LEGACY | Old in-process thread runner - never called via create_job() anymore |
| `_execute_bonfire()` | L431-463 | LEGACY | Duplicate bonfire execution - only callable from dead _run_job_thread |
| `_execute_jwiz()` | L465-567 | LEGACY | Contains synthetic 555- phone generation and example.com emails |
| `_execute_dasny()` | L569-615 | LEGACY | Calls scraper.scrape_listing_page() - different API than active dispatcher |
| `_execute_nyscr()` | L617-671 | LEGACY | References NyscrScraper (wrong class - active uses NYSCRScraper) |
| `_standardize_records()` | L673-787 | LEGACY | In-memory flat dict - active path uses DB-aware standardize_records() |
| `_update_job()/_add_log()` | varies | LEGACY | JSON-only job state writers - only used by dead _run_job_thread |

---

### 3.3 agents/orchestrator.py - AgentOrchestrator (1,230 lines)

Singleton: agent_orchestrator = AgentOrchestrator()

handle_message() execution flow:
1. Guard - reject empty messages
2. Session -> AgentSessionRepository.get_by_id() or create new AgentSession
3. Persist user message -> AgentMessage -> PostgreSQL
4. Parse -> QueryParser.parse() -> NormalizedQuery
5. Persist query -> Query model -> PostgreSQL
6. Evaluate -> DataAvailabilityChecker.evaluate() -> DecisionType
7. Requirement -> RequirementRepository.get_by_session() -> upsert Requirement
8. JOB STATUS BRANCH (L209-341) - handles "status of job X" queries
9. SCRAPER COMMAND BRANCH (_detect_scraper_command(), L343-719) - directly triggers scraper_manager.create_job() when explicit scraper name detected
10. AGENT COLLABORATION BRANCH (L721-858) -> CollaborationPlanner.plan() -> if multi-agent: CollaborationEngine.execute(), else: AgentRegistry.select_agent() -> agent.handle(context)
11. Persist assistant message -> AgentMessage -> PostgreSQL -> db.commit()
12. Return structured dict matching React BotChatResponse contract

confirm_and_generate() flow:
- Derives script_id from requirement data
- Builds parameters dict
- Calls scraper_manager.create_job() -> job_executor.submit_job()
- Persists Requirement.status = "generating" -> PostgreSQL
- Returns {success, jobId, scriptId, datasetId, message}

---

### 3.4 agents/query/ - Query Parsing

| File | Role | Active? |
|------|------|---------|
| `parser.py` | QueryParser.parse() -> NormalizedQuery | YES |
| `models.py` | NormalizedQuery dataclass | YES |

---

### 3.5 agents/decisions/data_availability.py

- DataAvailabilityChecker.evaluate(NormalizedQuery) -> DataAvailabilityResult
- Queries Lead, Organization tables via LeadRepository, OrganizationRepository
- Checks ScrapeRunRepository for freshness
- Returns DecisionType: USE_DATABASE, NEED_FETCH, or NEED_CLARIFICATION
- ACTIVE: directly called from handle_message() step 6

---

### 3.6 agents/registry.py - Agent Registry

- AgentRegistry singleton: agent_registry
- Registers 5 agents at import time: SalesAgent, DataAgent, ResearchAgent, EmailAgent, GrowthAgent
- select_agent(context) - priority order: sales -> data -> email -> growth -> research

---

### 3.7 agents/specialized/ - 5 Specialized Agents

| File | Agent Class | agent_code | Active? |
|------|-------------|------------|---------|
| `sales_agent.py` | SalesAgent | "sales" | YES |
| `data_agent.py` | DataAgent | "data" | YES |
| `research_agent.py` | ResearchAgent | "research" | YES |
| `email_agent.py` | EmailAgent | "email" | YES |
| `growth_agent.py` | GrowthAgent | "growth" | YES |

---

### 3.8 agents/collaboration/ - Multi-Agent Layer 12

| File | Role | Active? |
|------|------|---------|
| `planner.py` | CollaborationPlanner.plan() | YES |
| `engine.py` | CollaborationEngine.execute() | YES |
| `aggregator.py` | CollaborationAggregator | YES |
| `models.py` | CollaborationPlan, CollaborationResult, etc. | YES |

---

### 3.9 execution/ - Execution Layer

| File | Role | Active? |
|------|------|---------|
| `executor.py` | JobExecutor singleton - thread pool, DB writes | YES |
| `dispatcher.py` | dispatch_scraper() + 4 adapters + standardize_records() | YES |
| `registry.py` | SCRIPTS_REGISTRY (validated) + get_registered_script() | YES |
| `contract.py` | ExecutionRequest, ExecutionResult dataclasses | YES |

Active execution flow (new path via job_executor):
```
scraper_manager.create_job(script_id, params, dataset_id)
  -> ExecutionRequest(...)
  -> job_executor.submit_job(request, background=True)
        -> JobService.create(...) -> PostgreSQL: Job row (Queued)
        -> ScrapeRunService.create(...) -> PostgreSQL: ScrapeRun row
        -> threading.Thread(target=_worker, daemon=True).start()
              -> JobService.start() + ScrapeRunService.start()
              -> dispatch_scraper(script_id, params, telemetry)
                    -> execute_bonfire() | execute_jwiz() | execute_dasny() | execute_nyscr()
              -> standardize_records(raw_records, script_id, dataset_id)
              -> DatasetService.create() -> PostgreSQL: Dataset row
              -> LeadService.ingest_lead_atomic() x N -> PostgreSQL: Lead rows
              -> DatasetService.update_counts()
              -> JobService.complete() + ScrapeRunService.complete()
```

---

### 3.10 Scraper Engine Files

| File | Class Called | Active? | Notes |
|------|-------------|---------|-------|
| `dallas_bonfire_scraper.py` | DallasBonfireScraper | YES | Selenium/Chrome headless |
| `jwiz.py` | HTTPClient, build_search_url, etc. | YES | requests + BeautifulSoup |
| `dasny_scraper.py` | DasnyScraper | YES | Selenium/Chrome headless |
| `final_scraper.py` | NYSCRScraper | LIMITED | Requires auth/CAPTCHA |

NOTE: scraper_manager._execute_nyscr() (LEGACY path) imports NyscrScraper - WRONG class name.
Correct class is NYSCRScraper. Would raise ImportError if legacy path were called.

---

### 3.11 services/ - Service Layer

| File | Service Class | Active? |
|------|--------------|---------|
| `job_service.py` | JobService | YES |
| `dataset_service.py` | DatasetService | YES |
| `lead_service.py` | LeadService | YES |
| `scrape_run_service.py` | ScrapeRunService | YES |
| `organization_service.py` | OrganizationService | YES |
| `contact_service.py` | ContactService | YES |
| `source_service.py` | SourceService | YES |
| `base.py` | BaseService | YES |

---

### 3.12 database/ - Database Layer

| File | Role | Active? |
|------|------|---------|
| `connection.py` | SessionLocal + engine (SQLAlchemy 2.x, PostgreSQL) | YES |
| `base.py` | SQLAlchemy DeclarativeBase | YES |
| `models/__init__.py` | Exports 19 ORM models | YES |

19 Active ORM Models:
Department, User, Agent, AgentSession, AgentMessage, Requirement, Query,
Source, ScrapeRun, Job, Dataset, DatasetRecord, Organization, Contact,
Email, Phone, Location, Lead, AgentAction

Connection: DATABASE_URL from Backend/.env
Pool: pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800

---

### 3.13 repositories/ - Repository Layer

15 repository files (active). All extend BaseRepository. Called from:
- AgentOrchestrator (RequirementRepository, QueryRepository, AgentSessionRepository)
- DataAvailabilityChecker (LeadRepository, OrganizationRepository, ScrapeRunRepository)

---

## 4. What Is NOT Active at Runtime

| File/Code | Status | Reason |
|-----------|--------|--------|
| `scraper_manager._run_job_thread()` | LEGACY/DEAD | create_job() delegates to job_executor.submit_job() - never called |
| `scraper_manager._execute_bonfire/jwiz/dasny/nyscr()` | LEGACY/DEAD | Only callable from dead _run_job_thread |
| `scraper_manager._standardize_records()` | LEGACY/DEAD | Active path uses dispatcher.standardize_records() |
| `scraper_manager._update_job()` | LEGACY/DEAD | JSON-only writer - never called on active path |
| `scraper_manager._add_log()` | LEGACY/DEAD | JSON-only logger - never called on active path |
| `data/jobs.json`, `data/datasets.json`, `data/leads.json` | FALLBACK ONLY | Used only if PostgreSQL is unreachable |

---

## 5. Synthetic / Fabricated Data Locations

### 5.1 scraper_manager._execute_jwiz() (LEGACY - L465-567)
- L526: phone = f"+1 (212) {555 + len(records):03d}-..." - fabricated 555 phones
- L539: email = f"contact@{...}.com" - fabricated emails
- L554-565: Full fallback block generates entirely fake records:
    phone = f"+1 (212) 555-01{i+1:02d}"
    email = f"info@{keyword}service{i+1}.example.com"

### 5.2 dispatcher.py execute_jwiz() (ACTIVE PATH - L140)
- L140: phone = extract_phone(card) or "+1 (212) 555-0100"
  Fallback 555 phone still present in ACTIVE path, flows into PostgreSQL

### 5.3 dispatcher.py standardize_records() (ACTIVE)
- Bonfire L283: phone = "+1 (214) 670-3326" - hardcoded static phone for ALL Bonfire leads
- DASNY L330: phone = "+1 (518) 257-3000" - hardcoded static phone for ALL DASNY leads
- NYSCR L353: phone = "+1 (518) 474-2121" - hardcoded static phone for ALL NYSCR leads
- DASNY L329: email fallback "rfp-bids@dasny.org" - fabricated when no contact email scraped
- NYSCR L352: email fallback "procurement@nyscr.ny.gov" - fabricated when no contact email scraped

### 5.4 scraper_manager._execute_nyscr() (LEGACY - L617-671)
- L648-667: Hardcoded fallback records with fabricated titles fully synthetic data

---

## 6. Dual Registry Problem

Two independent copies of SCRIPTS_REGISTRY exist:

| Location | Used By |
|----------|---------|
| `scraper_manager.py:SCRIPTS_REGISTRY` (L36-113) | app.py, AgentOrchestrator._detect_scraper_command(), ScraperManager.get_scripts() |
| `execution/registry.py:SCRIPTS_REGISTRY` (L14-91) | JobExecutor.submit_job(), dispatcher.dispatch_scraper() |

Must be kept in sync manually - no single source of truth.

---

## 7. Critical Architecture Problems (for Phase 2 Refactor)

### PROBLEM 1: DUAL EXECUTION PATH
ScraperManager has two complete execution stacks:
- ACTIVE: create_job() -> job_executor.submit_job() -> dispatcher.py -> real scrapers -> PostgreSQL
- DEAD LEGACY: _run_job_thread() -> _execute_bonfire/jwiz/dasny/nyscr() -> in-memory JSON
The legacy path is never called but its 400+ lines of code generates confusion and fabricated data.

### PROBLEM 2: SYNTHETIC DATA IN ACTIVE PATH
- dispatcher.execute_jwiz() L140: fallback "+1 (212) 555-0100" flows into PostgreSQL
- standardize_records(): hardcoded fallback emails/phones written to PostgreSQL as real contact data

### PROBLEM 3: DUPLICATE REGISTRY
Two independent SCRIPTS_REGISTRY lists must stay manually synchronized.
No single source of truth for script metadata.

### PROBLEM 4: JSON FILE FALLBACK IN PRODUCTION
get_jobs(), get_datasets(), get_leads() all have data/*.json fallbacks.
These files may contain stale or fabricated data that bleeds into API responses if DB fails.

### PROBLEM 5: WRONG CLASS NAME IN LEGACY NYSCR PATH
scraper_manager._execute_nyscr() imports NyscrScraper (L623).
This class does NOT exist. The real class is NYSCRScraper in final_scraper.py.
Would raise ImportError if legacy path were ever triggered.

### PROBLEM 6: NYSCR REQUIRES AUTHENTICATED SESSION
dispatcher.execute_nyscr() raises RuntimeError if NYSCR returns 0 records:
"NYSCR returned 0 records. The portal may require an authenticated session (interactive login with reCAPTCHA)."
NYSCR scraper will ALWAYS fail in automated/background execution without pre-stored credentials.

---

## 8. Import Chain Summary

```
app.py
 +-- database.connection -> SessionLocal
 +-- scraper_manager -> ScraperManager, SCRIPTS_REGISTRY
 |     +-- database.connection
 |     +-- services.job_service -> JobService
 |     +-- services.dataset_service -> DatasetService
 |     +-- services.lead_service -> LeadService
 |     +-- execution.contract -> ExecutionRequest
 |     +-- execution.executor -> job_executor (JobExecutor singleton)
 |           +-- execution.dispatcher -> dispatch_scraper, standardize_records
 |           |     +-- execution.contract
 |           |     +-- execution.registry -> get_registered_script
 |           |     +-- [deferred imports in functions]:
 |           |           dallas_bonfire_scraper.DallasBonfireScraper
 |           |           jwiz.[HTTPClient, build_search_url, ...]
 |           |           dasny_scraper.DasnyScraper
 |           |           final_scraper.NYSCRScraper
 |           +-- execution.registry
 |           +-- services.dataset_service
 |           +-- services.job_service
 |           +-- services.lead_service
 |           +-- services.scrape_run_service
 +-- agents.orchestrator -> agent_orchestrator (singleton)
       +-- database.connection
       +-- database.models.[agent, message, requirement, query, session, action, lead, organization]
       +-- repositories.[agent_sessions, requirements, queries]
       +-- agents.query.models -> NormalizedQuery
       +-- agents.query.parser -> QueryParser
       +-- agents.decisions.data_availability -> DataAvailabilityChecker, DecisionType
       +-- agents.base -> AgentContext, AgentResult, AgentStatus, ProposedAction
       +-- agents.registry -> agent_registry (singleton)
       |     +-- agents.specialized.[sales, data, research, email, growth]_agent
       +-- agents.collaboration.planner -> CollaborationPlanner
       +-- agents.collaboration.engine -> collaboration_engine (singleton)
             +-- agents.collaboration.models
             +-- agents.collaboration.aggregator -> CollaborationAggregator
             +-- agents.registry
```

---

## 9. Frontend Integration Points

| Contract Field | Set By | Purpose |
|----------------|--------|---------|
| `reply` | AgentOrchestrator | Chat text |
| `suggestions` | Agent / Orchestrator | Quick-reply chips |
| `updatedRequirement` | _requirement_to_dict() | Requirement sidebar state |
| `recommendedScript` | DataAvailabilityResult | Script suggestion |
| `sessionId` | DB session | Multi-turn tracking |
| `decision` | DecisionType.value | USE_DATABASE/NEED_FETCH/NEED_CLARIFICATION |
| `agentCode` | Selected agent code | Which agent handled |
| `handledBy` | Agent class name | Debug trace |
| `collaborationId` | CollaborationEngine | Multi-agent ID |
| `agentsInvolved` | CollaborationResult | Participating agent list |
| `agentSteps` | CollaborationResult.tasks | Step-by-step breakdown |
| `jobId` | scraper_manager.create_job() | Active job reference |
| `proposedActions` | ProposedAction.to_dict() | UI action buttons |

---

## 10. Summary Table: Active vs Legacy

| Component | Status | Notes |
|-----------|--------|-------|
| `app.py` | ACTIVE | All routes used |
| `scraper_manager.create_job()` | ACTIVE | Correct delegation path |
| `scraper_manager.get_*()` | ACTIVE | DB-primary with JSON fallback |
| `scraper_manager._run_job_thread()` | LEGACY | Never called - dead code |
| `scraper_manager._execute_*()` | LEGACY | Never called - dead code |
| `scraper_manager._standardize_records()` | LEGACY | Never called - dead code |
| `execution/executor.py` | ACTIVE | Thread-safe DB writes |
| `execution/dispatcher.py` | ACTIVE | 4 engine adapters |
| `execution/registry.py` | ACTIVE | Script validation |
| `agents/orchestrator.py` | ACTIVE | Full pipeline |
| `agents/registry.py` | ACTIVE | 5 agents registered |
| `agents/specialized/` (all 5) | ACTIVE | All registered |
| `agents/collaboration/` | ACTIVE | Layer 12 |
| `agents/query/` | ACTIVE | Query parsing |
| `agents/decisions/` | ACTIVE | DB-first decision |
| `agents/base.py` | ACTIVE | Base contract |
| `database/connection.py` | ACTIVE | PostgreSQL pool |
| `database/models/` (19 models) | ACTIVE | All in use |
| `services/` (8 services) | ACTIVE | All in use |
| `repositories/` (15 repos) | ACTIVE | All in use |
| `migrations/` + `alembic.ini` | ACTIVE | Schema management |
| `data/jobs.json` etc | FALLBACK ONLY | Used only if PostgreSQL fails |
| `dallas_bonfire_scraper.py` | ACTIVE | Chrome/Selenium |
| `jwiz.py` | ACTIVE | HTTP + BeautifulSoup |
| `dasny_scraper.py` | ACTIVE | Chrome/Selenium |
| `final_scraper.py` | LIMITED | NYSCR requires auth/CAPTCHA |

---

*End of Phase 1 Audit. Phase 2 will use this map to perform the production architecture refactor.*
