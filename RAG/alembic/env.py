import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool, text

# Add parent directory to sys.path so RAG package can be imported
rag_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(rag_dir.parent))

from RAG.settings import get_rag_settings
from RAG.models import RAGBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = RAGBase.metadata


def get_url():
    url = os.environ.get("RAG_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        try:
            settings = get_rag_settings()
            url = settings.RAG_DATABASE_URL
        except Exception:
            url = "postgresql+psycopg://postgres:1234@localhost:5432/dataops"
    return url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_rag",
        version_table_schema="rag",
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # Ensure schema rag exists before version table is created
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS rag;"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_rag",
            version_table_schema="rag",
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
