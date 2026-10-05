"""
agents/graph/checkpointer.py
────────────────────────────
LangGraph PostgreSQL checkpointer setup for persistent memory.
"""

import os
from contextlib import contextmanager
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from settings import settings

_raw_url = settings.CHECKPOINT_DB_URL

# Default kwargs per P14.3
pool = ConnectionPool(
    conninfo=_raw_url,
    max_size=10,
    kwargs={"autocommit": True, "prepare_threshold": 0}
)

# Optional: ensure tables exist on startup
def setup_checkpointer():
    with pool.connection() as conn:
        PostgresSaver(conn).setup()

# Export a persistent saver instance
checkpointer = PostgresSaver(pool)
