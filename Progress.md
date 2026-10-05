# Remediation Progress — v8

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1 | DONE | f7ccfda | Snapshot baseline saved to docs/baseline/, old progress archived |
| P0.2 | DONE | — | API probe & experiments E1-E12 documented in docs/probe.md, scripts/probe_apis.py verified |
| P0.3 | IN_PROGRESS | — | pgvector extension check |
| P0.4 | PENDING | — | Test infrastructure |
| P0.5 | PENDING | — | S1 checkpoint: NYSCR password rotation acknowledged |

## Checkpoints & STOP Flags
- [x] **S1:** NYSCR password rotation acknowledged by human. (Confirmed: password already changed).
- [ ] **S9:** Vector extension availability check.

## Deviations from Plan
- E1 requires `tool_call_id: Annotated[str, InjectedToolCallId]` and a matching `ToolMessage` in `Command.update['messages']` due to strict LangGraph 1.2+ validation.
- Gemini model ID: `gemini-2.0-flash` deprecated by upstream API, updated testing to `gemini-2.5-flash` / `gemini-3.8-flash`.

## False Positives
- None so far.

## Task Details
### P0.1 Baseline & Snapshot
- Baseline outputs captured in `docs/baseline/`:
  - `pytest.txt`: 48 passed, 1 warning (11.30s)
  - `alembic.txt`: heads `b226615a3c81`, current `b226615a3c81`
  - `pip_freeze.txt`: all installed package versions recorded
  - `git_log.txt`: 30 recent commits recorded
  - `frontend_build.txt`: `tsc --noEmit && vite build` built successfully in 19.61s
- Old `PROGRESS.md` archived to `docs/history/PROGRESS.md`.

### P0.2 API Probe & Architecture Experiments
- Created `scripts/probe_apis.py` validating 16 packages and all required imports.
- Performed all 12 experiments E1–E12 (InMemorySaver & live API tests) and documented working code in `docs/probe.md`:
  - E1: Tool returning `Command(update=...)` requires `ToolMessage` with `InjectedToolCallId`.
  - E2: `state.interrupts` is the canonical property exposing active interrupts.
  - E3: `graph.invoke(None, config)` successfully re-runs failed node with earlier state intact.
  - E4: On `Command(resume=...)`, node containing `interrupt()` re-runs from its first line.
  - E5: `thinking_budget` and `thinking_config` are the thinking parameters for `ChatGoogleGenerativeAI`.
  - E6: `PostgresSaver(pool)` with `dict_row` verified against local PostgreSQL; `setup()` is idempotent.
  - E7: Invoking with new input starts fresh from START, dropping pending failed task.
  - E8: `graph.update_state` with `ToolMessage` successfully repairs dangling tool calls.
  - E9: Confirmed `issubclass(jwt.InvalidSignatureError, jwt.DecodeError) == True`.
  - E10: Confirmed Gemini accepts history containing tool calls, tool results, and `[JOB EVENT]` messages.
  - E11: Confirmed `Command(resume=..., update={...})` at `invoke` level directly applies state updates.
  - E12: Confirmed `ToolNode` raises tool error on unregistered tools; `propose_scrape` must not route to `ToolNode`.