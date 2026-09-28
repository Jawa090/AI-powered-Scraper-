import os
import urllib.parse
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Load environment variables from Backend/.env
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


def _normalize_database_url(url: str) -> str:
    """
    Normalizes a database URL to ensure that any special characters in the
    credentials (e.g. '@' in passwords) are properly percent-encoded for SQLAlchemy.
    """
    if not url or "://" not in url:
        return url

    scheme, rest = url.split("://", 1)

    if "?" in rest:
        base_part, query = rest.split("?", 1)
        query = "?" + query
    else:
        base_part, query = rest, ""

    if "@" in base_part:
        userinfo, host_db = base_part.rsplit("@", 1)
        if ":" in userinfo:
            user, password = userinfo.split(":", 1)
            user = urllib.parse.quote_plus(urllib.parse.unquote_plus(user))
            password = urllib.parse.quote_plus(urllib.parse.unquote_plus(password))
            userinfo = f"{user}:{password}"
        return f"{scheme}://{userinfo}@{host_db}{query}"

    return url


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the environment or Backend/.env file.")

# SQLAlchemy 2.x PostgreSQL Engine configuration
engine: Engine = create_engine(
    _normalize_database_url(DATABASE_URL),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
)

# Thread-safe database session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    Reusable database session dependency for FastAPI and backend services.
    Yields an active session and ensures it is cleanly closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
