# REMEDIATION_PLAN.md — v8 (final, complete)

> **Audience:** Gemini coding agent in Google Antigravity.
> **Supersedes** every earlier plan and every earlier PROGRESS.md claim. **The code is the only ground truth.**
> **Read this whole file before writing code.** Re-read §0 and §5 at the start of every phase.

## Contents
0 Operating instructions · 1 What we are building · 2 Product decisions · 3 Architecture & layout · 4 Audit summary · 5 Rules (protocol, hard rules, STOP checkpoints, technical decisions) · 6 Execution order · 7 Phases P0–P17 · 8 P18 Final self-verification · 9 Bug index · 10 PROGRESS.md template · 11 References

---

## 0. Operating instructions

1. One task at a time, **one phase per response**. End every response with: tasks done, evidence, false positives, deviations, next task.
2. Previous PROGRESS.md is not evidence. Move it to `docs/history/` (P0.1).
3. Change only files named in the task. If you must touch another file, list it with the reason in PROGRESS.md.
4. Run every command yourself and paste the output. Ask the human only at STOP checkpoints.
5. After each task: `git diff --stat`, run tests, commit.
6. If names/paths differ from this plan, search by symbol name, adapt, record under "Deviations". If you cannot adapt, stop and ask.
7. Never use a library API not confirmed in P0.2. Do not invent APIs.
8. If an unexpected test fails, stop feature work and fix or explain it first.
9. If you run out of budget mid-task, commit `wip(P<x>.<y>): <state>` and write where you stopped in PROGRESS.md.
10. Never print or commit secrets.
11. The OS is Windows. Use PowerShell or Git Bash; every check script in this plan is Python so it runs anywhere.

---

## 1. What we are building

An **AI lead-generation and procurement assistant**. A logged-in user chats with an agent ("find 50 roofing contractors in Dallas with emails", "open construction bids in New York"). The agent:
1. consults the **RAG knowledge base** first (if deployed);
2. searches the **database**;
3. returns records if there are enough; otherwise **proposes a scrape**, asks the user to confirm, runs the scraper in a **worker**, saves results **without duplicates**, re-queries, and **tells the user**.

Sources: **Bonfire** (Dallas procurement bids), **DASNY** (NY State public works RFPs), **NYSCR** (NY State Contract Reporter; login + CAPTCHA), **JWiz** (contractor/business directory). Bonfire, DASNY and NYSCR are **opportunities** (bids). JWiz is **companies**.

Built-in accounts come from `.env`: `Admin`/`Admin` (the only admin) and `User123`/`User123`. The admin can add users and sees **all user activity**: chats, decisions, tool traces, jobs, and the exact rows each user received.

**System rules:** everything goes through the LLM, with **no fallbacks**. If the LLM API is down, chat replies "The AI API is not responding. Please try again." **Modular scrapers:** one file plus one controller line per scraper. **Modular DB:** model plus repository plus one line in each of the two registries. **RAG** lives in its own `RAG/` folder and is reachable only over HTTP.

---

## 2. Product decisions (defaults applied; human may override at S8)

| # | Question | Decision |
|---|---|---|
| Q1 | Bids or companies? | Both. Bids matched by source + bid number; companies by fingerprint (name, domain, phone, email). |
| Q2 | Shared database? | Yes. Leads are shared. Users see only their own chats, jobs, requests and received rows; admin sees all. |
| Q3 | Expired bids count as "enough"? | No. Opportunities with `due_at < now()` are excluded unless the user asks for past bids. |
| Q4 | Old data re-scraped? | Only if the user asks for fresh data (`fresh_within_days`, default meaning 30 days). |
| Q5 | Confirm before scraping? | Yes (`AUTO_SCRAPE=false`). Switchable to automatic in `.env`. |
| Q6 | Extra frontend features (campaigns, calls, emails, Gantt, employees, departments, workflows, analytics, data-request stepper) | Hidden (routes and menu removed, code kept) until connected to real data (S11). |
| Q7 | Departments | One hidden department `dept-default`. |
| Q8 | Lead statuses | Read-only. Ingestion sets `New`; nobody edits statuses. |
| Q9 | Exports | CSV of the user's own received leads; admin can export everything. |
| Q10 | RAG content | Checked every turn; used for knowledge questions. Data questions still go to the DB. |
| Q11 | Where it runs | Windows dev machine; Docker supported. |
| Q12 | NYSCR CAPTCHA | Solved by the person running the worker in a visible Chrome window (S10). |
| Q13 | App LLM | Gemini (single provider). Human sets the exact model ID at S6. |
| Q14 | Admin chats? | Yes, the admin can chat too. |
| Q15 | Scale | < 20 users, < 100k leads. |

---

## 3. Architecture & layout

```
Browser ──JWT──► Backend API (FastAPI)
  /api/auth/*          login (env accounts + DB users), me
  /api/bot/*           chat, confirm, sessions, session messages (poll)
  /api/rag/{path}      authenticated pass-through to RAG service
  /api/jobs /api/leads /api/datasets /api/scripts   read-only, scoped
  /api/admin/*         users, activity, request detail, sessions, stats, exports
  └─ runner ─► LangGraph:
       load_context → rag_retrieve → agent ⇄ tools
       agent → validate_proposal → ask_confirmation → await_confirmation (interrupt) → enqueue_job → agent
       agent → finalize → END
Worker (python -m worker): claim job (FOR UPDATE SKIP LOCKED) → scrappers.controller.run
       → upsert_leads → completion pipeline → event turn (LLM writes the notification)
RAG service (python -m RAG): /v1/status, /v1/search (+ anything added later)
Postgres + pgvector: schema public (app, checkpoints, jobs) + schema rag (owned only by RAG/)
Chrome: local (dev) or Selenium standalone container (Docker)
```

```
Backend/
  settings.py _paths.py app.py worker.py run_server.py alembic.ini
  .env.example .env.test.example requirements.txt requirements-dev.txt
  integrations/rag_client.py
  routes/ auth.py bot.py admin.py jobs.py leads.py scripts.py rag_proxy.py serializers.py
  services/ auth.py users.py jobs.py ingest.py sources.py visibility.py
  scrappers/ base.py driver.py controller.py _template.py bonfire.py dasny.py jwiz.py nyscr.py
  agents/llm/chat_model.py
  agents/graph/ state.py graph.py runner.py checkpointer.py persist.py prompts/system.md
               nodes/ load_context.py rag_retrieve.py agent.py proposal.py finalize.py summarize.py
               tools/ knowledge.py search.py catalog.py jobs.py scrape.py
  migrations/  tests/ unit/ integration/ graph/ fixtures/ fakes/
Database/ controller.py normalize.py seed.py setup.py check.py models/ repositories/
RAG/ README.md CONTRACT.md __init__.py __main__.py app.py settings.py .env.example
     requirements.txt Dockerfile alembic.ini api/ core/ embedders/ store/ migrations/ tests/
scripts/ probe_apis.py backfill_identity.py merge_duplicates.py purge_checkpoints.py
         create_user.py e2e_smoke.py audit_patterns.py
docs/ ADDING_A_SCRAPER.md ADDING_A_TABLE.md RAG_INTEGRATION.md agent_graph.md probe.md
docker-compose.yml Dockerfile .dockerignore
```

---

## 4. Audit summary (why it fails today)

| # | Blocker | Evidence (file → symbol) |
|---|---|---|
| X1 | Every authenticated request → 500 | `services/auth.py` `get_current_user`, `enforce_scrape_limit` call `db.get_session()` (does not exist) |
| X2 | Impersonation, forged tokens, auto-admin | `except jwt.DecodeError: user_id = token` (PyJWT `InvalidSignatureError` subclasses `DecodeError`, so forged tokens pass); default secret `'supersecretkey'`; auto-creates `role='admin'` when `ENV != 'production'` |
| X3 | Chat memory likely broken | `agents/graph/checkpointer.py`: pool lacks `row_factory=dict_row`; `setup()` never called |
| X4 | Jobs cannot be created | `graph.py scrape_gate` passes `query_id=''`, `department_id=''`; `app.py run_script` passes `'dept-sales-1'`, `query_id=''` |
| X5 | Scraped leads likely lost | `LeadService` binds repos to scoped `db.session`; `db.transaction()` closes and `remove()`s it after each lead |
| X6 | No dedup | `ingest_lead_atomic` matches org by lowercase name; lead only if org AND contact exist; no unique keys; `normalize.py` unused; `external_id` dropped |
| X7 | No real confirmation | `scrape_gate` never calls `interrupt()`; confirm endpoint returns `job-{sessionId}` / `ds-{sessionId}` |
| X8 | Admin panel empty/crashes | chat writes no `queries`/`agent_messages`/`query_results`; reads `job.error_message` (missing); stats use `USE_DATABASE` (never written) |
| X9 | Wrong search results | `search_leads` joins city+state into one string; `if has_email:` ignores `False`; unordered pagination; category matches org name |
| X10 | Docker cannot run | context `./Backend` excludes `Database/`; `DB_*` vs `DATABASE_URL`; worker sleeps; no Chrome |
| X11 | Not modular | scraper names hard-coded in prompt, dispatcher, registry, seed, `scrappers/__init__.py`, tools |
| X12 | Fallbacks and manual paths | inventory in P9 |

---

## 5. Rules

### 5.1 Task protocol (every task)
1. **Read** the named files; quote the offending code (file + symbol) in PROGRESS.md.
2. **Red:** write a test that fails because of the bug; paste output. Not reproducible → `FALSE-POSITIVE` with evidence.
3. **Implement** the smallest change meeting "Done when".
4. **Green:** task tests + full `pytest -q`; paste output.
5. **Self-check** every "Done when" bullet in writing.
6. **Record** status, commit hash, tests, evidence in PROGRESS.md.
7. **Commit** one task per commit: `fix(P<phase>.<task>): <summary>`.

DONE requires pasted evidence (test output, SQL result, API response).

### 5.2 Hard rules
1. Never delete, skip, weaken or `xfail` a test to pass (S5 to change any existing test).
2. Integration/E2E tests use **real auth + real Postgres (pgvector image)**. No `dependency_overrides` for auth/DB. Only the LLM, embedder, live websites and (in Backend tests) the RAG HTTP service may be faked.
3. **No fallbacks:**
   - no backup LLM providers and no `.with_fallbacks()`
   - no regex, keyword or rule logic that decides instead of the LLM
   - no degraded mode
   - no `x or 'default'` for missing data or configuration
   - no `try: A except: B` where B is an alternative implementation
   - no `except ImportError` alternative paths

   **Allowed:** bounded retries of the *same* call on transient errors, and validation that marks input invalid (stored as NULL and reported).
4. **No manual system:** no endpoint/UI that triggers scraping or decisions outside the agent. Read-only views are allowed.
5. No `except: pass` / `except Exception: pass`. Catch specific exceptions; log with context; re-raise or return an explicit error.
6. Never fabricate data. Missing → `NULL`.
7. No hard-coded user/department/agent IDs outside `Database/seed.py`, migrations, `services/auth.py` (env-account IDs) and tests.
8. Never pass `''` to a foreign key. Use `None`.
9. **Scraper modularity:** outside `Backend/scrappers/`, nothing imports a specific scraper module or names a scraper (tests, fixtures, migrations, `scripts/backfill_identity.py` excepted).
10. **DB modularity:** outside `Database/`, nothing imports a repository module; use `Database.controller.Repositories`.
11. **RAG isolation:** `Backend/` and `Database/` never import `RAG`; `RAG/` never imports `Backend`/`Database`. Coupling = HTTP + `RAG/CONTRACT.md`.
12. **Config:** no defaults in code for configurable settings. Every key is in `.env.example`; startup validates presence and type.
13. Transactions are owned by the caller (route, worker, tool, runner). Services/repositories never commit.
14. API changes are additive (frontend compatibility), except removals listed in P9 (S4).
15. Every migration has a working `downgrade()`.
16. Don't reformat untouched files. Don't disable lint rules to pass.
17. **All user-facing chat text comes from the LLM.** The server returns only structured data (records, IDs, statuses, error codes) plus the single fixed D4 error message.

### 5.3 STOP checkpoints (ask the human, wait)
- **S1** Before starting: the human must change the NYSCR password (it is in git history). Wait for acknowledgement.
- **S3** Before `merge_duplicates.py --apply` on any non-local DB.
- **S4** Before deleting any file, module, endpoint or UI feature.
- **S5** Before changing or removing any existing test.
- **S6** Before setting the LLM provider/model/thinking level, an embedding provider/model, or external tracing.
- **S7** Before a migration that drops a column/table containing data.
- **S8** Before changing any product decision in §2 or visibility rule D9.
- **S9** If the `vector` extension is unavailable.
- **S10** How the NYSCR CAPTCHA will be solved (local visible Chrome, or Selenium container VNC: verify URL/port).
- **S11** Before hiding/removing frontend features: show the list and get approval.
- **S12** Before switching the Docker Postgres image to `pgvector/pgvector:pg15`: back up with `pg_dump` first.

### 5.4 Technical decisions

| ID | Decision |
|---|---|
| D1 | Auth: env accounts compared with `hmac.compare_digest`; DB users with `hashlib.pbkdf2_hmac('sha256', …, 200_000)`; JWT HS256 (`sub`, `role`, `iat`, `exp`). No password policies. Role re-read from DB every request. |
| D2 | Exactly one admin: `usr-env-admin`. The API never creates/promotes admins; a partial unique index enforces it. |
| D3 | LLM: single provider, single model, no fallback. Same-call retries `LLM_MAX_RETRIES` on timeout/429/5xx only. |
| D4 | LLM down → HTTP **503** `{"success": false, "error": {"code": "LLM_UNAVAILABLE", "reason": "<not_configured / timeout / auth_error / rate_limited / provider_error>", "message": "The AI API is not responding. Please try again."}}`. Retrying with the same `clientMessageId` resumes the same turn. |
| D5 | Job queue on the `jobs` table (`FOR UPDATE SKIP LOCKED`), process `python -m worker`. RQ/Redis removed. |
| D6 | `sessionmaker(expire_on_commit=False)`; explicit sessions; no `scoped_session`. |
| D7 | Dedup: `leads.identity_key` UNIQUE: opportunity → `src:<source>:<external_id>`; company → `fp:<fingerprint>`. `organizations.dedup_key` UNIQUE. Every sighting → `lead_sources`. |
| D8 | Agent: custom LangGraph `StateGraph`, `PostgresSaver`. Confirmation via `interrupt()` unless `AUTO_SCRAPE=true`. The user's reply is classified **by the LLM**. Buttons send text through the same chat path. |
| D9 | Visibility: **User** → own sessions/messages/jobs/requests, leads in own `query_results`, datasets of own jobs. **Admin** → everything + user management + read any chat. Agent tools search all leads; every row shown is recorded. |
| D10 | Decision vocabulary everywhere: `KB, DB, SCRAPER, PARTIAL, CLARIFY, NONE, DECLINED, FAILED, LLM_UNAVAILABLE`. |
| D11 | Query status: `received → answered / served_db / awaiting_confirmation / scraping → served_scrape / partial / declined / failed / llm_unavailable / abandoned`. |
| D12 | RAG: separate service in `RAG/`, schema `rag`, own Alembic (`version_table='alembic_version_rag'`). Backend calls only `GET /v1/status`, `POST /v1/search`; everything else via proxy. |
| D13 | Chrome: `SELENIUM_MODE=local/remote` (explicit); `SELENIUM_REMOTE_URL` required for `remote`. |
| D14 | Source codes are lowercase scraper ids everywhere. |
| D15 | Limits from `.env`: `MAX_TOOL_STEPS, RECURSION_LIMIT, HISTORY_TOKEN_BUDGET, SUMMARY_TRIGGER_MESSAGES, SCRAPES_PER_HOUR`. Code constants: page ≤ 50 rows, quantity 1–1000. |
| D16 | Job statuses: `Queued, Running, WaitingForUser, Completed, Partial, Failed, Cancelled`. |
| D17 | Deterministic message IDs: `msg-<clientMessageId>-user`, `msg-<clientMessageId>-assistant`; events `msg-evt-<job_id>`, `msg-evt-<job_id>-assistant`. Inserts use `ON CONFLICT DO NOTHING`. |
| D18 | Model-default rule: allowed defaults = empty `[]`/`{}`, zero counters, `False` flags, server timestamps. Descriptive/business values (model names, country, quantities, roles, types, versions, statuses) are set explicitly by the code that writes the row; DB columns without a known value are nullable. |

---

## 6. Execution order

```
P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P10 → P11 → P12 → P13 → P14 → P15 → P16 → P17 → P18
```
P3 needs P2; P5 needs P4; P7 needs P5+P6; P11 needs P3, P7, P8, P10; P12 needs P11; P13 needs P12. Tests are written inside each phase.

---

## 7. Phases

### P0 — Baseline & safety net

**P0.1 Snapshot.**
1. Commit everything as `wip: snapshot before remediation v8`.
2. Create the branch with `git switch -c remediation-v8`.
3. Move PROGRESS.md to `docs/history/`, then create a new PROGRESS.md from §10.
4. Save to `docs/baseline/`:
   - `pytest -q`
   - `alembic heads` and `alembic current`
   - `pip freeze`
   - `git log --oneline -30`
   - frontend `npm run build`

**P0.2 API probe** — `scripts/probe_apis.py` prints installed versions and fails loudly if any import is missing:
- `langgraph.types.interrupt`, `Command`
- `langgraph.prebuilt.ToolNode`, `InjectedState`
- `langchain_core.tools.InjectedToolCallId`
- `langchain_core.messages.trim_messages`, `RemoveMessage`, `ToolMessage`
- `langgraph.checkpoint.postgres.PostgresSaver`, `langgraph.checkpoint.memory.InMemorySaver`
- `psycopg_pool.ConnectionPool`, `psycopg.rows.dict_row`
- `sqlalchemy.dialects.postgresql.insert`
- `pgvector.sqlalchemy.Vector`
- `httpx`, `jwt`
- `langchain_google_genai.ChatGoogleGenerativeAI`

Run tiny experiments (InMemorySaver) and record exact working code in `docs/probe.md`:

| Exp | Question |
|---|---|
| E1 | A tool returning `Command(update=...)` inside `ToolNode` updates state. |
| E2 | Which accessor exposes a pending interrupt on `graph.get_state(config)` (`.tasks[i].interrupts` or `.interrupts`). |
| E3 | After a node raises, `graph.invoke(None, config)` re-runs that node with earlier state intact. |
| E4 | On `Command(resume=...)`, the node containing `interrupt()` re-runs from its first line. |
| E5 | The thinking-level constructor parameter of the installed `ChatGoogleGenerativeAI`. |
| E6 | `PostgresSaver(pool)` with `dict_row` works; `setup()` is idempotent. |
| E7 | After a failed run (`state.next` non-empty), invoking with **new input** starts from START (pending task dropped) or not. |
| E8 | `graph.update_state(config, {"messages": [ToolMessage(...)]}, as_node=...)` works for repairing dangling tool calls. |
| E9 | `issubclass(jwt.InvalidSignatureError, jwt.DecodeError)` (documents the X2 bypass). |
| E10 | Gemini accepts history with AI tool-call messages + ToolMessages + a HumanMessage starting with `[JOB EVENT]`. |
| E11 | Whether `Command(resume=..., update={...})` at `invoke` level applies the update; otherwise use `update_state` before resuming. |

**P0.3 pgvector** — `SELECT name, installed_version FROM pg_available_extensions WHERE name='vector';` Missing → **S9**.

**P0.4 Test infrastructure**
- `Backend/.env.test.example` with every P1.2 key (test values).
- `Backend/conftest.py`:
  - Before importing the app, set `DATAOPS_ENV_FILE=Backend/.env.test` (never load the real `.env`).
  - Start `PostgresContainer("pgvector/pgvector:pg15")` and export its URLs as `DATABASE_URL` / `CHECKPOINT_DB_URL`.
  - Run `alembic upgrade head`.
  - Fixtures: `db_session` (rolled back per test), `client` (real `TestClient`), `login(username, password)`, `admin_token`, `user_token`, `make_user`.
- `tests/fakes/`:
  - `scripted_chat_model.py`: `BaseChatModel` returning scripted `AIMessage`s (with `tool_calls`); `bind_tools()` returns self; `with_structured_output()` is scripted; modes that raise timeout/auth/429/5xx.
  - `fake_scraper.py`: yields `tests/fixtures/fake/records.json`.
  - `fake_rag.py`: `httpx.MockTransport` implementing RAG contract v1 with a configurable state.
- Markers `unit, integration, graph, live`; `addopts = -m "not live"`.
- **Done when:** an integration test calls `/health/ready` against the container and passes.

**P0.5 S1** — remind the human to change the NYSCR password; record acknowledgement.

---

### P1 — Settings, `.env`, packaging (no defaults)

**P1.1 `Backend/settings.py`**
- Loads `$DATAOPS_ENV_FILE` if set, else `Backend/.env`. Missing file → startup error.
- Validates every key, collects all problems, raises one `ConfigError`.

| Key | Rule |
|---|---|
| `DATABASE_URL` | starts `postgresql+psycopg://` |
| `CHECKPOINT_DB_URL` | starts `postgresql://` |
| `ENVIRONMENT` | `development` / `test` / `production` |
| `LOG_LEVEL` | `DEBUG/INFO/WARNING/ERROR` |
| `CORS_ORIGINS` | comma-separated, ≥ 1 |
| `API_HOST`, `API_PORT` | string; int 1–65535 |
| `AUTH_ADMIN_USERNAME`, `AUTH_ADMIN_PASSWORD`, `AUTH_USER_USERNAME`, `AUTH_USER_PASSWORD` | non-empty; usernames differ (case-insensitive) |
| `JWT_SECRET` | ≥ 32 chars |
| `JWT_EXPIRE_HOURS` | int > 0 |
| `LLM_PROVIDER` | `gemini` / `openai_compatible` |
| `LLM_MODEL`, `LLM_API_KEY` | may be empty → chat returns `not_configured` |
| `LLM_BASE_URL` | required iff `openai_compatible` |
| `LLM_THINKING_LEVEL` | `low/medium/high` or empty (= do not send) |
| `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES` | int > 0; int ≥ 0 |
| `AUTO_SCRAPE` | `true`/`false` |
| `MAX_TOOL_STEPS`, `RECURSION_LIMIT`, `HISTORY_TOKEN_BUDGET`, `SUMMARY_TRIGGER_MESSAGES`, `SCRAPES_PER_HOUR`, `FRESHNESS_DAYS` | int > 0 |
| `LANGGRAPH_STRICT_MSGPACK` | `true`/`false`; exported to `os.environ` before importing langgraph |
| `RAG_SERVICE_URL` | may be empty → KB state `not_deployed` |
| `RAG_SERVICE_TOKEN` | required iff URL set |
| `RAG_TIMEOUT_S`, `RAG_TOP_K` | int > 0; int 1–20 |
| `NYSCR_USERNAME`, `NYSCR_PASSWORD` | may be empty → NYSCR not ready |
| `SELENIUM_MODE`, `SELENIUM_REMOTE_URL` | `local/remote`; URL required iff `remote` |
| `SCRAPER_MODE` | `live` / `fixture`; `fixture` only when `ENVIRONMENT=test` |
| `WORKER_POLL_SECONDS`, `JOB_STALE_SECONDS`, `CAPTCHA_WAIT_SECONDS`, `CHECKPOINT_RETENTION_DAYS` | int > 0 |
| `SENTRY_DSN` | may be empty |
| `SENTRY_TRACES_SAMPLE_RATE` | float 0–1 |

- Replace every `os.getenv`, `os.environ.get`, `load_dotenv` in `Backend/` and `Database/` with `settings.*` (incl. `Database/setup.py`, `Database/check.py`, `migrations/env.py`, `run_server.py`, `conftest.py`, `utils/logging_config.py`). Remove silent URL rewrites (`postgres://`, `+asyncpg`) and the defaults in `Database/setup.py` (`username or 'postgres'`, `'localhost'`, `5432`, `'/dataops'`).
- **Tests:** missing key, wrong type, provider without base URL, `remote` without URL, `fixture` outside test, RAG URL without token.
- **Done when:** `python scripts/audit_patterns.py --only config` shows 0 hits.

**P1.2 `Backend/.env.example`** (local `Backend/.env` is the same with real values; never committed):
```env
# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/dataops
CHECKPOINT_DB_URL=postgresql://postgres:postgres@localhost:5432/dataops
ENVIRONMENT=development
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
API_HOST=0.0.0.0
API_PORT=8000

# Built-in accounts (login compares against these values)
AUTH_ADMIN_USERNAME=Admin
AUTH_ADMIN_PASSWORD=Admin
AUTH_USER_USERNAME=User123
AUTH_USER_PASSWORD=User123
# Generate: python -c "import secrets;print(secrets.token_urlsafe(48))"
JWT_SECRET=
JWT_EXPIRE_HOURS=12

# LLM: single provider, no fallback (STOP S6). Empty key/model → chat replies "The AI API is not responding".
LLM_PROVIDER=gemini
LLM_MODEL=
LLM_API_KEY=
LLM_BASE_URL=
LLM_THINKING_LEVEL=
LLM_TIMEOUT_S=60
LLM_MAX_RETRIES=1

# Agent
AUTO_SCRAPE=false
MAX_TOOL_STEPS=6
RECURSION_LIMIT=25
HISTORY_TOKEN_BUDGET=6000
SUMMARY_TRIGGER_MESSAGES=30
SCRAPES_PER_HOUR=10
FRESHNESS_DAYS=30
LANGGRAPH_STRICT_MSGPACK=true

# RAG service (folder RAG/). Empty URL → knowledge base reported as "not_deployed".
RAG_SERVICE_URL=
RAG_SERVICE_TOKEN=
RAG_TIMEOUT_S=10
RAG_TOP_K=5

# Scrapers / worker
NYSCR_USERNAME=
NYSCR_PASSWORD=
SELENIUM_MODE=local
SELENIUM_REMOTE_URL=
SCRAPER_MODE=live
WORKER_POLL_SECONDS=2
JOB_STALE_SECONDS=300
CAPTCHA_WAIT_SECONDS=300
CHECKPOINT_RETENTION_DAYS=30

# Monitoring
SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0.1
```
- Generate `JWT_SECRET` into local `Backend/.env`.
- Remove old keys after the code no longer reads them: `LLM_PRIMARY_PROVIDER`, `LLM_FALLBACK_PROVIDERS`, `GEMINI_*`, `DEEPSEEK_*`, `NVIDIA_*`, `PORT`, `HOST`.
- `.gitignore`: `Backend/.env`, `Backend/.env.test`, `RAG/.env`.

**P1.3 Paths & entrypoints**
- `Backend/_paths.py` adds the repo root + `Backend/` to `sys.path` once. Use it everywhere; remove every other `sys.path.insert`.
- `run_server.py` → `uvicorn.run("app:app", app_dir=str(BACKEND_DIR), host=settings.API_HOST, port=settings.API_PORT, reload=settings.ENVIRONMENT == "development")`.
- **Done when:** the server starts from the repo root and from `Backend/`; `/health` → 200.

**P1.4 Sentry** — init only if `SENTRY_DSN` is set; `send_default_pii=False`; `traces_sample_rate` from settings; remove `profiles_sample_rate=1.0`; `before_send` masks emails/phones.

**P1.5 Logging** — `utils/logging_config.py` reads `settings.LOG_LEVEL`; JSON logs; keep the `request_id` context var.

---

### P2 — Modular DB layer & sessions (fixes X5)

**P2.1 Session layer** in `Database/controller.py`:
```python
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

def get_db():
    with session_scope() as s:
        yield s
```
- Remove `scoped_session`, `DBController`, the `db` singleton, repository properties, `atexit`, and `Database/session.py` (S4 after callers move).
- `Database/__init__.py` exports `engine, SessionLocal, session_scope, get_db, Repositories`.
- **Test:** two scopes give different sessions; objects stay readable after commit.

**P2.2 Repository registry (one-line rule)**
```python
class Repositories:
    """Single entry point for data access.
    To add a table: create models/<x>.py + repositories/<x>.py, then add ONE line below."""
    _REGISTRY = {
        "agents": AgentRepository,
        "agent_sessions": AgentSessionRepository,
        "agent_messages": AgentMessageRepository,
        "agent_actions": AgentActionRepository,
        "contacts": ContactRepository,
        "datasets": DatasetRepository,
        "dataset_records": DatasetRecordRepository,
        "departments": DepartmentRepository,
        "emails": EmailRepository,
        "jobs": JobRepository,
        "leads": LeadRepository,
        "lead_sources": LeadSourceRepository,
        "locations": LocationRepository,
        "organizations": OrganizationRepository,
        "phones": PhoneRepository,
        "queries": QueryRepository,
        "query_results": QueryResultRepository,
        "requirements": RequirementRepository,
        "scrape_runs": ScrapeRunRepository,
        "sources": SourceRepository,
        "users": UserRepository,
    }

    def __init__(self, session):
        self.session = session
        self._cache = {}

    def __getattr__(self, name):
        if name not in self._REGISTRY:
            raise AttributeError(name)
        if name not in self._cache:
            repo_cls = self._REGISTRY[name]
            self._cache[name] = repo_cls(self.session)
        return self._cache[name]
```
Add missing repositories: `UserRepository, DepartmentRepository, AgentActionRepository, LeadSourceRepository, QueryResultRepository`.

**P2.3 Model registry** — `Database/models/__init__.py`: one import line per model ("add ONE line per new table"). Contract test `test_db_registry.py`: every model module is imported; every repository class is registered.

**P2.4 Services take a session** — `__init__(self, session)`; repos via `Repositories(session)`; delete `BaseService._commit/_rollback/_flush/_transaction` and all `commit=` params; update callers in the same commit.

**P2.5 Update every caller** — `python scripts/audit_patterns.py --only db` lists every `db.session`, `db.transaction`, `db.<repo>`, `from Database import db`, `Service()` (no session), and direct `Database.repositories.*` import outside `Database/`. Routes → `Depends(get_db)`; worker/tools/runner/scripts → `session_scope()`. **Done when:** 0 hits.

**P2.6 Repository fixes**
1. `BaseRepository.count()` raises `ValueError` on unknown filters; `list()` raises on unknown `order_by`.
2. `BaseRepository.update()` / `upsert_by()` raise on unknown fields (no warn-and-skip).
3. `LeadRepository.list()` raises on unknown filters/order_by.
4. `AgentMessageRepository.list_by_session` returns the newest N in chronological order.
5. `SourceRepository.get_by_code/upsert_by_code`, `AgentRepository.get_by_code` stop upper-casing (D14).
6. Rewrite `LeadRepository.search_leads(*, category=None, city=None, us_state=None, source_code=None, has_email=None, has_phone=None, fresh_within_days=None, include_expired=False, lead_ids=None, limit=20, offset=0)` returning `(leads, total)`:
   - `city` → `Location.city ILIKE :city`; `us_state` → `Location.state = :code` (2-letter, upper). Canonical columns only (P4.2 moves metadata data).
   - `category` → `Lead.title`, `Lead.notes`, `Organization.industry`, `lead_metadata->>'category'` (ILIKE). Never `Organization.name`.
   - tri-state `has_email/has_phone`: `True` → `EXISTS` (org or contact), `False` → `NOT EXISTS`, `None` → no filter.
   - `source_code` exact. `fresh_within_days` → `Lead.last_seen_at >= now() - interval`. `include_expired=False` → `(Lead.due_at IS NULL OR Lead.due_at >= now())`.
   - Pagination: distinct ids ordered `created_at DESC, id` → `OFFSET/LIMIT` → eager-load (org → emails/phones/locations; contact → emails/phones) in the same order.
   - **Tests:** city+state returns rows; `has_email=False` excludes leads with emails; pages don't overlap; an org named "Plumbing City" isn't matched by category "plumb" through its name; expired bids excluded by default.

**P2.7 Model hygiene** — fix `TYPE_CHECKING` imports `database.models` → `Database.models`. Apply D18:
- Remove `Agent.model='gpt-4o'`, `Location.country='USA'`, `Requirement.quantity=20`, `Job.total_target=20`, `Source.default_limit=20`, `Source.version='1.0.0'`, `User.role='sales'`, `Email.email_type='work'`, `Phone.phone_type='office'`, `Query.status='pending'`, `Lead.status='New'`, `Job.status='Queued'`, `Dataset.status='Completed'`, `ScrapeRun.status='Pending'`.
- Callers set these explicitly; nullability changes are in P4.1.

**P2.8 Alembic env** — `migrations/env.py`: read `settings.DATABASE_URL`; add `include_object` / `include_name` filters that ignore LangGraph checkpoint tables (`checkpoint%`) and schema `rag`, so `alembic check` reports only real drift.

**P2.9 Docs** — `docs/ADDING_A_TABLE.md`: model → repository → 1 line in `models/__init__.py` → 1 line in `_REGISTRY` → `alembic revision --autogenerate` → review → `alembic upgrade head` → `pytest -k db_registry`.

---

### P3 — Authentication & user management (fixes X1, X2)

**P3.0 Migration `c0_users_auth`** (one revision, ordered):
1. Insert department `dept-default` ("Default", code `DEFAULT`) and agent `agent-master` (department `dept-default`, name "DataOps Agent", code `agent-master`, status `idle`, capabilities `[]`) with `ON CONFLICT (id) DO NOTHING`.
2. Add `users.username` (String 100), `users.password_hash` (String 255), `users.auth_source` (String 10), all nullable.
3. Make nullable: `users.email`, `agents.model`.
4. Existing users (`usr-ahmed, usr-sara, usr-marcus, usr-elena`, …) → `role='user'`, `status='Disabled'`, `auth_source='db'`, `username=id` (kept for history).
5. `users.auth_source` NOT NULL.
6. `CREATE UNIQUE INDEX uq_users_username_lower ON users (lower(username)) WHERE username IS NOT NULL;`
7. `CREATE UNIQUE INDEX uq_users_single_admin ON users ((role)) WHERE role = 'admin';`
- `downgrade()` reverses 7 → 2.

**P3.1 `services/auth.py`**
```python
ENV_ADMIN_ID = "usr-env-admin"
ENV_USER_ID = "usr-env-user"

def authenticate(session, username, password):
    """1) env admin  2) env user  (username case-insensitive, password exact, hmac.compare_digest)
    3) DB users with auth_source='db' and status='Active' via verify_password(). Returns User or None."""
def hash_password(password)            # "pbkdf2_sha256$200000$<salt_hex>$<hash_hex>"
def verify_password(password, stored)
def create_access_token(user)          # sub, role, iat, exp
def get_current_user(credentials=Depends(bearer), session=Depends(get_db)):
    """jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"]); jwt.InvalidTokenError → 401.
    No raw-token fallback, no auto-creation. Missing user or status != 'Active' → 401."""
def require_admin(user=Depends(get_current_user))   # 403 unless role == 'admin'
```
Delete: `db.get_session()`, the `DecodeError` branch, `'supersecretkey'`, the auto-create block, `os.getenv('SCRAPES_PER_HOUR', '10')`.

**P3.2 `sync_env_users(session)`** (API lifespan, worker start, `seed.py`): upsert `usr-env-admin` (admin) and `usr-env-user` (user):
- `username` from env, `name` = username, `email` NULL
- `department_id='dept-default'`, `auth_source='env'`, `password_hash` NULL, `status='Active'`, `role_title='Built-in account'`

Changing env usernames updates the same two rows.

**P3.3 `routes/auth.py`**
- `POST /api/auth/login {username, password}` → `{accessToken, tokenType:"bearer", expiresIn, user:{id, username, name, role, departmentId, departmentName}}`. Wrong credentials → 401 "Invalid username or password".
- `GET /api/auth/me`.

**P3.4 User management (admin only)**

| Method | Path | Rules |
|---|---|---|
| GET | `/api/admin/users` | all users; env accounts flagged `builtIn: true` |
| POST | `/api/admin/users {username, name?, password}` | role forced `user`; username unique (case-insensitive) and ≠ env usernames → 409 |
| PATCH | `/api/admin/users/{id} {name?, password?, status?}` | role can't change; env accounts → 400 "edit .env" |
| DELETE | `/api/admin/users/{id}` | soft-disable; env accounts → 400 |

Any body with `role: "admin"` → 400 "Only one admin is allowed (defined in .env)". Add `scripts/create_user.py` (prompts for a password).

**P3.5 Seed** — `Database/seed.py`: `sync_env_users()` + `sync_sources()` (P6.6). Remove demo `USERS`, per-scraper departments/agents, `SCRIPTS_REGISTRY`, and JSON-string-into-JSONB inserts.

**P3.6 Authorization matrix** (implement + test every row)

| Endpoint | Rule |
|---|---|
| `/api/auth/login`, `/health`, `/health/ready`, `/health/llm` | public (`/health/llm?probe=true` admin) |
| `/api/bot/*` | authenticated; session must belong to the user |
| `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/cancel` | own (admin all) |
| `/api/scripts` | authenticated (read-only catalog) |
| `/api/leads`, `/api/leads/export.csv`, `/api/datasets` | D9 scoping |
| `/api/rag/v1/status`, `/api/rag/v1/search` | authenticated |
| `/api/rag/{anything else}` | admin |
| `/api/admin/*` | admin |

**P3.7** `enforce_scrape_limit(session, user)` runs inside `enqueue_scrape` (not a route dependency).

**Done when (integration, real auth):**
- `Admin/Admin` → admin token; `User123/User123` → user token.
- Wrong password → 401; `Bearer usr-env-admin` → 401; token with a forged signature → 401; expired token → 401.
- User calling `/api/admin/*` → 403.
- Admin creates `alice`, and alice can log in.
- A second admin via the API → 400; via SQL → unique violation.
- User A can't read user B's job or session.

---

### P4 — Schema migrations & data cleanup (main schema only)

**P4.1 `c1_jobs_identity`**
- `jobs`: `error_message` (Text), `worker_id`, `waiting_for` (String 50), `resume_requested` (bool, server default false)
- `leads`: `identity_key` (String 300), `due_at` (timestamptz) + index
- `organizations.dedup_key` (String 64)
- `queries`: `client_message_id` (String 100), `turn_id` (String 100)
- `agent_messages`: index on `(session_id, created_at)`
- Make nullable: `emails.email_type`, `phones.phone_type`, `locations.country` (no default), `requirements.quantity`, `jobs.total_target`, `sources.version`, `sources.default_limit`
- Lowercase `sources.code`, `leads.source_code`, `lead_sources.source_code`, `jobs.script_id`

**P4.2 `scripts/backfill_identity.py --dry-run|--apply`**
- Organizations: `normalized_name`, `domain`, `dedup_key`.
- Emails/phones: normalized values (report invalid ones).
- Leads:
  - `source_code` and `external_id` (strip legacy `nyscr_`); `identity_key`
  - `due_at` from metadata due/close dates (unparseable → NULL + report)
  - upsert `lead_sources`
- **Move** `lead_metadata` city/state/email/phone into canonical `locations/emails/phones`; parse `raw_location`.
- Never invent values; print counts.

**P4.3 `scripts/merge_duplicates.py --dry-run|--apply`** (S3 for non-local DBs)
- Group by `dedup_key` / `identity_key`; the survivor is the oldest.
- Re-point FKs: `leads, contacts, emails, phones, locations, dataset_records, query_results, lead_sources, agent_actions`.
- Delete the losers; write `merge_log.csv`.

**P4.4 `c2_unique_indexes`** (`autocommit_block()`, `postgresql_concurrently=True`):
- `uq_leads_identity_key` (then NOT NULL), `uq_org_dedup_key` (then NOT NULL)
- `uq_emails_owner (normalized_email, coalesce(organization_id,''), coalesce(contact_id,''))`
- `uq_phones_owner (normalized_phone, coalesce(organization_id,''), coalesce(contact_id,''))`
- `uq_contacts_org_name (coalesce(organization_id,''), normalized_full_name)`
- `uq_locations_org_city_state (organization_id, coalesce(city,''), coalesce(state,''))`
- `uq_jobs_idempotency (idempotency_key) WHERE idempotency_key IS NOT NULL`
- `uq_jobs_active_params (script_id, params_hash) WHERE status IN ('Queued','Running','WaitingForUser')`
- `uq_queries_session_client_msg (session_id, client_message_id) WHERE client_message_id IS NOT NULL`

**Done when:** `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` passes; all indexes are present.

---

### P5 — Duplicate-free ingestion (fixes X6)

**P5.1 `Database/normalize.py`**
- Add `normalize_state`, `parse_location(raw) → (city, state, postal)`, `parse_due_date(raw) → datetime|None` (`python-dateutil`), `org_key(name, domain, phone, city, state)`, `lead_identity(kind, source_code, external_id, fingerprint)`.
- Remove the `except ImportError` digit-parsing path in `normalize_phone` (`phonenumbers` is required).
- Replace broad excepts with specific ones.

**P5.2 `services/ingest.py`**
```python
def upsert_leads(session, records, *, dataset_id, scrape_run_id, source_id, department_id):
    """Returns UpsertResult(inserted, updated, unchanged, skipped, failed, lead_ids, errors).
    lead_ids are in input order. Caller commits."""
```
Batches of ≤ 100:
1. Compute `identity_key`, `fingerprint`, `dedup_key`; merge in-batch duplicates (prefer non-null); records without identity → `skipped` + error.
2. Organizations: `pg_insert(...).on_conflict_do_update(index_elements=['dedup_key'], set_=COALESCE(existing, excluded))` returning ids; no org name → `organization_id=None`.
3. Locations/contacts/emails/phones: `on_conflict_do_nothing()`, then select ids by natural key. Set `email_type`/`phone_type` from the record or NULL.
4. Leads: `on_conflict_do_update(index_elements=['identity_key'])`. Detect insert vs update with ONE method (`RETURNING (xmax = 0)` verified in a test, or pre-select keys in the same transaction) and document it.
   - Always set `department_id, source_id, source_code, external_id, fingerprint, scrape_run_id, due_at`, `status='New'` on insert, `first_seen_at` on insert, and `last_seen_at`.
   - `StandardRecord.extra` → `lead_metadata`.
5. `lead_sources`, `dataset_records` → `on_conflict_do_nothing()`.
6. Deadlock `40P01` → retry the same batch once, then fail it.

Remove `LeadService.ingest_lead_atomic` (S4).

**Tests (real Postgres):**
- Same 50 records twice → counts unchanged; the 2nd run has `inserted=0`.
- Two concurrent overlapping batches → no duplicates.
- 3 bids from one agency → 1 org, 3 leads.
- "Acme Inc." vs "ACME" with the same phone → 1 lead.
- `organization_name=None` → saved.
- All `lead_ids` readable after commit.

---

### P6 — Modular scraper framework (fixes X11)

**P6.1 `scrappers/base.py`**
- `ScraperMeta`: `id`, `name`, `description`, `record_kind` (`opportunity`/`company`), `category`, `version`, `coverage` (dict, e.g. `{"city":"Dallas","state":"TX"}`), `supports` (subset of `limit, keyword, location`), `fields`, `required_env`, `default_limit`, `max_limit`. Every scraper sets every field explicitly.
- `ScrapeParams`: `limit, keyword, city, us_state, timeout_s`.
- `ScrapeContext` protocol: `log(level, msg)`, `progress(pct, step)`, `should_cancel()`, `wait_for_user(reason)` → bool.
- `StandardRecord`: `source_code, record_kind, external_id, source_url, title, description, organization_name, contact_name, contact_title, email, phone, website, city, us_state, postal_code, category, due_at, extra`.
- `BaseScraper(ABC)`: class attribute `meta`; `__init__(self, ctx)` must not raise for missing credentials; abstract `scrape(self, params)` yields raw dicts; abstract `to_standard(self, raw)` returns a `StandardRecord` (all per-source mapping lives here); `close(self)` is safe to call twice.

**P6.2 `scrappers/driver.py`**
- `make_driver(headless)`: `remote` → `webdriver.Remote(settings.SELENIUM_REMOTE_URL)`; `local` → `webdriver.Chrome()` (Selenium Manager).
- Explicit timeouts; same-call retry helper (max 3).
- **Remove** `webdriver_manager` and the `ChromeDriverManager … except: webdriver.Chrome()` fallback.
- Scrapers use `logging`, not `print` (except the JWiz CLI `main()`), with no bare excepts.

**P6.3 `scrappers/controller.py`** — the ONLY public scraper API:
```python
from scrappers.bonfire import BonfireScraper
from scrappers.dasny import DasnyScraper
from scrappers.jwiz import JWizScraper
from scrappers.nyscr import NyscrScraper

# To add a scraper: copy _template.py to scrappers/<name>.py, implement it,
# import it above and add its class below. Nothing else changes.
REGISTERED_SCRAPERS = (
    BonfireScraper,
    DasnyScraper,
    JWizScraper,
    NyscrScraper,
)

def list_scrapers(): ...          # ScraperMeta list
def scraper_ids(): ...
def get_meta(scraper_id): ...     # raises UnknownScraper
def check_ready(scraper_id): ...  # (ok, reason) from required_env
def validate_params(scraper_id, raw): ...   # explicit errors; no silent clamping/dropping
def describe_for_llm(): ...       # id, name, description, record_kind, coverage, supports, fields, ready
def to_api_dict(meta): ...        # frontend Script shape
def run(scraper_id, params, ctx): # yields StandardRecord; checks ctx.should_cancel(); JobCancelled propagates; close() in finally
    ...
```
Import-time validation: unique lowercase ids; every class has `meta`. `SCRAPER_MODE=fixture` (test only) makes `run` yield `tests/fixtures/<id>/records.json` through the real `to_standard`.

**P6.4 Port and fix each scraper** (move mapping from `dispatcher.py` into `to_standard`; due dates → `due_at`)
- **Bonfire:**
  - Remove the fabricated `purchasing@dallascityhall.com` and the placeholder contact.
  - Apply the keyword filter before the limit.
  - `external_id = ref_number` (missing → skip, no URL fallback); `coverage` Dallas/TX.
- **DASNY:**
  - Apply the keyword filter before the limit (paginate until `limit` matches or `max_pages`).
  - `external_id` = solicitation number (missing → skip + report).
  - Filter by location after extraction.
- **NYSCR:**
  - `__init__` never raises; `required_env=("NYSCR_USERNAME","NYSCR_PASSWORD")`.
  - Implement the keyword filter (currently `pass`); `external_id` = numeric `opp_id`.
  - **CAPTCHA (S10):** remove the `except ImportError` polling fallback. Single path: detect → `ctx.wait_for_user('captcha')` (job → `WaitingForUser`, event turn tells the user) → user says it's solved → LLM calls `resume_job` → `jobs.resume_requested=true` → continue. Timeout `CAPTCHA_WAIT_SECONDS` → `Failed` "captcha not solved".
- **JWiz:**
  - Remove `make_fallback_key`, `fallback_keys` and the "generating fallback ID" log.
  - `external_id = profile_url` or `None` (identity via fingerprint).
  - Build the location slug from city/state (verify the format against fixtures); keyword from category; `record_kind="company"`.

**P6.5 Delete** (S4):
- `scrappers/__init__.py` runners, including `mock_records`
- `execution/registry.py` (`SCRIPTS_REGISTRY`, `recommend_scraper`)
- `execution/dispatcher.py` per-source code
- `execution/captcha_manager.py`

**P6.6 Everything reads the controller**
- `services/sources.py: sync_sources(session)` upserts `sources` from `list_scrapers()` (API start, worker start, seed). No seed edits for new scrapers.
- `/api/scripts` uses `to_api_dict`; agent `list_sources` uses `describe_for_llm()`; the prompt source catalogue is generated.

**P6.7** `scrappers/_template.py` + `docs/ADDING_A_SCRAPER.md` (copy template → implement → save fixtures in `tests/fixtures/<id>/` → add one controller line → `pytest -k scraper`).

**P6.8 Tests**
- `test_scraper_contract.py`, parametrized over `REGISTERED_SCRAPERS`: meta is valid; `to_standard` on fixtures gives records with an identity; `describe_for_llm` includes it.
- `test_scrapers_registered.py`: an unregistered module → fails with "add it to REGISTERED_SCRAPERS".
- `test_no_direct_scraper_imports.py` (rule 9).
- Offline fixture parsing for all 4 scrapers.

---

### P7.0 Corrections to P0–P6 (these override earlier text)
1. **Seed is broken today (verified):** `Database/seed.py` inserts `users` without `status` and `agents` without `model`, `status`, `capabilities`. These are NOT NULL with no server default, so a fresh `setup.py` fails at seeding. P3.5: write seed rows through repositories, setting every NOT NULL column explicitly. Add `test_seed_fresh_db` (empty DB → setup → seed twice).
2. **P3.0 step order:** run step 3 (make `agents.model` and `users.email` nullable) BEFORE step 1 (insert `agent-master`). New order: 3 → 1 → 2 → 4 → 5 → 6 → 7.
3. **D14 scope:** lowercase applies to **source codes only**. Agent codes are matched exactly (no case transform); existing `AGT-*` codes stay.
4. **P4.3 merge script:** after re-pointing foreign keys, de-duplicate child rows that now collide before P4.4 creates the unique indexes:
   - emails (`normalized_email` + owner) and phones (`normalized_phone` + owner)
   - contacts (org + `normalized_full_name`) and locations (org + city + state)
   - `lead_sources`, `dataset_records` and `query_results`
5. **P2.8:** `migrations/env.py` must not create an engine at import time; build it inside `run_migrations_online()`.
6. **P0.2 extra experiment E12:** confirm `ToolNode` errors on a tool call whose name isn't in its tool list (so `propose_scrape` must never be routed to it).

### P7 — Job queue & worker (fixes X4)

**P7.1 `services/jobs.py: enqueue_scrape(session, *, user, script_id, params, query_id, idempotency_key)` → `(job, created)`.** The ONLY way to create scrape jobs. It is called only by the graph node `enqueue_job` (P11.6).
1. Validate:
   - `controller.get_meta` → unknown → `ScrapeNotAllowed`
   - `check_ready` → `ScraperNotReady(reason)`
   - `validate_params` → `InvalidScrapeParams(errors)`
2. `enforce_scrape_limit(session, user)`: jobs with `created_by=user.id` in the last hour ≥ `SCRAPES_PER_HOUR` → `ScrapeRateLimited`.
3. `params_hash = sha256(json.dumps(params, sort_keys=True))`.
4. Insert the job and return its id:
   - `pg_insert(Job).values(...).on_conflict_do_nothing().returning(Job.id)`
   - values: `id`, `name`, `type='scrape'`, `script_id`, `script_name`, `source_id`, `status='Queued'`, `progress=0`, `created_by=user.id`, `department_id=user.department_id`, `query_id`, `idempotency_key`, `params_hash`, `total_target=params['limit']`, `parameters=params`, `logs=[]`
5. If no row came back:
   - select the existing job by `idempotency_key`; otherwise select the active job with the same `(script_id, params_hash)`
   - set `queries.job_id` of the caller's query to that job
   - return `(existing, False)`
6. Never create the dataset here (the worker does).
- Remove `scraper_manager.create_job` and `execution/contract.py` if they become unused (S4).

**P7.2 `Backend/worker.py`** (run with `python -m worker [--once]`)
- **Start:** load `settings`, run `sync_env_users()` and `sync_sources()`, and set `worker_id = f"{hostname}-{pid}"`.
- **Claim a job** (one transaction):
```sql
UPDATE jobs SET status='Running', started_at=now(), heartbeat_at=now(), worker_id=:wid, updated_at=now()
WHERE id = (SELECT id FROM jobs WHERE status='Queued' ORDER BY created_at
            FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id;
```
- **No job:** sleep `WORKER_POLL_SECONDS`.
- **Heartbeat:** a thread with its own session updates `heartbeat_at` every 15 s until the job ends, including during ingestion and `WaitingForUser`.
- **Run the job:**
  1. Create a `datasets` row (status `Running`, `created_by`, `department_id`, name) and a `scrape_runs` row; set `job.dataset_id`.
  2. Call `controller.run(script_id, params, JobContext)`.
  3. Collect records in batches of 100 and call `upsert_leads` for each batch, each in its own `session_scope`.
  4. Run the completion pipeline (P7.5).
- **SIGINT/SIGTERM:** finish the current batch; an unfinished job becomes `Failed` (`'worker shutdown'`).
- **Delete from `execution/executor.py`:** `ThreadPoolExecutor`, `_active_jobs`, `is_job_active`, `get_active_job_for_script`, and `limit or defaultLimit`. The API never runs scrapers.

**P7.3 `JobContext`** (implements `ScrapeContext`)
- `log(level, msg)` / `progress(pct, step)`: update `jobs.logs`, `progress`, `current_step` in short `session_scope`s.
- `should_cancel()`: reads `jobs.cancel_requested`.
- `wait_for_user(reason)`:
  - Set `status='WaitingForUser'`, `waiting_for=reason`, `resume_requested=false`, and write a `job_waiting` event (P7.5 step 5).
  - Poll every 2 s. `resume_requested` → status `Running`, return True. `cancel_requested` → raise `JobCancelled`. After `CAPTCHA_WAIT_SECONDS` → raise `UserWaitTimeout`.
- `JobCancelled` is raised outside any broad `except`; the worker marks the job and dataset `Cancelled`.
- `POST /api/jobs/{id}/cancel` (owner or admin) sets `cancel_requested=true`.

**P7.4 Reaper** (worker loop, every 60 s)
- `Running` / `WaitingForUser` jobs with `heartbeat_at < now() - JOB_STALE_SECONDS` → `Failed` (`'stalled: heartbeat timeout'`), dataset `Failed`, plus a `job_failed` event.
- Never reap `Queued`. Delete the API lifespan reaper from `app.py`.

**P7.5 Completion pipeline** (one `session_scope` after the last batch)
1. **Job status** (unit test `test_job_status_mapping`):

   | Outcome | Status |
   |---|---|
   | all records saved | `Completed` |
   | some failed or skipped | `Partial` |
   | scraper error before any record | `Failed` |
   | cancelled | `Cancelled` |
   | CAPTCHA timeout | `Failed` |

2. **Job counts:**
   - `records_found`
   - `verified_count = inserted + updated`
   - `duplicates_count = updated + unchanged`
   - `errors_count = failed + skipped`
   - `error_message` (first errors, ≤ 2000 chars), `completed_at`, `duration`
3. Update `scrape_runs` and `datasets` counts and status.
4. For **every** query with `queries.job_id = job.id`:
   - Re-run `search_leads` with `queries.parameters['slots']`, including the job's `lead_ids`.
   - Write `query_results` (rank order, `ON CONFLICT DO NOTHING`).
   - Update the query:
     - `decision`: `SCRAPER` or `PARTIAL`
     - counts: `records_new=inserted`, `records_updated=updated`, `records_returned`
     - `served_at`
     - `status`: `served_scrape`, `partial` or `failed`
5. **One event per affected session:** insert into `agent_messages` with `ON CONFLICT DO NOTHING`:
   - `id='msg-evt-<job_id>'`, `sender='system'`, `role='system_event'`, `text=<json summary>`
   - `message_metadata={type, job_id, query_id, inserted, updated, failed, status, notified: false}`
6. **Notify** (after commit): `runner.run_event_turn(session_id, job_id)` (P11.10).
   - Skip if the session has a pending interrupt.
   - If it raises `LLMUnavailable`, leave `notified=false`; the next user turn picks the event up.

**P7.6 Tests** (integration, `SCRAPER_MODE=fixture`, scripted LLM)
- enqueue → `python -m worker --once` → job `Completed`, dataset `Completed`, `query_results` rows written, event message created
- the same `idempotency_key` twice → one job
- identical parameters from two users → one job, and **both** queries are served
- cancel → `Cancelled`
- the reaper touches only stale `Running` jobs
- CAPTCHA wait → `WaitingForUser` → `resume_requested` → `Running`; a timeout → `Failed`

---

### P8 — LLM layer: single provider, no fallback

**P8.1 `agents/llm/chat_model.py`**
```python
class LLMUnavailable(Exception):
    def __init__(self, reason, detail): ...
    # reason: not_configured | timeout | auth_error | rate_limited | provider_error

def get_chat_model(tools): ...          # cached per tool-name tuple; empty LLM_MODEL/LLM_API_KEY → LLMUnavailable('not_configured')
def invoke_llm(model, messages): ...    # same-call retries (LLM_MAX_RETRIES) on timeout/429/5xx only; maps errors → LLMUnavailable
def invoke_structured(schema, messages): ...   # with_structured_output(schema); same error mapping
def probe(): ...                        # 1-token call → {provider, model, reachable, latency_ms, reason}
```
- **Providers:**
  - `gemini` → `ChatGoogleGenerativeAI(model=LLM_MODEL, google_api_key=LLM_API_KEY, timeout=LLM_TIMEOUT_S, max_retries=0)`, plus the thinking parameter from P0.2 E5 when `LLM_THINKING_LEVEL` is set.
  - `openai_compatible` → `ChatOpenAI(model, api_key, base_url=LLM_BASE_URL, timeout, max_retries=0)`.
- **Error mapping** (exception class names verified in P0.2):

  | Error | Reason | Retry? |
  |---|---|---|
  | auth / permission | `auth_error` | no |
  | 429 / quota | `rate_limited` | yes |
  | timeout / connection | `timeout` | yes |
  | 5xx | `provider_error` | yes |
  | anything else | `provider_error` (with detail) | no |

- **No `.with_fallbacks()`.** No second provider is ever constructed.

**P8.2 Health**
- `/health/llm` → `{provider, model, configured}`. Never return keys.
- `/health/llm?probe=true` (admin only) → the `probe()` result.

**P8.3 STOP S6** — the human sets `LLM_MODEL` and `LLM_THINKING_LEVEL`. Record the choice in PROGRESS.md.

**P8.4 Delete (S4):** `agents/llm/config.py`, `factory.py`, `openai_compatible.py`, `provider.py`, the old `chat_models.py`, `services/config_validator.py`.

**P8.5 Tests**
- empty key → `not_configured`
- timeout → retried `LLM_MAX_RETRIES` times, then `timeout`
- 401 → `auth_error` with zero retries
- only one provider class is ever instantiated
- `test_both_providers_creates_fallback` contradicts the no-fallback rule → STOP S5, then replace it with `test_no_fallback_provider`

---

### P9 — Remove fallbacks & manual paths

**P9.1 Fallback inventory.** Fix every row. Prove each with a test or a 0-hit grep.

| ID | Location (verify by symbol) | Fallback | Fix |
|---|---|---|---|
| F1 | `agents/llm/chat_models.py` | DeepSeek/NVIDIA `.with_fallbacks()` chain | P8 |
| F2 | `agents/llm/config.py` | env-or-default chains, `gemini-2.0-flash` | delete |
| F3 | `agents/llm/factory.py` | `FallbackLLMProvider`; "QueryParser fallback" | delete |
| F4 | `agents/llm/openai_compatible.py` | `localhost:11434` / `llama3` defaults; regex JSON parsing | delete |
| F5 | `agents/graph/graph.py` `call_model` | except → "use the filters" message, `degraded=True` | raise `LLMUnavailable` → D4 |
| F6 | `agents/graph/runner.py` `classify_confirmation` | keyword lists (yes/haan/ok/only/change…) | LLM structured output (P11.9) |
| F7 | `runner.to_api_response` | `'Not specified'`, `'No response generated.'`, `'I have a proposal for you.'` | real values or `null`; text from the LLM |
| F8 | `services/config_validator.py` | defaults; static scraper "READY" | delete |
| F9 | `services/auth.py` | secret default; raw-token fallback; auto-admin; limit default | P3.1 |
| F10 | `execution/registry.py` `recommend_scraper` | keyword/regex scraper routing | delete; the LLM chooses via `list_sources` |
| F11 | `execution/dispatcher.py` | `'City of Dallas'`, `"{category} Owner / Manager"`, `"USA"`, `else: # nyscr` | P6.4 |
| F12 | `execution/executor.py` | `limit or defaultLimit` | P7.1 |
| F13 | `scrappers/__init__.py` | `mock_records` generator | delete |
| F14 | `scrappers/jwiz.py` | `make_fallback_key`, "generating fallback ID" | P6.4 |
| F15 | `scrappers/dasny.py`, `nyscr.py` | `ChromeDriverManager` → plain Chrome | P6.2 |
| F16 | `scrappers/nyscr.py` | CAPTCHA `except ImportError` → polling | P6.4 |
| F17 | `scrappers/bonfire.py` | fabricated contact email; URL-as-ID | P6.4 |
| F18 | `Database/normalize.py` `normalize_phone` | `except ImportError` digit parsing | P5.1 |
| F19 | `Database/controller.py` `connect` | missing URL only warns; silent URL rewrites | P1.1 |
| F20 | `Database/repositories/leads.py` `search_leads` | `lead_metadata` OR-fallbacks | P2.6 |
| F21 | `app.py` | CORS default list; health uses `SCRIPTS_REGISTRY` | P1.1, P6.6 |
| F22 | `scraper_manager.py` serializers | `'00:00'`, `'New'`, `'Scraper Job'`, `or ''` | P12.2 |
| F23 | `utils/logging_config.py` | `LOG_LEVEL` default | P1.5 |
| F24 | model defaults | `gpt-4o`, `USA`, `20`, `'sales'`, `'work'`, `'office'` | P2.7 |
| F25 | `Database/setup.py` | `or 'postgres'`, `'localhost'`, `5432`, `'/dataops'` | P1.1 |
| F26 | `run_server.py` | `ENVIRONMENT` default `'development'` | P1.3 |
| F27 | `migrations/env.py` | `postgres://` rewrite; `load_dotenv` | P1.1 |
| F28 | `conftest.py` | loads the real `Backend/.env` | P0.4 |

**P9.2 Manual paths** (S4 for each removal)

| ID | Manual path | Fix |
|---|---|---|
| M1 | `POST /api/scripts/run` | delete; scraping only through the agent |
| M2 | `/api/bot/confirm-and-generate` resumes the graph directly | send approval text through the chat path (P11.11) |
| M3 | `recommend_scraper` | delete |
| M4 | keyword confirmation | LLM only |
| M5 | "use the filters panel" mode | delete |
| M6 | `captcha_manager` "type done" outside the LLM | `resume_job` tool |
| M7 | frontend Scripts "Run", `DataGenerationStepper`, `RoleSwitcher`, filter-based generation | P13 (S11) |
| M8 | any route other than `/api/bot/*` that creates jobs | remove |

- **Test `test_no_manual_scrape_paths.py`:** the only call site of `enqueue_scrape` is the `enqueue_job` node.
- **Final grep** (0 hits outside tests and docs): `fallback|degraded|with_fallbacks|except ImportError|mock_records|recommend_scraper|webdriver_manager|ChromeDriverManager`.

---

### P10 — RAG module as a separate service

**P10.1 Folder `RAG/`** (self-contained)
- Own `requirements.txt`, `.env.example`, `settings.py` (same no-defaults rules), `Dockerfile`, `alembic.ini`, tests.
- Run with `python -m RAG` (uvicorn on `RAG_PORT`).
- `RAG/.env.example` keys:
  - `RAG_DATABASE_URL`, `RAG_PORT`, `RAG_SERVICE_TOKEN`
  - `RAG_EMBEDDING_PROVIDER`, `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_DIM`
  - `RAG_STATUS_CACHE_SECONDS`, `LOG_LEVEL`

**P10.2 `RAG/CONTRACT.md` — v1 (frozen; the Backend depends only on this)**
- **Auth:** header `X-RAG-Service-Token` on every route. The Backend forwards `X-User-Id` and `X-User-Role`.
- **`GET /v1/status`** → `{"state", "available", "message", "documents", "chunks", "embeddingModel", "dim", "version": "v1"}`
  - `state` ∈ `not_configured | extension_missing | dimension_mismatch | model_mismatch | empty | ready | error`
  - `available` is true only when `state` is `ready`.
- **`POST /v1/search {"query", "topK" (1–20), "filters"}`** → `{"hits": [{"chunkId", "documentId", "title", "content", "score", "metadata"}]}`. Not ready → 409 with the status body.
- **Errors:** `{"error": {"code", "message"}}`.
- Any other endpoint belongs to `RAG/` and is reached through the Backend proxy.

**P10.3 Storage** (inside `RAG/` only)
- Schema `rag`. Own Alembic with `version_table='alembic_version_rag'` and `version_table_schema='rag'`.
- Revision `r1_init`:
  - `CREATE SCHEMA IF NOT EXISTS rag`
  - `CREATE EXTENSION IF NOT EXISTS vector` (on failure, the message explains S9)
  - `rag.documents(id, title, source, source_uri, content_hash UNIQUE, metadata JSONB, chunk_count, embedding_model, created_by, created_at, updated_at)`
  - `rag.chunks(id, document_id FK CASCADE, chunk_index, content, content_hash, token_count, embedding vector(RAG_EMBEDDING_DIM) NOT NULL, metadata JSONB, created_at, UNIQUE(document_id, chunk_index))`
  - an HNSW index using `vector_cosine_ops`
- `RAG_EMBEDDING_DIM > 2000` → error (the HNSW limit).
- `created_by` is a plain string: no foreign key into the main schema.

**P10.4 Skeleton behaviour** (until the human builds the real pipeline)
- `embedders/__init__.py`: `EMBEDDERS = {}` ("add ONE line per provider"). `get_embedder()` returns `None` when `RAG_EMBEDDING_PROVIDER` is empty → state `not_configured`. **No fallback embedder.**
- `core/status.py`: computes the states, cached for `RAG_STATUS_CACHE_SECONDS`.
- `core/search.py`: cosine distance (`embedding <=> :q`), `score = 1 - distance`.
- `core/ingest.py` + `core/chunker.py`: ingest with `content_hash` dedup; bulk insert of pre-computed vectors, validating the dimension and `embeddingModel`.
- `api/routes.py`:
  - `/v1/status`, `/v1/search`
  - `/v1/documents` (GET, POST, DELETE) and `/v1/chunks/bulk`: admin only, checked via `X-User-Role`
  - wrong service token → 401
- `RAG/README.md`: how to add an embedder, ingest, change the dimension (new RAG migration + re-embed), and run the tests.

**P10.5 Backend client `Backend/integrations/rag_client.py`** (written once against contract v1)
- `status()`:
  - empty `RAG_SERVICE_URL` → `state='not_deployed'`
  - connection error or timeout → `state='unreachable'`
  - response not matching the contract → `state='error'`
- `search(query, top_k, filters)`.
- Uses `httpx` with `RAG_TIMEOUT_S` and sends the token plus identity headers. A RAG problem is reported, never replaced by other knowledge.

**P10.6 Generic proxy `Backend/routes/rag_proxy.py`**
- `/api/rag/{path:path}` (all methods) → `RAG_SERVICE_URL/{path}`. Forwards the body, query string, identity headers and token.
- Access rules are in P3.6. No RAG-specific logic in the Backend, so new RAG endpoints need **zero** Backend changes.

**P10.7 Isolation tests**
- `test_rag_isolation.py`: scan the AST of `Backend/` and `Database/` for imports of `RAG`, and of `RAG/` for imports of `Backend` or `Database` → none allowed.
- `RAG/tests/test_contract.py`: the shapes of `/v1/status` and `/v1/search` match CONTRACT.md (pgvector testcontainer + a test-only fake embedder).

**P10.8 `docs/RAG_INTEGRATION.md`:** "To build the RAG, work only in `RAG/`. Keep `/v1/status` and `/v1/search` compatible with contract v1. Set `RAG_SERVICE_URL` and `RAG_SERVICE_TOKEN` in `Backend/.env` once."

---

### P11 — Agent graph (LangGraph)

**P11.1 State** (`agents/graph/state.py`; delete `AgentStateV2`)
```python
class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    user_role: str
    department_id: str | None
    session_id: str
    query_id: str | None
    turn_id: str
    event_job_id: str | None           # set only for event turns (P11.10)
    rag_status: dict
    rag_hits: list
    slots: dict                        # category, city, us_state, quantity, required_fields, source, fresh_within_days
    last_search: dict | None           # turn_id, slots_hash, total, returned, lead_ids, sufficient, reasons
    pending_proposal: dict | None      # id, source, args, missing, question, tool_call_id
    confirmed: bool
    active_job_id: str | None
    decision: str | None               # D10
    summary: str
    tool_steps: int
    trace: list                        # ordered tool trace for this turn
```

**P11.2 Checkpointer** (`agents/graph/checkpointer.py`)
- `ConnectionPool(conninfo=settings.CHECKPOINT_DB_URL, max_size=10, open=True, kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0})`
- `PostgresSaver(pool)`
- Call `setup()` once in the API lifespan and in `Database/setup.py`; close the pool on shutdown.
- `scripts/purge_checkpoints.py --older-than-days CHECKPOINT_RETENTION_DAYS`.

**P11.3 Graph wiring** (`agents/graph/graph.py`)
```python
g = StateGraph(AgentState)
g.add_node("load_context", load_context)
g.add_node("rag_retrieve", rag_retrieve)
g.add_node("agent", call_model)
g.add_node("tools", ToolNode(READ_TOOLS, handle_tool_errors=True))
g.add_node("validate_proposal", validate_proposal)
g.add_node("ask_confirmation", ask_confirmation)
g.add_node("await_confirmation", await_confirmation)
g.add_node("enqueue_job", enqueue_job)
g.add_node("finalize", finalize)

g.add_edge(START, "load_context")
g.add_edge("load_context", "rag_retrieve")
g.add_edge("rag_retrieve", "agent")
g.add_conditional_edges("agent", route_after_agent, ["tools", "validate_proposal", "finalize"])
g.add_edge("tools", "agent")
g.add_conditional_edges("validate_proposal", route_after_validate, ["agent", "ask_confirmation", "enqueue_job"])
g.add_edge("ask_confirmation", "await_confirmation")
g.add_conditional_edges("await_confirmation", route_after_confirmation, ["enqueue_job", "validate_proposal", "agent"])
g.add_edge("enqueue_job", "agent")
g.add_edge("finalize", END)
graph = g.compile(checkpointer=checkpointer)
```
- `route_after_agent`:
  - no tool calls → `finalize`
  - `tool_steps >= MAX_TOOL_STEPS` → `finalize`
  - any `propose_scrape` call → `validate_proposal`
  - otherwise → `tools`
- `route_after_validate`:
  - refusal written → `agent`
  - valid and (`AUTO_SCRAPE` or `confirmed`) → `enqueue_job`
  - valid → `ask_confirmation`
- `route_after_confirmation`:
  - `approve` → `enqueue_job`
  - `modify` → `validate_proposal` (with `confirmed=True`)
  - `reject` / `unrelated` → `agent`
- Export `graph.get_graph().draw_mermaid()` to `docs/agent_graph.md` in CI.

**P11.4 Nodes**
- **`load_context`:**
  - Build the system message each turn from:
    - `prompts/system.md`
    - the source catalogue (`describe_for_llm()`)
    - a KB block (state + message; excerpts with chunk ids when ready)
    - `slots`, a summary of `last_search`, and `summary`
    - unseen `system_event`s (`notified=false`)
  - The system message is **not** stored in `messages`.
  - Reset `tool_steps=0`, `trace=[]`, `confirmed=False`.
- **`rag_retrieve`:** runs once per new human turn.
  - `rag_status = rag_client.status()`; if available, `rag_hits = rag_client.search(last_human_text, RAG_TOP_K)`.
  - Add trace entry 1: `{tool: 'rag_retrieve', state, hit_ids}`.
  - Never raises.
- **`agent` (`call_model`):**
  - Call `invoke_llm(get_chat_model(ALL_TOOL_SCHEMAS), [system, *trim_messages(...)])` within `HISTORY_TOKEN_BUDGET`, using `strategy='last'` and `start_on='human'`.
  - Never split an AI tool-call message from its ToolMessages.
  - Increment `tool_steps`. `LLMUnavailable` propagates.
- **`validate_proposal`:**
  - Answer every non-`propose_scrape` tool call in the same AI message with `ToolMessage("Not executed: call propose_scrape alone.")`.
  - Check, read-only:
    - `last_search.turn_id == turn_id`, the same `slots_hash`, and `sufficient is False`
    - the source is in `scraper_ids()` and `check_ready` passes
    - the rate limit is not exceeded
    - every argument is supported by the source (otherwise refuse and list what the source supports)
  - On failure, answer the `propose_scrape` call with a refusal ToolMessage that gives the reason.
  - On success, set `pending_proposal = {id: sha256(session_id, query_id, normalized args), source, args, missing, tool_call_id}`.
- **`ask_confirmation`:**
  - One `invoke_llm` call (no tools) that writes a short confirmation question in the user's language from `pending_proposal`. Store it in `pending_proposal.question`.
  - **Do not** add it to `messages`; the `propose_scrape` tool call stays open.
  - This is a separate node, so it doesn't re-run when the graph resumes.
- **`await_confirmation`:**
  - `decision = interrupt({"type": "scrape_confirmation", "proposal": pending_proposal, "question": pending_proposal["question"]})`. Nothing before this line writes to the DB.
  - `approve` → continue.
  - `reject` → answer the open call with `ToolMessage("User declined the scrape.")`, set `decision='DECLINED'`.
  - `unrelated` → `ToolMessage("User did not confirm; their new message follows.")` + `HumanMessage(decision['text'])`.
  - `modify` → apply `decision['edits']` to `pending_proposal.args`, set `confirmed=True`.
- **`enqueue_job`:**
  - Call `enqueue_scrape(..., idempotency_key=pending_proposal['id'])` in a `session_scope`. Map `category` → `keyword`, and `city` / `us_state` → location.
  - Answer the open call with `ToolMessage(json {job_id, status, created})`, or the error reason.
  - Set `active_job_id`, `decision = 'PARTIAL' if last_search.total > 0 else 'SCRAPER'`, `pending_proposal=None`.
- **`finalize`:**
  - Answer any dangling tool calls with `ToolMessage("not executed: step limit")`.
  - If the last message isn't a final AI answer, make **one** more `invoke_llm` call (no tools) for the final answer.
  - Call `persist.save_turn(...)` (P11.8).
  - Groundedness check: every number in the reply must appear in this turn's tool or RAG outputs; otherwise log `groundedness_warning`.
- **`summarize`** (optional, inside `load_context`): when the message count exceeds `SUMMARY_TRIGGER_MESSAGES`, make one LLM call to update `summary` and remove old messages with `RemoveMessage`.

**P11.5 Tools** (`agents/graph/tools/*`)
- Each tool opens `session_scope()`. Identity comes from `Annotated[dict, InjectedState]` (hidden from the model).
- Outputs are compact: ≤ 20 items, short fields. Each call appends to `trace`.
- Rename the old `state` (US state) argument to `us_state`.

| Tool | Args (model-visible) | Behaviour |
|---|---|---|
| `knowledge_base_status` | — | `rag_client.status()` |
| `search_knowledge_base` | query, top_k ≤ 10 | follow-up KB search; error text if the KB isn't ready |
| `search_leads` | category, city, us_state, has_email, has_phone, source, quantity (1–1000; the prompt says use 20 when unstated), fresh_within_days, include_expired, page | repo search (P2.6); `sufficient = total ≥ quantity` and required fields present; returns `Command(update={last_search, slots, messages:[ToolMessage]})` |
| `count_leads` | filters, group_by ∈ {source, city, state, category, status} | grouped counts |
| `get_lead` | lead_id | full record |
| `list_sources` | — | `describe_for_llm()` |
| `list_datasets` / `get_dataset_leads` | — / dataset_id, limit, offset | D9-scoped |
| `get_job_status` | job_id? | jobs created by the user **or** linked to the user's queries (admin: any); includes `waiting_for`, `error_message` |
| `resume_job` | job_id | own job in `WaitingForUser` → `resume_requested=true` |
| `cancel_job` | job_id | own job → `cancel_requested=true` |
| `propose_scrape` | source, category, city, us_state, quantity | schema only; handled by `validate_proposal`, never by `ToolNode` |

**P11.6 System prompt** (`prompts/system.md`)
- Remove the hard-coded "Available Data Sources" list; the catalogue is generated.
- Rules:
  1. The knowledge base is consulted first automatically. Use its excerpts for knowledge questions and cite them as `[kb:<chunk_id>]`.
  2. If the KB isn't available and the question depends on it, say so using the KB status message.
  3. Always call `search_leads` before `propose_scrape`; only propose when the results are insufficient.
  4. Never invent records, counts, IDs or statistics.
  5. If no quantity is given, use 20 and say so.
  6. Use 2-letter `us_state` codes.
  7. Expired bids are excluded unless the user asks for past bids.
  8. Don't retype long lists; the UI renders `records`.
  9. Mention partial results and offer to fetch the rest.
  10. When a job waits for a CAPTCHA, explain what to do, and call `resume_job` when the user says it's solved.
  11. A message starting with `[JOB EVENT]` is a system notification: tell the user the outcome briefly using its numbers.
  12. Reply in the user's language, including Roman Urdu.

**P11.7 Runner** (`agents/graph/runner.py`): `run_turn(user, session_id, text, client_message_id)`
1. `ensure_session`: create the session if missing (`agent-master`, the user's department); if another user owns it → 403.
2. **Lock:** `pg_try_advisory_lock(hashtextextended(:sid, 0))` on a dedicated connection. Retry for up to 30 s, then 409 "session busy". Unlock in `finally`. Delete `_session_locks`.
3. **Retry of the same message:** if a `queries` row with (`session_id`, `client_message_id`) exists:
   - status `llm_unavailable` → `graph.invoke(None, config)` resumes the failed turn (E3)
   - already answered → return the stored response
4. **Pending confirmation:**
   - `state = graph.get_state(config)`; if an interrupt is pending (accessor from E2), call `classify_confirmation(text, pending)`.
   - That is `invoke_structured(ConfirmationDecision{decision: approve|reject|modify|unrelated, edits?, text}, …)`, LLM only.
   - Then `graph.invoke(Command(resume=decision), config)`. The reply belongs to the original query (`pending_proposal`'s `query_id`); no new query row.
5. **Failed earlier turn** (`state.next` non-empty, different `client_message_id`):
   - Mark the old query `abandoned`.
   - Answer its dangling tool calls via `update_state(...)` (E7/E8).
   - Then continue as a normal turn.
6. **Normal turn:**
   - Create a `queries` row: `status='received'`, `client_message_id`, `turn_id=uuid4`, `parameters={}`, `user_id`, `session_id`, `query_text`.
   - Invoke with the initial state.
   - `config = {'configurable': {'thread_id': session_id}, 'recursion_limit': settings.RECURSION_LIMIT}`.
7. **After invoke, if an interrupt is pending:** call `persist.save_paused_turn(...)`:
   - the user message
   - the question as a display message (`msg-<cid>-assistant`, role `assistant`, metadata `{kind: 'confirmation_question'}`)
   - query status `awaiting_confirmation`
   - return `pendingAction`
8. **`LLMUnavailable`:** persist the user message, set query `llm_unavailable` and decision `LLM_UNAVAILABLE`, return HTTP 503 per D4.
9. **Any other exception:** roll back, log with `exc_info`, set query `failed`, return HTTP 500 `{error: {code: 'INTERNAL_ERROR'}}`.

**P11.8 `persist.py`** (shared by `finalize`, paused turns, event turns, LLM failures; one `session_scope`, deterministic IDs per D17)
- `save_turn`:
  - the user message (once) and the assistant reply, with `message_metadata={query_id, turn_id}` and the ordered `tool_trace`
  - update `queries`: `parameters={slots, rag_state, rag_hit_ids}`, `decision`, `status`, `records_returned`, `served_at`, `job_id`
  - write `query_results` for `last_search.lead_ids` (rank order)
  - mark injected events `notified=true`
- **Decision when no scrape:**

  | Situation | Decision |
  |---|---|
  | sufficient search | `DB` |
  | answered from the KB only | `KB` |
  | no data tools used | `NONE` |
  | clarifying question | `CLARIFY` |

**P11.9 Response mapping** (additive; keep the existing fields)
- New fields: `records` (same serializer as `/api/leads`), `total`, `queryId`, `decision`, `jobId`, `pendingAction`, `kb: {state, available, hits: [{chunkId, title, score}]}`.
- `proposedActions[0]`: `{actionType: 'scrape', label: <the LLM question>, parameters: proposal, requiresConfirmation: true}`.
- `updatedRequirement` comes from `slots`, with `null` for unknown values. Never `'Not specified'`.

**P11.10 Event turns:** `run_event_turn(session_id, job_id)`
- Take the lock. Skip if an interrupt is pending.
- Invoke with `HumanMessage("[JOB EVENT] " + json summary, additional_kwargs={"hidden": True})` and `event_job_id`.
- The LLM writes the notification. Persist it as `msg-evt-<job_id>-assistant` under the job's `query_id` and mark the event notified.
- `LLMUnavailable` → leave the event unseen. The UI hides messages flagged `hidden`.

**P11.11 Endpoints** (`routes/bot.py`)

| Method | Path | Behaviour |
|---|---|---|
| POST | `/api/bot/chat {sessionId, message, clientMessageId}` | `run_turn` |
| POST | `/api/bot/confirm {sessionId, decision: approve\|reject, clientMessageId}` | sends "Yes, run the proposed scrape." or "No, don't run it." through `run_turn` (the LLM classifies) |
| POST | `/api/bot/confirm-and-generate` (shape unchanged) | no pending interrupt → 409 `{success:false}`; otherwise same as confirm/approve; returns the real `jobId`, `scriptId`, and `datasetId` (null until the worker creates it) |
| GET | `/api/bot/sessions` | the user's own sessions |
| GET | `/api/bot/sessions/{id}/messages?after=<iso>` | owner only; excludes hidden messages |

---

### P12 — API & admin panel

**P12.1 `app.py`**
- Routers only: `auth`, `bot`, `admin`, `jobs`, `leads`, `scripts`, `rag_proxy`.
- Lifespan: settings check, `sync_env_users`, `sync_sources`, `checkpointer.setup()`, close pools.
- Remove the reaper, the `db_session_cleanup` middleware (it has an `except: pass`), and the manual endpoints (P9.2).
- `/health/ready`: DB `SELECT 1` + checkpointer pool check.
- `/health`: `{status, scrapers: len(scraper_ids()), llmConfigured, ragState}`.

**P12.2 Scoping & serializers** (`routes/serializers.py`, `services/visibility.py`)
- `/api/jobs`: own jobs or jobs linked to own queries; admin sees all.
- `/api/leads`: a user sees leads in their `query_results` plus their jobs' datasets; admin sees all.
- `/api/datasets`: a user sees their own jobs' datasets; admin sees all.
- `/api/leads/export.csv`: same scoping, streamed.
- Lead serializer:
  - `location` (`"City, ST"`), `city`, `state`, `sourceCode`, `dueAt`
  - email/phone from the contact or the org
  - `null` when unknown; drop `'00:00'`, `'New'`, `'Scraper Job'` defaults.

**P12.3 Admin** (`routes/admin.py`, `Depends(get_db)` everywhere)

| Method | Path | Returns |
|---|---|---|
| GET/POST/PATCH/DELETE | `/api/admin/users…` | P3.4 |
| GET | `/api/admin/requests?user_id&from&to&decision&source&page&page_size` | request log; `to` inclusive (`< to + 1 day`); invalid dates → 400 |
| GET | `/api/admin/requests/{id}` | request, slots, decision, KB state + hits, job (incl. `errorMessage`), transcript for this query + job events, ordered tool trace, **rows served** (one query with `selectinload`, no N+1) |
| GET | `/api/admin/users/{id}/requests` | user timeline |
| GET | `/api/admin/users/{id}/sessions`, `/api/admin/sessions/{id}/messages` | read any chat (including hidden event messages) |
| GET | `/api/admin/stats` | D10 counts, jobs by status, duplicates prevented, LLM-unavailable turns, KB usage |
| GET | `/api/admin/requests/export.csv` | streamed; same filters and validation |

- Remove `except Exception: pass`.
- The `source` filter goes through `jobs.script_id`.

**P12.4 Postman** — add:
- login (Admin/Admin, User123/User123) with bearer auth
- admin users and activity
- chat, confirm, the messages poll
- jobs cancel
- the RAG proxy

---

### P13 — Frontend (`AI Powered/`; verify first — only types were audited)

**P13.1 Audit** — read these files and record what each currently does in PROGRESS.md (including any mock data):
- `AuthContext.tsx`, `Login.tsx`, `RoleSwitcher.tsx`, `DataOpsContext.tsx`
- `api.service.ts`, `agent.service.ts`
- `AgentChat.tsx`, `ConfirmationModal.tsx`, `RequirementSummaryPanel.tsx`
- `Sidebar.tsx`, `App.tsx`

**P13.2 Auth**
- Login form: username + password → `/api/auth/login`.
- Keep the token in memory + `sessionStorage`; send `Authorization: Bearer` on every call; a 401 logs the user out.
- `UserRole = 'admin' | 'user'`. Remove `RoleSwitcher` (S4).

**P13.3 Types (additive)**
- `BotChatResponse`: `records?`, `total?`, `queryId?`, `pendingAction?`, `kb?`, `decision?`.
- `BotConfirmResponse.datasetId: string | null`.
- `User.username`. `Lead.dueAt?`.
- Error type for the 503 `LLM_UNAVAILABLE` response.

**P13.4 Chat**
- Generate a `clientMessageId` (uuid) per message.
- Render `records` with `LeadTable`.
- Show Approve/Reject from `pendingAction`; they call `/api/bot/confirm`.
- On 503: show "The AI API is not responding" with a **Retry** button that resends the same `clientMessageId`.
- Show a KB status chip.
- While a job is active, poll the messages endpoint and refresh the records on a new assistant event message.
- Stop sending `history`.

**P13.5 Admin UI** (admin only)
- **Users:** list, create, reset password, disable. Built-in accounts are read-only.
- **Activity:** filters → request detail (transcript, KB hits, tool trace, rows served, job).
- **Knowledge base:** status, documents (list, upload text, delete) via `/api/rag/v1/...`.

**P13.6 Hide features with no backend (S11)**
- Campaigns, call/email modals, Gantt, Employees, Departments, Workflows, Analytics, DataRequests stepper, Scripts "Run".
- Remove their routes and menu items; keep the code.
- Keep: Agent, Leads, Datasets, Jobs, Settings, and the Admin pages.

**P13.7 Checks:** `npm ci && npm run build && npx tsc --noEmit && npm run lint` all pass.

---

### P14 — Docker & deployment

- **`Dockerfile`** (repo-root context):
  - copy `Backend/` and `Database/`
  - `PYTHONPATH=/app:/app/Backend`, a non-root user
  - `CMD ["uvicorn","app:app","--app-dir","/app/Backend","--host","0.0.0.0","--port","8000"]`
- **`RAG/Dockerfile`:** its own image.
- **`docker-compose.yml`:**

  | Service | Configuration |
  |---|---|
  | `postgres` | `pgvector/pgvector:pg15` (S12: `pg_dump` first; restore into a fresh volume if the existing one is incompatible), healthcheck |
  | `migrate` (one-shot) | `python Database/setup.py` (create DB, `alembic upgrade head`, checkpointer setup, seed) + `python -m RAG.migrate` |
  | `api` | `env_file: Backend/.env`; override `DATABASE_URL` / `CHECKPOINT_DB_URL` to the `postgres` host; no `--reload`; no bind mount (dev mounts go in `docker-compose.override.yml`); depends on `migrate: service_completed_successfully` |
  | `worker` | same image; `python -m worker`; `SELENIUM_MODE=remote`, `SELENIUM_REMOTE_URL=http://chrome:4444/wd/hub` (verify the path for the pinned image) |
  | `rag` | `python -m RAG`; `env_file: RAG/.env` |
  | `chrome` | `selenium/standalone-chrome` (pinned version), `shm_size: 2g` |

  Remove `redis` and `browserless/chrome`.
- **Requirements:**
  - Split into `requirements.txt` (prod) and `requirements-dev.txt` (pytest, testcontainers, ruff, mypy).
  - Add `pgvector`, `httpx`, `python-dateutil`, `bcrypt` (only if used).
  - Remove `rq`, `redis`, `passlib`, `webdriver-manager`, and `testcontainers` from prod.
  - Lock with `uv pip compile` or `pip-compile`.
- **`.dockerignore`:** `.env*`, `.venv`, `node_modules`, `__pycache__`, `_unused_scripts/`, scraper outputs, `docs/baseline`.
- **Done when:** `docker compose up --build` → migrate succeeds, the api is ready, the rag status is reachable, and the worker claims a job (test profile with `SCRAPER_MODE=fixture`).

---

### P15 — Dead code & hygiene (S4 before each deletion)
- **Delete if unused (grep first):**
  - `agents/llm/{config,factory,openai_compatible,provider,chat_models}.py`
  - the `scrappers/__init__.py` runners
  - `execution/{registry,dispatcher,captcha_manager,contract}