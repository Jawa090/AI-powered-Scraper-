# DataOps AI Extraction Platform

Users request companies and procurement opportunities through the AI agent. The application asks for missing requirements before any knowledge-base lookup, record search or scraping. Once requirements are complete, it checks the knowledge base, searches PostgreSQL with the interpreted criteria, asks for approval when more data is needed, and saves scraped records before delivering them. Admin Activity shows each user's exact delivered data under their email, with the administrator's data under `admin`.

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for completed changes, verification evidence and remaining limitations. [PROJECT_AUDIT_AND_IMPLEMENTATION_PLAN.md](PROJECT_AUDIT_AND_IMPLEMENTATION_PLAN.md) preserves the original audit.

## Requirements

- Python 3.11 (verified with the pinned requirements).
- Node.js 22.12 or newer; CI and local verification use Node 24.
- PostgreSQL; the Docker configuration uses PostgreSQL 16 with pgvector.
- Google Chrome for local browser scrapers, or the Selenium service in Docker.
- At least one configured AI provider.

## Local setup

Run commands from the repository root. Activate a Python virtual environment first.

```powershell
python -m pip install -r Backend/requirements.txt -r RAG/requirements.txt
```

The existing root `.env` is supported. Configuration precedence is process environment, the file named by `DATAOPS_ENV_FILE`, `Backend/.env` when present, otherwise the root `.env`, with example defaults underneath. An explicitly named missing file is an error. Avoid creating `Backend/.env` over an existing root configuration without copying the needed values.

For a new installation, copy `Backend/.env.example` to `Backend/.env` and configure:

- `DATABASE_URL=postgresql+psycopg://...` and `CHECKPOINT_DB_URL=postgresql://...`.
- A `JWT_SECRET` of at least 32 characters. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `DEEPSEEK_API_KEY`, `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY`. The provider chain tries DeepSeek, Gemini, then OpenRouter; plain, structured and tool calls use the same fallback behavior. Provider model names are configurable.
- `NYSCR_USERNAME` and `NYSCR_PASSWORD` for NYSCR. Other current scrapers need no account.
- `AUTH_USER_EMAIL` if the built-in normal user needs an email heading. Administrators can add or update normal-user emails in User Management.

Initialize a new database or upgrade an existing installation:

```powershell
python Database/setup.py
```

Setup applies migrations, initializes conversation checkpoints and seeds reference data idempotently. It preserves existing accounts, password resets, disabled status and records. The approved migration has already been applied to this workspace's configured database.

Start the API and its background worker together:

```powershell
python Backend/run_server.py
```

Alternatively, start the API directly; local development still supervises its worker:

```powershell
python -m uvicorn app:app --app-dir Backend --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```powershell
cd 'AI Powered'
npm ci
npm run dev
```

Open http://localhost:5173. API documentation is at http://localhost:8000/docs. Fresh example databases seed `Admin / Admin` and `User123 / User`; environment settings may choose different initial credentials. Existing DB passwords take precedence after setup. Use User Management to reset a normal account.

## NYSCR sign-in and robot verification

NYSCR may require a person to complete robot verification. The worker preserves a `WaitingForUser` job, and Job Detail provides the configured viewer link plus Resume and Cancel actions. After completing verification in the browser, use Resume.

For a local persistent Chrome session on Windows, launch Chrome with a dedicated profile:

```powershell
$chromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$profilePath = Join-Path (Get-Location) '.nyscr-browser-profile'
Start-Process -FilePath $chromePath -WindowStyle Normal -ArgumentList @(
    '--remote-debugging-port=9222', '--remote-debugging-address=127.0.0.1',
    ('--user-data-dir="' + $profilePath + '"'), '--new-window',
    'https://www.nyscr.ny.gov/Account/Login'
)
```

Set `NYSCR_DEBUGGER_ADDRESS=127.0.0.1:9222` in the selected environment file, then restart the worker. The scraper fills configured login fields when login is required; complete the human verification and sign in. Keep this window open while using its session. An expired session requires sign-in again. The local browser profile is ignored by Git and Docker. Use one local worker with this shared browser session.

Docker workers use the remote Chrome service instead, with the viewer at http://localhost:7900; local debugger attachment is cleared in Compose.

Local development automatically starts and supervises one scraper worker. It reuses that worker across API reloads and restarts it after an exit. A queued job reports its queue position and whether another scrape is running. Production and Docker use the separately configured worker service; `python run_worker.py` remains available for manual worker operation.

## Records, search and audit

“10 roofing constructors from NY newyork” means ten roofing companies in New York city, NY. Trade, record type, city/state, source, required contacts, freshness, expiry and the New data only preference are applied before records count toward the request. Bid sources supply opportunities; they cannot substitute for contractor companies.

Before any data access, every record request needs record type, trade/category, location, quantity and an explicit email/phone preference (email, phone, both or neither). For “1 roofing contractor,” the assistant asks for location and contact requirements and waits. For the ten-company example above, it asks for the missing contact preference. Explicit “any category,” “any location,” statewide plus a state, and “neither” are valid answers. Clarification replies preserve supplied requirements; new requests start with their own criteria. Source and freshness remain optional.

JWiz collection requires a city or state. When the user allows any location, the database search can remain unrestricted, but the assistant must ask for a collection location before approving or queueing JWiz.

When the verified search falls short, the assistant creates a targeted scrape proposal and displays an **Action** button. Clicking Action approves and queues that scrape; Cancel declines it. The worker saves every valid record extracted within the run budget using the database deduplication rules, then selects the delivery. “Get 2 more” requests two additional records and automatically excludes versions already delivered to that user, even when the New data only checkbox is off.

The AI interprets short answers and references semantically using pending requirements and recently shown records. A request for comprehensive information fills both contact requirements and makes available details accessible by opening a result row; it does not change the requested record count. A follow-up about a shown contractor retrieves that exact record, reports unavailable fields honestly, and asks which record the user means when the reference is ambiguous. Interpretation comes from the model's structured output, not a keyword-to-response lookup.

Scrapers can return fewer matching records than requested. The worker collects through the source's bounded run limit even after enough matches have been found, and saves all valid extracted records, including unrelated and incomplete listings. If the canonical search fulfills the request, only the requested number of matching rows is delivered. Otherwise, the user receives the run's entire deduplicated recovered dataset with an explicit requirements-not-fulfilled banner, matching count, requested count and model explanation. Recovered rows never count toward fulfillment, and unknown categories or cities are not inferred from the request. A source interruption preserves data already saved; an empty run gets an explicit no-recoverable-records explanation. New data only excludes versions already delivered to that user; a material update can become eligible again. Completion supplies the remaining distinct records when an initial partial response was already delivered in this mode.

Each scraper runs in an owned process. Five minutes without a new extracted record stops that process, preserves committed and buffered records, and sends an active chat a timeout report. The report describes all four sources, offers a rerun and identifies the best compatible alternative by record type and geographic coverage. It states when no alternative fits. A rerun or source change still passes through the Action approval flow.

Clear Chat closes the old session, blocks further model actions, removes its checkpoint and cancels its scraper subscriptions. Extracted data remains deduplicated in PostgreSQL. Cancellation outcomes and recovered-record counts are logged on the backend; no cancellation messages, dumps or delivery reports appear in user chat or admin activity, including reports from the earlier implementation. A cleared chat receives no timeout retry prompt. Work shared with another active user remains available to that user.

Chat displays results in a table. Click a row to inspect its details; complete field lists and raw source JSON are not automatically printed into the conversation. The assistant receives fresh job states each turn, so terminal jobs are not described as still queued.

Every delivered row has an immutable ordered snapshot. Admin Activity displays these snapshots under the user's stored email and `admin`, with the understood request, fulfillment status, recovered or matching delivery type, transcript, job links and authenticated CSV export. Admin and user receive the same frozen rows; the admin sees recovered dumps only for unfulfilled requests and requested matches only for fulfilled requests. Zero-record scrape completions also remain visible. Legacy receipts created before snapshots existed are marked as historical values unavailable; the application does not reconstruct invented past values. Missing legacy user emails are shown explicitly and can be corrected in User Management.

| Source | Record type | Coverage |
|---|---|---|
| JWiz | Company | Directory listings; observed location and profile trade are validated |
| Bonfire | Opportunity | City of Dallas, TX |
| DASNY | Opportunity | New York State |
| NYSCR | Opportunity | New York State; configured login and occasional human verification |

## Optional knowledge base

Set `RAG_SERVICE_URL` and the same `RAG_SERVICE_TOKEN` in Backend and RAG configuration, then run `python -m RAG`. An unconfigured, unavailable or empty knowledge base has an explicit status. The production embedding and ingestion pipeline remains deferred as specified in the project documentation.

## Verification

The designated test database must be separate from application data. Tests fail closed when the configured database is not a test database.

```powershell
python -m pip install -r requirements-dev.txt ruff mypy
python docs/audit/run_integration.py --with-conftest Backend/tests RAG/tests
python -m ruff check Backend Database RAG --select E9,F821,F822,F823,F631
python -m mypy --follow-imports=skip --ignore-missing-imports Database/search.py Backend/agents/graph/state.py
cd 'AI Powered'
npm run lint
npm run build
```

`run_integration.py` allocates and records an isolated database on the configured PostgreSQL server; the account needs database-creation permission for its first run. Live audit scripts make external requests and are opt-in; `verify_configured_flow.py` also writes genuine source data and audit entries to the configured database.

## Docker

Copy Backend and RAG example environments, set a random JWT secret and matching RAG service tokens, then run `docker compose up --build`. Compose initializes migrations before API/worker/RAG startup. The frontend is started separately with npm.

The PostgreSQL image uses version 16. Existing data volumes from other major versions need a verified backup and upgrade/restore procedure before switching versions. Docker image build and boot checks are blocking in CI; Docker was unavailable on this workstation, so local container execution has not been verified.

## Further documentation

- [Adding a Scraper](docs/ADDING_A_SCRAPER.md)
- [Adding a Table](docs/ADDING_A_TABLE.md)
- [RAG Integration](docs/RAG_INTEGRATION.md)

## License

Proprietary. All rights reserved.
