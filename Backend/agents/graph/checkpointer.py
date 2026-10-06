"""
agents/graph/checkpointer.py
────────────────────────────
LangGraph PostgreSQL checkpointer setup for persistent agent state.
Complies with Phase P11.2 and Experiment E6.
"""

from __future__ import annotations

import logging
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from settings import settings

logger = logging.getLogger(__name__)

_raw_url = settings.CHECKPOINT_DB_URL

# Connection pool configured with dict_row and autocommit per P11.2 & E6
pool = ConnectionPool(
    conninfo=_raw_url,
    max_size=10,
    open=True,
    kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
)

# Export a persistent saver instance
checkpointer = PostgresSaver(pool)


def setup_checkpointer() -> None:
    """Initialize checkpoint tables in PostgreSQL. Idempotent."""
    try:
        checkpointer.setup()
        logger.info("LangGraph PostgresSaver checkpointer initialized successfully.")
    except Exception as e:
        logger.error("Failed to setup PostgresSaver checkpointer: %s", e, exc_info=True)
        raise


def close_checkpointer() -> None:
    """Close the underlying connection pool."""
    try:
        if not pool.closed:
            pool.close()
    except Exception:
        pass


import atexit
atexit.register(close_checkpointer)
