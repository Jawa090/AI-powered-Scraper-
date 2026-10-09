# DataOps AI Extraction Platform

This document describes the implementation in this repository. Runtime behavior depends on environment configuration, database contents, provider availability, and the external scraper websites. Historical audit output is not a statement about the current database or a guarantee of current source availability.

## Purpose and current scope

Authenticated users can ask the AI agent to find company records or procurement opportunities. The agent interprets the request, applies it to the normalized PostgreSQL record store, and can offer a source-specific scrape when the matching record count is short. Scraping starts only after the user approves the displayed proposal.

The application includes a React frontend, a FastAPI backend, a LangGraph conversational agent, a PostgreSQL-backed worker queue, four website scrapers, a normalized record and delivery store, and a separate RAG service. The scraper and record-search workflow is the active product path.

The repository also retains UI pages and components for campaigns, calls, emails, departments, analytics, and other earlier prototype features. These are not all connected to the backend. In particular, call and email dialogs do not send messages or place calls through an external service.

## Architecture

The request path is: user → React frontend → authenticated FastAPI API → LangGraph agent → PostgreSQL search or RAG HTTP service. An approved scrape proposal creates or reuses a PostgreSQL job. A worker claims the job, runs a registered scraper adapter, normalizes and ingests records, then creates a durable completion event for the originating chat.

| Area | Implementation |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, and Recharts in **AI Powered/**. |
| API and agent | FastAPI routes, configuration, provider handling, LangGraph workflow, and background-job services in **Backend/**. |
| Scrapers | Adapter contract, source catalog, Selenium/network helpers, and four registered adapters in **Backend/scrappers/**. |
| Main database | SQLAlchemy models, repositories, normalization, ingestion, and setup in **Database/**; Alembic migrations are in **Backend/migrations/**. |
| RAG | An isolated FastAPI service, vector schema, migration, chunking, retrieval, and embedder interface in **RAG/**. The backend communicates with it over HTTP. |
| Worker | **Backend/worker.py** claims jobs from PostgreSQL, runs scrapers, ingests records, and produces completion events. |

The agent graph is recorded in [docs/agent_graph.md](docs/agent_graph.md). Scraper extension guidance is in [docs/ADDING_A_SCRAPER.md](docs/ADDING_A_SCRAPER.md), and RAG service integration notes are in [docs/RAG_INTEGRATION.md](docs/RAG_INTEGRATION.md).

## Request and scrape lifecycle

1. A user signs in and sends a message in the Agent page. The browser sends the message and a client message ID; it does not send the whole transcript. The backend loads the persisted LangGraph conversation.
2. A structured model call classifies the message and extracts criteria. Record requests must specify record type, category or explicit any category, location scope, quantity, and whether email and phone are required. The agent asks only for missing criteria and waits before accessing the database or knowledge base.
3. The chat location criterion is state-level: a state, statewide with a state, or explicit any location. The chat search schema does not have a city field. State names are normalized to postal abbreviations. Source adapters can have their own location requirements.
4. For a complete request, the agent checks RAG status/retrieval and can use its registered tools. Record search uses the normalized lead store and the request filters. A database error is treated as an error, not as an empty result.
5. If enough matching rows exist, the agent returns those rows. If the successful search for the current criteria is short, the agent may prepare a scrape proposal from a ready source with a compatible record type and coverage. It will not propose a scrape after a failed search.
6. The proposal is shown in chat with an approval action. Only explicit approval of the unchanged proposal can enqueue it. If the user changes the proposal, the new criteria must be searched and approved. The backend checks the proposal ID, search evidence, current session, source readiness, record type, and scraper parameters before enqueueing.
7. A PostgreSQL worker runs the approved source and saves valid extracted records through the canonical ingestion path. Each record is normalized and deduplicated; source errors do not erase records already committed.
8. On completion, the backend searches again with the original request criteria and freezes the displayed rows and their order in a delivery snapshot. Request fulfillment and scraper job status are separate facts: a job can finish with a shortfall.

For chat-linked jobs, the worker uses a collection limit of at least 100 records, or the approved missing quantity if it is larger. This gives the final filtered search more records to evaluate; it does not guarantee that the source will return that many records or that they will meet the request.

### Search filters and delivery

The canonical search supports record kind, category, state, contact requirements, source, freshness, expired-opportunity inclusion, and new-only delivery. Opportunities with past due dates are excluded unless expired records were explicitly requested. Category matching uses record category and descriptive fields rather than using a company name as category evidence.

New-only is per user. It excludes the same record version that the user has already received. When a record changes materially and its version increments, it can qualify again. It does not remove or hide the shared canonical record.

Every scraper record accepted by ingestion can remain in the job's dataset, even if it does not match the original request. The completion table is based on the original filtered search and can contain fewer than the requested number of rows. It does not automatically print the entire recovered scrape dataset into chat. Users can inspect authorized datasets and job results separately. The agent reports the shortfall and distinguishes matching results from the broader scrape run.

Delivery rows are stored in **query_results** with rank, record version, and a JSON snapshot of the values shown at delivery time. Later edits to a canonical record do not rewrite that snapshot. Admin Activity and its CSV export read the saved delivery values.

## Request interpretation and AI providers

The agent uses structured model output to identify intent and criteria, then application code validates and applies those criteria. Greetings, knowledge questions, job-status questions, and company/opportunity requests follow different paths. Follow-up answers can fill outstanding requirements; a new request does not silently inherit unrelated criteria.

The configured provider chain tries DeepSeek, Gemini, and OpenRouter, using provider-specific keys and model settings from the environment. A generic Gemini or OpenAI-compatible configuration is also supported. Plain chat, structured interpretation, and tool-bound calls use the same provider-chain handling. If all configured providers fail, the API returns an explicit 503 AI-unavailable response.

The model can call tools for knowledge-base status/search, lead count/search/detail, source and dataset discovery, and authorized job status/resume/cancel. Scrape proposal validation, ownership checks, and queue insertion are enforced by application code. A model response cannot directly execute a scraper.

## Scraper catalog

The source catalog is registered in **Backend/scrappers/controller.py**. It reports each adapter's record kind, geographic coverage, filters, readiness, and required configuration.

| ID | Source | Record kind | Declared coverage and requirements |
|---|---|---|---|
| jwiz | JWiz Commercial & Services Directory | Company | US business directory. The adapter requires a city or state to run; a chat request allowing any location still needs a collection location before a JWiz proposal is valid. Profile enrichment is configurable. |
| bonfire | Dallas City Hall Bonfire Portal | Opportunity | Dallas, Texas municipal opportunities; keyword and limit are supported. |
| dasny | DASNY RFP & Bid Opportunities | Opportunity | New York State public works and solicitations. |
| nyscr | New York State Contract Reporter | Opportunity | New York State procurement. Requires configured NYSCR credentials and may pause for human sign-in or robot verification. |

The three procurement sources cannot supply company/contractor records. A source's published coverage does not change the user's search criteria. Live websites can change, block requests, require human verification, or return fewer qualifying records than requested.

All adapters implement the common BaseScraper contract and return StandardRecord values. Fixture mode is limited to test environment configuration. Production worker runs execute a scraper in an owned process; the five-minute no-data watchdog is an inactivity timeout that resets whenever a record arrives. Buffered records are drained during shutdown and passed through normal ingestion.

## Jobs, sessions, and cancellation

Jobs are persisted in PostgreSQL. Workers claim queued jobs with row locking and SKIP LOCKED, so separate workers do not claim the same row. The job record stores source, parameters, status, progress, counts, errors, timestamps, worker heartbeat, and logs. Queue status includes position and whether another scrape is running.

| Status | Meaning |
|---|---|
| Queued | Waiting for a worker or earlier queued work. |
| Running | Claimed and executing. |
| WaitingForUser | Paused for a human action, such as portal verification. |
| Completed | The source run completed according to worker status rules. This does not alone prove the original request was fulfilled. |
| Partial | The source run or the linked request did not complete fully. |
| Failed | The run failed, timed out waiting for a user, or was marked stale. Previously committed records remain in the database. |
| Cancelled | Cancellation completed. |

Job Detail can display progress and logs, cancel a visible job, and resume one waiting for user action. A non-admin cannot cancel work shared with another user. If a chat is cleared, its session is closed, its checkpoint is removed, and cancellation is requested for its subscribed work. When another active chat shares that job, the cleared chat is detached without cancelling the shared job. Saved scrape data is retained; the cleared chat receives no cancellation delivery.

Chat sessions, requests, messages, job events, and LangGraph checkpoints are persisted separately. Client message IDs, proposal IDs, job idempotency keys, and database locks make retries safer. The application permits one active chat per user. In development with local Selenium, the API lifespan supervises a single local worker across API reloads. Other deployments run the worker separately.

## Storage, normalization, and access

The main PostgreSQL schema stores users, departments, agents, sessions, messages, requests, jobs, scrape runs, datasets, normalized records, contacts, sources, actions, session events, and delivery results. **Database/models/** contains the ORM definitions. The LangGraph checkpointer uses CHECKPOINT_DB_URL; it can point to the same PostgreSQL server while keeping conversational checkpoints distinct from the application's business records.

Companies and opportunities use different record identities:

- Company identity is based on a normalized fingerprint using available identity fields such as company name, domain, phone, or email.
- Opportunity identity uses the source plus its source-issued external ID.

Ingestion normalizes names, domains, emails, phones, state codes, and dates. It merges newly observed non-empty values, tracks a content hash/version, and records source aliases and dataset membership. Concurrent identity writes use database locking and unique keys.

Canonical records are shared across the application and are searchable by the chat agent. Regular-user list/detail APIs scope leads, datasets, jobs, and sessions to that user's deliveries, jobs, or subscriptions. Administrators can inspect all users' activity and records. The agent and API also enforce ownership when reading individual sessions, jobs, and datasets.

Login uses database-backed accounts, salted PBKDF2-SHA256 password hashes, and signed bearer tokens. Startup synchronizes the configured built-in user and administrator accounts without replacing an existing password hash or disabled status. The application supports one administrator; regular users are managed through the administrator API.

## Frontend

The active routes in **AI Powered/src/App.tsx** are:

| Route | Page |
|---|---|
| /agent | Natural-language request, criteria clarification, scrape approval, results, and chat history. |
| /leads | Authorized lead table and row detail drawer. |
| /datasets and /datasets/:id | Authorized dataset list and detail. |
| /jobs and /jobs/:id | Authorized job list and diagnostics/actions. |
| /settings | Settings UI shell. Several preference and profile controls are local UI state and are not persisted by the backend. |
| /admin/users | Administrator user management. |
| /admin/activity | Administrator request, transcript, tool trace, delivery, and export views. |
| /admin/kb | Administrator RAG status, document, and upload UI. |

Pages for dashboards, campaigns, employees, departments, workflows, analytics, scripts, and data requests remain in the source tree but are not active routes in the current application router. The Scripts API currently lists scraper metadata; it does not expose an HTTP endpoint to start arbitrary scrapes. Normal scrape execution is initiated through the approved agent workflow.

Some prototype details remain in the UI. In particular, missing industry or company-size values in the lead drawer have fixed display fallbacks and should not be treated as source-confirmed facts. Call and email dialogs update client-side state and display success messages; they do not connect to telephony or email delivery services.

## API surface

The backend OpenAPI page is available at /docs and ReDoc at /redoc.

| Area | Representative routes |
|---|---|
| Health | GET /health, GET /health/ready, GET /health/llm. Readiness checks PostgreSQL connectivity. /health/llm?probe=true performs a provider probe and requires administrator access. |
| Authentication | POST /api/auth/login, GET /api/auth/me. |
| Agent | POST /api/bot/chat/new, /api/bot/chat, /api/bot/confirm, /api/bot/job-update; session list, message history, and state reads are also provided. |
| Sources | GET /api/scripts, GET /api/scripts/{script_id}. These return registered scraper metadata and readiness. |
| Jobs | GET /api/jobs, GET /api/jobs/{job_id}, POST /api/jobs/{job_id}/cancel, POST /api/jobs/{job_id}/resume. |
| Datasets and leads | /api/datasets, /api/datasets/{dataset_id}, /api/leads, /api/leads/export.csv; lead status changes use PATCH /api/leads/{lead_id}/status and require administrator access. |
| Administrator | /api/admin/users, /api/admin/requests, /api/admin/deliveries, /api/admin/stats, request details, and CSV exports. |
| RAG proxy | /api/rag/{path}. Authenticated users can read status/search; other proxied RAG operations require administrator access. |

Liveness and readiness endpoints are public. Application data endpoints require bearer authentication. Administrator endpoints check the authenticated user's administrator role. The RAG service also checks its service token and, for document/ingestion operations, the forwarded administrator role.

## RAG service status

**RAG/** contains a separate FastAPI service with a rag PostgreSQL schema, migrations, document/chunk tables, sliding-window chunking, vector search, document lifecycle routes, and a BaseEmbedder interface. The API supports document ingestion and precomputed bulk chunk insertion when a compatible embedder and database schema are available.

There is currently no production embedder registered in **RAG/embedders/__init__.py**; its provider registry is empty and the example provider setting is blank. Therefore the checked-in service reports not_configured by default, and semantic ingestion/search are not operational until an embedder is implemented and registered. The admin upload UI is present but cannot make RAG available by itself. The RAG search request accepts a filters object, but the current SQL search does not apply those filters.

RAG status distinguishes states such as not_configured, extension_missing, empty, dimension/model mismatch, ready, and error. When not ready, semantic search returns a not-ready response rather than pretending there are relevant documents.

## Configuration and local operation

Use Python 3.11, Node.js 22.12 or newer, and PostgreSQL. Docker Compose uses PostgreSQL 16 with pgvector and a Selenium Chrome service.

Backend settings are validated at startup. The loader uses DATAOPS_ENV_FILE when set, otherwise Backend/.env if present, otherwise the repository-root .env; example values are the base configuration and process environment overrides file values. RAG settings use DATAOPS_RAG_ENV_FILE, RAG/.env, or the repository-root .env.

Important settings include:

- DATABASE_URL for the SQLAlchemy application database and CHECKPOINT_DB_URL for LangGraph checkpoints.
- JWT_SECRET, built-in user/admin credentials, CORS_ORIGINS, ENVIRONMENT, and log level.
- Provider-specific LLM keys/models, or generic provider configuration; timeout, retry, history, and tool-step limits.
- RAG_SERVICE_URL, RAG_SERVICE_TOKEN, timeout, and top-K settings for the optional RAG service.
- NYSCR credentials, Selenium local/remote mode and URL, browser headless settings, and source page limits.
- Worker polling, job heartbeat/staleness, CAPTCHA wait, checkpoint retention, and optional Sentry configuration.

Do not commit environment files, provider keys, database passwords, signing secrets, or scraper credentials. Replace development credentials and secrets before using a shared or externally reachable deployment.

### Local setup

From the repository root, install the backend and RAG dependencies:

    python -m pip install -r Backend/requirements.txt -r RAG/requirements.txt

Copy Backend/.env.example to Backend/.env, set a strong JWT secret, database/checkpoint URLs, allowed CORS origins, and at least one working LLM provider key/model. Add NYSCR credentials if that source is needed. Then initialize or migrate the database and reference data:

    python Database/setup.py

Start the API and its worker:

    python Backend/run_server.py

In a separate terminal, start the frontend:

    cd "AI Powered"
    npm ci
    npm run dev

The Vite configuration defaults to http://localhost:3000. The backend example environment currently lists CORS origins on port 5173, so include the actual frontend origin in CORS_ORIGINS before using the browser UI with that default Vite port.

The API runs on the configured API host/port (example port 8000). In development with SELENIUM_MODE=local, the API lifespan supervises the local worker. In other environments, run a worker separately with python run_worker.py.

### Docker Compose

Compose starts PostgreSQL, a one-shot migration service, the API, a separate worker, the RAG service, and remote Selenium Chrome. It expects Backend/.env and RAG/.env to exist. The frontend is not a Compose service; start it separately with npm. The Compose worker uses remote Selenium and exposes the Chrome viewer on port 7900.

## Tests and supporting utilities

Backend unit, integration, and API tests are under **Backend/tests/**; RAG contract tests are under **RAG/tests/**. Backend database tests must use an isolated test database, not application data. Frontend package scripts include npm run lint, npm run typecheck, and npm run build. Live scraper diagnostics under scripts/ may access external websites and are not offline unit tests.

Root utilities include run_scraper.py for direct source-adapter runs, run_worker.py for the queue worker, and Database/setup.py for schema setup. The direct scraper command is a developer utility and bypasses the agent approval and normal job/delivery workflow.

## Current operational limits

- External sources can change their pages, require credentials or human verification, block automation, and return fewer matching records than requested.
- The conversational location criterion is state-level or any-location; there is no conversational city criterion in the current search model.
- RAG has service/API scaffolding but no registered embedder in this repository.
- Calls, email delivery, and campaign execution are not integrated services. Some legacy pages and local-only controls remain in the frontend.
- The frontend default port and the example backend CORS list differ; configure CORS for the port actually used.
- Health readiness currently verifies the main PostgreSQL connection only. LLM provider and RAG status have their own checks; worker health is not included in /health/ready.
