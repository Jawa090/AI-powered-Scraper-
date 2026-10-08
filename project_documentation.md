# AI Data Agent Platform

## Project overview

The AI Data Agent Platform lets authenticated users request business leads and public procurement opportunities in natural language. The agent interprets the request, searches the shared PostgreSQL database, and proposes a source-specific scrape only when the database does not have enough qualifying records. The user must approve the proposed scrape with the **Action** control before a job is created.

The system uses an LLM to understand user intent and write ordinary chat replies. Source capabilities, required fields, ownership, approval, persistence, deduplication, cancellation, and delivery limits are enforced by application code and the database. The model must reason from the request and the available source descriptions; phrases such as “everything” are not handled by a canned keyword response.

This document records the intended behavior and the implementation decisions made during the project review. It also records the account cleanup that was explicitly requested and applied to the configured database.

## User-facing behavior

### Greetings and complete requirements

For a greeting such as “hi” or “hello,” the model writes a natural greeting and asks for the information needed to begin a data request:

- Record type: companies/contractors or bid opportunities.
- Trade/category, or an explicit request for any category.
- Location: city and state, statewide with a state, or an explicit any-location request.
- Quantity.
- Contact requirement: email, phone, both, or neither.

Source and freshness preferences are optional. A greeting must not initiate a database search, knowledge-base lookup, or scrape.

For a data request, the agent must ask for any missing required information before taking action. It preserves supplied requirements across short follow-up answers. An explicit “everything” request is interpreted in context: for a contractor record it requires both email and phone and requests the available stored details. The model supplies this interpretation through structured intent extraction; application code validates its output instead of matching fixed user phrases.

An any-location request is valid for a database search. A scraper may have additional execution requirements. JWiz needs a city or state to construct its search, so the agent asks for a location before it offers or queues a JWiz scrape. It must not invent a location.

### Search, approval, and results

The agent searches the database using the interpreted category, record type, location, quantity, contact fields, source, freshness, expiry, and the user's delivery history. The count and rows come from the same canonical search. The AI may not substitute opportunities for companies, or change the user's criteria to make a result appear sufficient.

If the database can meet the request, the agent returns the qualifying rows without scraping. If more records are needed, it prepares a source-compatible proposal based on a successful search for the same criteria in the current turn. It displays the proposal and an **Action** button. A scrape does not begin until the user activates Action. Repeated confirmation and message retries must not create duplicate jobs.

A scrape saves every valid record it extracts through its bounded source run, even when a record does not match the user's requested category, location, or contact requirements. Database identity and merge rules prevent duplicates; nonempty, newly observed fields can update an existing row. The request's matching search then determines what is delivered:

- When enough records meet every requested condition, the user sees only the requested matching rows.
- When the request is not fulfilled, the user is told which requirements were unmet and sees the deduplicated records recovered from that run, clearly identified as recovered data rather than matching results.
- A failed empty run reports the source error and zero recovered records. Recovered records remain saved even when the job ends as Partial or Failed.

Results appear in a table. When a user asks for “everything” about a requested record, the model interprets that request in context and the chat also shows the available user-facing fields for that record, such as its email, phone, website, source, address, and notes. Missing fields are identified instead of invented. A user can open a row to inspect its stored fields. Raw source JSON, internal logs, and unrelated records are not shown as a substitute for the requested results.

“New data only” is scoped to each user's delivery history. It excludes record versions that user has already received; a material update can qualify again. This preference does not delete or hide the shared canonical database record.

## AI and tools

The configured provider chain is DeepSeek, Gemini, then OpenRouter. The same provider handling is used for ordinary, structured, and tool-bound model requests. Temporary failures may be retried; an unavailable provider returns an explicit service error. The timeout completion path has a factual fallback so a user still receives a timeout explanation and choices when all model providers are unavailable.

Available agent capabilities include knowledge-base status/search, canonical record search, record details, source discovery, scrape proposals, and authorized job status, resume, and cancellation. The model chooses and explains actions, while code validates:

- All required request fields are present before a data action.
- A successful same-turn search shows that more records are needed.
- The source is registered, ready, compatible with the record type, geography, and filters, and satisfies its own execution prerequisites.
- A user-approved proposal is the proposal that is actually enqueued.
- A user can access only their own chat, jobs, and results; administrator access is separately authorized.

Knowledge-base support is integrated with the chat and admin APIs. Production document ingestion and embedding remain a separate, unfinished RAG capability; the application reports the actual service status and does not claim unavailable knowledge-base coverage.

## Scraper sources

| Source | Record type | Coverage and execution notes |
|---|---|---|
| JWiz Commercial & Services Directory | Companies/business listings | Broad US directory. Scraping requires a city or state; an unrestricted database search is allowed, but an unrestricted JWiz scrape is not. |
| Bonfire | Procurement opportunities | Dallas, Texas municipal opportunities. |
| DASNY | Procurement opportunities | New York State public works and procurement opportunities. |
| NYSCR | Procurement opportunities | New York State Contract Reporter. Credentials come from configuration; a human may need to complete a robot-verification challenge. |

A source catalog describes each source's record type, supported filters, geographic coverage, readiness, and execution requirements. A company request cannot be rerouted to one of the three bid sources. When a timed-out source has no compatible alternative, the interface says so instead of recommending an incompatible source.

JWiz's missing-location failure is prevented before approval and queueing. Its source metadata marks location as required, the model is told about that requirement, the proposal validator rejects an invalid proposal, and enqueue-time validation acts as a second guard. The website itself can still return fewer records than requested, and returned categories and locations must be verified from record data rather than inferred from a search page or directory footer.

## Jobs, queues, and timeouts

Jobs use the database as a persistent queue. A worker claims queued work with row locking so workers do not execute the same job. Job status, queue position, progress, source errors, records found, deduplication counts, and timestamps are persisted. A job waiting behind another job remains Queued and its status reports that it is waiting. A Failed, Partial, Completed, or Cancelled job is terminal; later replies must use the current stored status rather than repeat an earlier “queued” message.

Each scraper runs in an owned process. If it returns no new record for five minutes, the worker terminates that scraper process and records a timeout. The five-minute clock resets each time a record is received, so it is an inactivity limit rather than an overall scrape-duration limit. Records already ingested, and records recovered from the process buffer during shutdown, remain saved through the normal database deduplication path.

If a scraper times out while its chat is still active, the user sees the timeout, the recovered results when applicable, short descriptions of all four sources, an option to rerun the failed source, and the most likely compatible alternative when one exists. A retry or source change still requires the user to approve a fresh Action proposal. No compatible alternative is reported honestly.

In local development, the API supervises one worker using a PostgreSQL advisory lock. The worker persists across API autoreloads and is relaunched after an exit. Production and Docker can run the worker as a separate service. A worker crash must not leave a job falsely reported as actively running indefinitely; stale-job recovery records a terminal failure.

### Job states

| State | Meaning |
|---|---|
| Queued | Approved job is waiting for a worker or earlier queued work. |
| Running | A worker has claimed and is executing the job. |
| WaitingForUser | A source is paused for a human action, such as CAPTCHA completion. |
| Completed | Collection completed and the relevant requested rows were available. |
| Partial | Some records were recovered, but the run or request was incomplete. |
| Failed | The source or worker failed before delivering a fulfilled request. Any already saved data remains available under the recovered-data rules. |
| Cancelled | The user, administrator, or Clear Chat cancelled the work. |

A normal source error terminates that job; the worker then moves to other queued work. A terminal source error must not leave its job in the queue.

## Clear Chat

Clear Chat closes the old session, blocks subsequent model actions in it, removes its model checkpoint, and requests cancellation of scraper work tied to that chat. The user has one active chat. If a job is shared with another active user, clearing one subscriber detaches that chat without interrupting the other user's job.

Records already scraped are retained in PostgreSQL with deduplication. Cancellation details and recovered-record counts go to the backend log. Clear Chat does not create a user-facing or administrator-facing cancellation message, recovered-data dump, delivery, or activity report. Old cancellation reports from the previous behavior are suppressed in chat history, admin request/detail views, and exports. Cancellation state is not copied into the new model conversation or retried as a timeout request.

## Database and data integrity

PostgreSQL stores users, sessions, messages, requests, jobs, scrape runs, datasets, normalized records, contact details, source membership, delivery snapshots, and audit metadata. LangGraph checkpoints store model conversation state separately from the immutable request and record history. The RAG service owns its own knowledge-base data.

Records are shared and deduplicated globally. Opportunities use source plus source-issued solicitation identity. Companies use normalized identity fingerprints and source aliases. Ingestion is transactional and safe under concurrent jobs. Missing values remain null; a source error or a missing contact is never filled with invented data.

Every user delivery is frozen as an ordered snapshot with the request's understood criteria, fulfillment status, matching count, requested count, and delivery type. Later source updates cannot rewrite a previous snapshot. If requirements are fulfilled, the user and administrator see the requested matching rows. If they are not fulfilled, both see the recovered run data and the explicit shortfall. Administrators see each user's deliveries grouped under that user's stored email; accounts without an email are labeled by username, and the administrator's own deliveries appear under **admin**. A cancelled Clear Chat job is not a delivery and is not shown in this activity view.

## Accounts and access

Login uses database-backed accounts and signed tokens. Passwords are stored as hashes. The API rechecks account status, scopes records and sessions by owner, and limits administrative operations to the administrator. Only one administrator is supported. Startup synchronizes the configured built-in User and Admin accounts without overwriting an existing email or password reset.

The configured database was cleaned at the user's request. It now retains only:

| Username | Display name | Email |
|---|---|---|
| User | User | User@bitwords.com |
| user1 | User1 | user1@rushcorp.com |
| Admin | Admin | Not set |

The purge removed 334 other accounts and their account-linked chat/activity data, including one session, three requests, and two jobs. It verified that no remaining user foreign-key references point at deleted accounts. Shared canonical scraped records were retained when they were not exclusively owned by the deleted account, preserving the application's global deduplication model. The exact database cleanup counts and remaining accounts are recorded in [the cleanup verification report](docs/audit/account_cleanup_verification.json). Do not reintroduce retired demo-user profiles as hard-coded frontend accounts; profile and activity views must use authenticated database accounts.

## Administrator activity and exports

Admin Activity provides per-user groups, headed by email when present, and an **admin** group for administrator data. For each non-cancelled request, the administrator can review what the model understood, the conversation and tool trace, job outcome, and the exact frozen rows delivered. CSV exports use the same saved delivery values. Records acquired during a scrape but not delivered for a fulfilled request remain in the database; they are not falsely presented as having been delivered to that user.

Account cleanup removes the deleted users' sessions, messages, requests, actions, delivery snapshots, jobs, and related owned activity. Shared global company or opportunity rows are preserved when they remain referenced by retained users or the shared database.

## Chat and browser state

A user has one active chat at a time. Reload restores the active server-side conversation and pending job state. Clear Chat starts a new session and prevents the old checkpoint or running scraper from continuing as that user's conversation. Chat retries use client message IDs and scrape approvals use idempotency keys to prevent duplicate work.

NYSCR may require a human to sign in or solve a challenge in its browser. Credentials are read from configuration. A verified local Chrome session may be attached for development; the worker must not close the user's attached browser. Docker uses its configured remote Selenium browser.

## Frontend and API

The React interface includes login, AI chat, result tables with row-level detail viewing, user data and job pages, and administrator pages for users, activity, jobs, and knowledge-base status. The chat's Action control is the approval point for scraping. There is no user-facing cancellation report after Clear Chat.

The FastAPI backend provides health/readiness, authentication, chat/session, record/dataset, source, job, admin, and RAG proxy endpoints. Every endpoint enforces authentication and owner/admin access. Health and readiness checks distinguish an unavailable API from downstream AI, database, RAG, or worker status.

## Current limits

- Production RAG document ingestion and embedding are not deployed; the chat and admin surfaces report actual RAG availability.
- Docker was unavailable on the workstation during implementation review, so a local Docker build and end-to-end Docker run were not verified. CI and manifest checks are separate evidence.
- External websites can change, require human verification, or have fewer qualifying records than requested. A successful sample extraction does not guarantee a future quantity.
- Email delivery, calling, and campaign execution are not working integrations in this scraper/data workflow, even where legacy UI components remain in the frontend.

## Configuration and operation

Configuration is loaded from the process environment and configured environment files. Database URLs, token signing secret, AI provider keys, NYSCR credentials, browser mode, timeouts, and service addresses must not be committed to source control or printed in reports. Local setup applies migrations, initializes checkpoint tables, and seeds reference data. The local development API supervises its worker; production/Docker worker topology is configured separately.

Browser-source behavior depends on the source website, network, credentials, and any human verification challenge. Live source coverage and available result counts can change over time.

## Known incidents and their resolution

- A request for roofing contractors with both contacts and any location was allowed through database interpretation, then failed inside JWiz because the source needs a city or state. Source requirements are now declared and validated before approval and queueing. The database search can still use any location.
- A Bonfire job was described in chat as queued while it was waiting behind earlier work; the later audit records job `f7a0739d-2f29-4db1-aee4-3c7c9c0eb058` completing as Partial. A separate reported Bonfire job, `118c4f1a-4811-492e-aa97-36f0b74062f5`, was Partial with 17 recovered records. Current job statuses and source errors are now provided as authoritative context for later replies. The [source preflight/runtime report](docs/audit/source_preflight_runtime.json) also records the JWiz missing-location job as Failed with zero recovered records and confirms invalid JWiz proposals are rejected before queueing.
- Repeated ERR_CONNECTION_REFUSED messages occurred when the local API process was stopped or restarting. A 503 from the chat endpoint indicates that the API was reachable but the chat request failed in the backend; it is distinct from a refused connection. Health/readiness and logs are the source of truth for current runtime availability.
- Scraper jobs that wait without returning records are stopped after five minutes of inactivity, and an active user can choose a fresh approved attempt or a compatible alternative.

## Verification recorded during implementation

The implementation review recorded 318 passing backend and RAG tests, successful frontend lint and production build, and passing Python correctness and whitespace checks. The configured API health and readiness endpoints returned 200, and its local supervised worker was available. Recorded live source checks extracted and persisted sample company and opportunity records across JWiz, Bonfire, DASNY, and NYSCR; they are summarized in [implementation status](IMPLEMENTATION_STATUS.md#live-source-results). A live JWiz cancellation check recovered and persisted records before Clear Chat stopped the owned scraper process; the cancellation was logged without producing a user/admin report. The account-cleanup report records the exact number of removed accounts and linked activity. These checks establish behavior at review time; they do not promise that an external source will return a particular quantity in future.
