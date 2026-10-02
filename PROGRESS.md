# PROGRESS

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1 | DONE | 081a6f7 | Removed hard-coded credential fallbacks from nyscr.py. |
| P0.2 | DONE | 081a6f7 | Moved 4 codemod scripts to _unused_scripts/. |
| P0.3 | DONE | 081a6f7 | Consolidated duplicate packages, migrations, alembic.ini. |
| P0.4 | DONE | 081a6f7 | Rewrote seed.py and check.py with SQLAlchemy. Fixed setup.py path. |
| P0.5 | DONE | 081a6f7 | Removed hard-coded paths and runtime pip install from 3 scrapers. |
| P14.0 | DONE | c6724e9 | All 8 root causes (RC1-RC8) confirmed from code analysis. |
| P14.1 | DONE | c6724e9 | chat_models.py: Gemini + DeepSeek fallback. /health/llm endpoint. 7/7 tests. |
| P1.1 | DONE | 273ef29 | Database/session.py with get_db(). Fixed transaction() finally. Session cleanup middleware. |
| P1.2 | DONE | 273ef29 | Agent error handler rolls back session. |
| P1.3 | DONE | 273ef29 | Executor worker finally cleans up thread-local session. |
| P1.4 | DONE | 273ef29 | selectinload for Lead→Org→emails/phones, Lead→Contact→emails/phones. |
| P1.5 | DONE | 273ef29 | BaseRepository.list() raises ValueError on unknown filter keys. |
| P1.6 | DONE | 273ef29 | Replaced test_db_import.py with pytest test_db_connection.py. |
| P2.1 | DONE | — | Added columns: leads(source_code, external_id, fingerprint, first_seen_at, last_seen_at), queries(decision, job_id, records_returned, records_new, records_updated, served_at), jobs(params_hash, idempotency_key, heartbeat_at, cancel_requested), agent_messages(role, tool_trace). Org/email/phone already had normalized_* columns. |
| P2.2 | DONE | — | Created query_results(query_id, lead_id, rank) and lead_sources(id, lead_id, source_code, external_id, source_url, seen_at) tables. |
| P2.3 | PARTIAL | — | UNIQUE(source_code, external_id) on lead_sources done. Remaining unique indexes deferred to P2.4 data migration (need backfill first). |
| P2.4 | DONE | — | Migration b226615a3c81: upgrade/downgrade/upgrade clean. Fixed migrations/env.py sys.path. |
| P2.5 | DONE | — | Timestamps already use timezone=True. alembic.ini reads DATABASE_URL from env. |

## Open Questions
- [ ] (P2.3) Remaining unique indexes (leads.fingerprint, orgs.normalized_name, etc.) need P3.1 normalize.py + backfill first.

## Deviations from plan
- (P0.2) Scripts moved to _unused_scripts/ instead of deleted, per user request.
- (S1/S2) No password rotation or git history rewrite — user confirmed.
- (S6) Confirmed: Gemini primary + DeepSeek fallback, keep existing model IDs, no LangSmith.
- (P1.6) test_db_import.py moved to _unused_scripts/.
- (P2.1) Organization already had normalized_name and domain; Email had normalized_email; Phone had normalized_phone — false positive, columns existed.
- (P2.3) Unique indexes for leads.fingerprint etc. deferred — need normalize.py + data backfill (P3.1/P3.2) before indexes can be created.
