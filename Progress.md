# Remediation Progress — v8

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1 | IN_PROGRESS | — | Snapshot baseline saved to docs/baseline/, old progress archived |
| P0.2 | PENDING | — | API probe & experiments E1-E12 |
| P0.3 | PENDING | — | pgvector extension check |
| P0.4 | PENDING | — | Test infrastructure |
| P0.5 | PENDING | — | S1 checkpoint: NYSCR password rotation acknowledged |

## Checkpoints & STOP Flags
- [x] **S1:** NYSCR password rotation acknowledged by human. (Confirmed: password already changed).
- [ ] **S9:** Vector extension availability check.

## Deviations from Plan
- None so far.

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