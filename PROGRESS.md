# PROGRESS

## Status
| Task | Status | Commit | Notes |
|---|---|---|---|
| P0.1 | DONE | — | Removed hard-coded credential fallbacks from nyscr.py; now reads NYSCR_USERNAME/NYSCR_PASSWORD from env only; raises EnvironmentError if missing. Both credential pairs added to .env files. Added keys to .env.example. |
| P0.2 | DONE | — | Moved comment_db.py, generate_db.py, rewrite_repos.py, rewrite_services.py to _unused_scripts/. No live imports found. DB_controller.py was never generated. comment_db.py damage found in Backend/database/ (all commented out) — addressed in P0.3. |
| P0.3 | DONE | — | Moved duplicate Backend/database/ package to _unused_scripts/ (all code was commented out by comment_db.py or was a stale copy of Database/models/). Removed duplicate Database/migrations/ and Database/alembic.ini (same revision bb5b5d152b0e as Backend/migrations/). Removed empty Backend/repositories/. Single alembic.ini remains in Backend/. |
| P0.4 | DONE | — | Rewrote seed.py to use SQLAlchemy text() + ON CONFLICT DO NOTHING (was using non-existent db._fetch_one/_execute). Rewrote check.py similarly. Fixed setup.py alembic.ini path to point to Backend/alembic.ini after removing Database/ copy. |
| P0.5 | DONE | — | Removed hard-coded C:\Users\lenovo paths and runtime pip install from nyscr.py, dasny.py, bonfire.py. Dependencies must be in requirements.txt. |

## Open Questions
- [ ] (S2) Git history still contains old NYSCR credentials — user confirmed no history rewrite needed.

## Deviations from plan
- (P0.2) Scripts moved to _unused_scripts/ instead of deleted, per user request.
- (P0.3) Backend/database/ package moved to _unused_scripts/ instead of fixed in place — it was entirely commented out / stale copies. The canonical package Database/ (capital D) is untouched.
- (S1/S2) User confirmed: no password rotation confirmation needed, no git history rewrite needed. Just ensure new code has no hard-coded credentials.
