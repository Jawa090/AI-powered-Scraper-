"""
Database Package
────────────────
Central database access layer for the entire project.
Exposes a single `db` object (DBController singleton) that all other
modules use to interact with PostgreSQL.

Usage from anywhere in the project:
    from Database import db
    rows = db._fetch_all("SELECT * FROM leads")
"""

from Database.controller import db, DBController, DBError, engine, SessionLocal, session_scope, get_db

__all__ = ["db", "DBController", "DBError", "engine", "SessionLocal", "session_scope", "get_db"]
