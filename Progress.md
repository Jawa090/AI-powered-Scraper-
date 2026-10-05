# Remediation Progress — v8

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1 | DONE | f7ccfda | Snapshot baseline saved to docs/baseline/, old progress archived |
| P0.2 | DONE | e294cd9 | API probe & experiments E1-E12 documented in docs/probe.md, scripts/probe_apis.py verified |
| P0.3 | BLOCKED (S9) | — | STOP checkpoint S9: vector extension is missing from pg_available_extensions in local PostgreSQL 18 |
| P0.4 | PENDING | — | Test infrastructure (depends on S9 / Postgres resolution) |
| P0.5 | PENDING | — | S1 checkpoint: NYSCR password rotation acknowledged by human |

## Checkpoints & STOP Flags
- [x] **S1:** NYSCR password rotation acknowledged by human. (Confirmed: password has been changed).
- [!] **S9:** **BLOCKED at STOP checkpoint S9.** `SELECT name, installed_version FROM pg_available_extensions WHERE name='vector'` returned `[]` (0 rows) on local PostgreSQL 18.6 (x86_64-windows). Furthermore, Docker daemon is not active on this Windows host to launch `PostgresContainer("pgvector/pgvector:pg15")`.

## Deviations from Plan
- **E1 (LangGraph ToolNode update):** Requires `tool_call_id: Annotated[str, InjectedToolCallId]` and a matching `ToolMessage` in `Command.update['messages']` due to strict LangGraph 1.2+ validation.
- **E10 (Gemini Model ID):** `gemini-2.0-flash` is deprecated by the upstream Google API endpoint (`models/gemini-2.0-flash is no longer available`); updated verification to `gemini-2.5-flash` / `gemini-3.8-flash`.

## False Positives
- None so far.

## Task Details

### P0.1 Baseline & Snapshot
- Generated baseline outputs in UTF-8 format in `docs/baseline/`:
  - `pytest.txt`: 48 passed, 1 warning (11.30s)
  - `alembic.txt`: heads `b226615a3c81`, current `b226615a3c81`
  - `pip_freeze.txt`: all installed package versions recorded
  - `git_log.txt`: 30 recent commits recorded
  - `frontend_build.txt`: `tsc --noEmit && vite build` built successfully in 19.61s
- Old `PROGRESS.md` archived to `docs/history/PROGRESS.md`.
- Committed in `f7ccfda`.

### P0.2 API Probe & Architecture Experiments
- Created `scripts/probe_apis.py` validating 16 packages and all required imports. Exits with code 0.
- Installed `pgvector==0.5.0` Python client package.
- Performed all 12 experiments E1–E12 (InMemorySaver & live API tests) and documented working code in `docs/probe.md`:
  - **E1:** Tool returning `Command(update=...)` requires `ToolMessage` with `InjectedToolCallId`.
  - **E2:** `state.interrupts` is the canonical property exposing active interrupts.
  - **E3:** `graph.invoke(None, config)` successfully re-runs failed node with earlier state intact.
  - **E4:** On `Command(resume=...)`, node containing `interrupt()` re-runs from its first line.
  - **E5:** `thinking_budget` and `thinking_config` are the thinking parameters for `ChatGoogleGenerativeAI`.
  - **E6:** `PostgresSaver(pool)` with `dict_row` verified against local PostgreSQL; `setup()` is idempotent.
  - **E7:** Invoking with new input starts fresh from START, dropping pending failed task.
  - **E8:** `graph.update_state` with `ToolMessage` successfully repairs dangling tool calls.
  - **E9:** Confirmed `issubclass(jwt.InvalidSignatureError, jwt.DecodeError) == True`.
  - **E10:** Confirmed Gemini accepts history containing tool calls, tool results, and `[JOB EVENT]` messages.
  - **E11:** Confirmed `Command(resume=..., update={...})` at `invoke` level directly applies state updates.
  - **E12:** Confirmed `ToolNode` raises tool error on unregistered tools; `propose_scrape` must not route to `ToolNode`.
- Committed in `e294cd9`.

### P0.3 pgvector Verification
- Ran verification query against local PostgreSQL database:
  ```sql
  SELECT name, default_version, installed_version
  FROM pg_available_extensions
  WHERE name = 'vector';
  ```
- **Evidence:** Result returned `[]` (0 rows). The `vector` extension is not installed in the Windows PostgreSQL 18 installation (`C:\Program Files\PostgreSQL\18\share\extension`).
- Checked Docker status: Docker daemon is not running on the Windows host (`//./pipe/docker_engine` not found), so `PostgresContainer("pgvector/pgvector:pg15")` cannot be spun up automatically.
- Hit **STOP Checkpoint S9**. Per §5.1 / §5.3, execution halts here without workaround.