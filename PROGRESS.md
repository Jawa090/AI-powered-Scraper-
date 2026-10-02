# PROGRESS

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1 | DONE | 081a6f7 | Removed hard-coded credential fallbacks from nyscr.py; env-only with EnvironmentError if missing. |
| P0.2 | DONE | 081a6f7 | Moved 4 codemod scripts to _unused_scripts/. No live imports. |
| P0.3 | DONE | 081a6f7 | Consolidated: removed duplicate Backend/database/, Database/migrations/, Database/alembic.ini. |
| P0.4 | DONE | 081a6f7 | Rewrote seed.py and check.py with SQLAlchemy. Fixed setup.py alembic.ini path. |
| P0.5 | DONE | 081a6f7 | Removed hard-coded C:\Users\lenovo paths and runtime pip install from 3 scrapers. |
| P14.0 | DONE | — | Baseline from code analysis. All 8 root causes (RC1-RC8) confirmed from source. |
| P14.1 | DONE | — | Created agents/llm/chat_models.py with ChatGoogleGenerativeAI (Gemini) + ChatOpenAI (DeepSeek) fallback via .with_fallbacks(). Added GET /health/llm endpoint. Added langchain-openai to requirements. 7/7 tests pass. |

## Open Questions
- [ ] (P14.0) Full API-level baseline test deferred until server can be started.

## Deviations from plan
- (P0.2) Scripts moved to _unused_scripts/ instead of deleted, per user request.
- (P0.3) Backend/database/ moved to _unused_scripts/ — entirely commented out / stale.
- (S1/S2) No password rotation or git history rewrite — user confirmed.
- (S6) Confirmed: Gemini primary + DeepSeek fallback, keep existing model IDs, no LangSmith.
- (P14.1) Old LLM client code (factory.py, openai_compatible.py, provider.py) kept for now — still used by legacy greeting node. Will be deleted in P14.12 after full cut-over.
