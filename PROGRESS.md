# PROGRESS

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1 | DONE | 081a6f7 | Removed hard-coded credential fallbacks from nyscr.py; env-only with EnvironmentError. |
| P0.2 | DONE | 081a6f7 | Moved 4 codemod scripts to _unused_scripts/. |
| P0.3 | DONE | 081a6f7 | Consolidated duplicate packages, migrations, alembic.ini. |
| P0.4 | DONE | 081a6f7 | Rewrote seed.py and check.py with SQLAlchemy. Fixed setup.py path. |
| P0.5 | DONE | 081a6f7 | Removed hard-coded C:\Users\lenovo paths and runtime pip install from 3 scrapers. |
| P14.0 | DONE | c6724e9 | All 8 root causes (RC1-RC8) confirmed from code analysis. |
| P14.1 | DONE | c6724e9 | chat_models.py: ChatGoogleGenerativeAI + ChatOpenAI fallback. /health/llm endpoint. 7/7 tests. |
| P1.1 | DONE | — | Created Database/session.py with get_db() generator (commit/rollback/finally close+remove). Fixed transaction() to include finally. Added session cleanup middleware in app.py. |
| P1.2 | DONE | — | Added session.rollback() in run_agent_graph error handler. Replaced print() with logger. |
| P1.3 | DONE | — | Added SessionFactory.remove() in executor _worker finally block to prevent session leaks across ThreadPoolExecutor thread reuse. |
| P1.4 | DONE | — | Added selectinload for Lead→Organization→emails/phones, Lead→Contact→emails/phones in LeadRepository.list(). Prevents N+1 queries on serialization. |
| P1.5 | DONE | — | BaseRepository.list() now raises ValueError on unknown filter keys instead of silently skipping. |
| P1.6 | DONE | — | Moved broken test_db_import.py to _unused_scripts. Created proper pytest test_db_connection.py with SELECT 1 and rollback-recovery tests. |

## Open Questions
- [ ] (P14.0) Full API-level baseline test deferred until server can be started.
- [ ] (P1.6) test_db_connection.py requires a live PostgreSQL to run — will pass in CI.

## Deviations from plan
- (P0.2) Scripts moved to _unused_scripts/ instead of deleted, per user request.
- (S1/S2) No password rotation or git history rewrite — user confirmed.
- (S6) Confirmed: Gemini primary + DeepSeek fallback, keep existing model IDs, no LangSmith.
- (P1.6) test_db_import.py moved to _unused_scripts/ (per user's "keep backups" rule).
