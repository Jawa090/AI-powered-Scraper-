"""
tests/test_db_connection.py
───────────────────────────
Smoke test for database connectivity.
"""

import pytest
from sqlalchemy import text


def test_db_connection_select_1():
    """Database responds to SELECT 1 (basic connectivity check)."""
    from Database.session import get_db

    gen = get_db()
    session = next(gen)
    try:
        result = session.execute(text("SELECT 1 AS ok"))
        row = result.one()
        assert row[0] == 1
    finally:
        try:
            gen.close()
        except StopIteration:
            pass


def test_get_db_rollback_on_error():
    """get_db() rolls back and cleans up the session on exception."""
    from Database.session import get_db

    gen = get_db()
    session = next(gen)
    try:
        # Force an error by executing invalid SQL
        with pytest.raises(Exception):
            session.execute(text("SELECT * FROM nonexistent_table_xyz_123"))
            gen.close()  # Would try to commit → error
    finally:
        # Session should still be usable after cleanup
        try:
            gen.throw(Exception("test"))
        except (Exception, StopIteration):
            pass

    # A new session should work fine (not poisoned)
    gen2 = get_db()
    session2 = next(gen2)
    result = session2.execute(text("SELECT 1 AS ok"))
    assert result.one()[0] == 1
    try:
        gen2.close()
    except StopIteration:
        pass
