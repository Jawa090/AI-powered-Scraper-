# Unused Scripts

These scripts were moved here during Phase 0 cleanup (P0.2). They are **harmful
code-rewriting tools** that should never be run against the codebase:

- `comment_db.py` — comments out SQLAlchemy lines, leaving orphaned indented blocks
- `generate_db.py` — rewrites repository methods incorrectly (set params, broken queries)
- `rewrite_repos.py` — deletes any line containing `Session`
- `rewrite_services.py` — rewrites service files with hard-coded paths

All contain hard-coded personal filesystem paths and destructive transforms.
Kept here for reference only.
