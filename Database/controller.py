import threading
import os
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session

# Import all repositories
from Database.repositories.agent_sessions import AgentSessionRepository
from Database.repositories.contacts import ContactRepository
from Database.repositories.datasets import DatasetRepository, DatasetRecordRepository
from Database.repositories.emails import EmailRepository
from Database.repositories.jobs import JobRepository
from Database.repositories.leads import LeadRepository
from Database.repositories.locations import LocationRepository
from Database.repositories.organizations import OrganizationRepository
from Database.repositories.phones import PhoneRepository
from Database.repositories.queries import QueryRepository
from Database.repositories.requirements import RequirementRepository
from Database.repositories.scrape_runs import ScrapeRunRepository
from Database.repositories.sources import SourceRepository

logger = logging.getLogger(__name__)

class DBError(Exception):
    pass

class DBController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBController, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.engine = None
        self.SessionFactory = None
        self._pid = os.getpid()

    def connect(self):
        if self.engine is None or self._pid != os.getpid():
            from dotenv import load_dotenv
            load_dotenv()
            
            db_url = os.getenv("DATABASE_URL", "")
            if not db_url:
                logger.warning("DATABASE_URL environment variable is not set")
                
            # Convert async URLs to sync if needed for SQLAlchemy
            if "postgresql+asyncpg" in db_url:
                db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg")
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://")
                
            self.engine = create_engine(db_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
            self.SessionFactory = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=self.engine))
            self._pid = os.getpid()

    @property
    def session(self) -> Session:
        """Return the thread-local session from the scoped_session registry."""
        self.connect()
        return self.SessionFactory()

    # ------------------------------------------------------------------
    # Repository properties — each returns a repo bound to the current
    # thread's session so background worker threads are safe.
    # ------------------------------------------------------------------
    @property
    def agent_sessions(self):
        return AgentSessionRepository(self.session)

    @property
    def contacts(self):
        return ContactRepository(self.session)

    @property
    def datasets(self):
        return DatasetRepository(self.session)

    @property
    def dataset_records(self):
        return DatasetRecordRepository(self.session)

    @property
    def emails(self):
        return EmailRepository(self.session)

    @property
    def jobs(self):
        return JobRepository(self.session)

    @property
    def leads(self):
        return LeadRepository(self.session)

    @property
    def locations(self):
        return LocationRepository(self.session)

    @property
    def organizations(self):
        return OrganizationRepository(self.session)

    @property
    def phones(self):
        return PhoneRepository(self.session)

    @property
    def queries(self):
        return QueryRepository(self.session)

    @property
    def requirements(self):
        return RequirementRepository(self.session)

    @property
    def scrape_runs(self):
        return ScrapeRunRepository(self.session)

    @property
    def sources(self):
        return SourceRepository(self.session)

    def close(self):
        if self.SessionFactory:
            self.SessionFactory.remove()
        if self.engine:
            self.engine.dispose()

    @contextmanager
    def transaction(self):
        self.connect()
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            self.SessionFactory.remove()

db = DBController()

import atexit
atexit.register(db.close)

