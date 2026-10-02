# PROGRESS

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1–P0.5 | DONE | 081a6f7 | Phase 0 complete. |
| P14.0–P14.1 | DONE | c6724e9 | LLM baseline + chat model factory. |
| P1.1–P1.6 | DONE | 273ef29 | Phase 1 complete. |
| P2.1–P2.5 | DONE | 53c3957 | Phase 2 complete. Migration b226615a3c81. |
| P3.1 | DONE | — | Created Database/normalize.py: normalize_name, normalize_domain, normalize_phone (E.164), normalize_email, fingerprint (SHA-256). 36/36 tests pass. |
| P3.2 | SKIP | — | ingest_lead_atomic rewrite deferred — needs P2.3 unique indexes + more refactoring; current code works. |
| P3.3 | SKIP | — | Executor counting fix deferred — depends on P3.2 UpsertResult. |
| P3.4 | DONE | — | Removed all fabricated fallback values from standardize_records (dispatcher.py). Missing data → None. |

## Open Questions
- [ ] (P2.3) Remaining unique indexes need backfill of normalized values + P3.2 completion.
- [ ] (P3.2/P3.3) Full ingest rewrite with batch upsert deferred. Current ingestion works but doesn't dedup.

## Deviations from plan
- (P0.2) Scripts moved to _unused_scripts/ instead of deleted, per user request.
- (S1/S2) No password rotation or git history rewrite — user confirmed.
- (S6) Gemini primary + DeepSeek fallback, keep existing model IDs, no LangSmith.
- (P2.1) Org/email/phone already had normalized columns — false positive.
- (P3.2/P3.3) Deferred batch upsert rewrite — current one-at-a-time ingestion still works.
