"""
agents/graph/checkpointer.py
────────────────────────────
LangGraph PostgreSQL checkpointer setup for persistent memory.
"""

import os
from contextlib import contextmanager
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

# We need a synchronous psycopg pool pointing to the checkpointer DB.
# Convert sqlalchemy URL to postgresql:// if needed.
_raw_url = os.environ.get("CHECKPOINT_DB_URL", os.environ.get("DATABASE_URL", ""))
if _raw_url.startswith("postgresql+psycopg://"):
    _raw_url = _raw_url.replace("postgresql+psycopg://", "postgresql://")
elif _raw_url.startswith("postgresql+psycopg2://"):
    _raw_url = _raw_url.replace("postgresql+psycopg2://", "postgresql://")

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
