"""
repositories/__init__.py
─────────────────────────
Clean public API for the repository layer.

Import pattern::

    from repositories import OrganizationRepository, LeadRepository

All repositories accept a SQLAlchemy Session as their sole constructor argument.
Transactions are managed by the caller (Service layer).
"""

from Database.repositories.base import BaseRepository
from Database.repositories.organizations import OrganizationRepository
from Database.repositories.contacts import ContactRepository
from Database.repositories.emails import EmailRepository
from Database.repositories.phones import PhoneRepository
from Database.repositories.locations import LocationRepository
from Database.repositories.leads import LeadRepository
from Database.repositories.datasets import DatasetRepository, DatasetRecordRepository
from Database.repositories.jobs import JobRepository
from Database.repositories.sources import SourceRepository
from Database.repositories.scrape_runs import ScrapeRunRepository
from Database.repositories.agent_sessions import AgentRepository, AgentSessionRepository, AgentMessageRepository
from Database.repositories.requirements import RequirementRepository
from Database.repositories.queries import QueryRepository

__all__ = [
    "BaseRepository",
    "OrganizationRepository",
    "ContactRepository",
    "EmailRepository",
    "PhoneRepository",
    "LocationRepository",
    "LeadRepository",
    "DatasetRepository",
    "DatasetRecordRepository",
    "JobRepository",
    "SourceRepository",
    "ScrapeRunRepository",
    "AgentRepository",
    "AgentSessionRepository",
    "AgentMessageRepository",
    "RequirementRepository",
    "QueryRepository",
]
