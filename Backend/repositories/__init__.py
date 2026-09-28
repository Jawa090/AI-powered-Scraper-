"""
repositories/__init__.py
─────────────────────────
Clean public API for the repository layer.

Import pattern::

    from repositories import OrganizationRepository, LeadRepository

All repositories accept a SQLAlchemy Session as their sole constructor argument.
Transactions are managed by the caller (Service layer).
"""

from repositories.base import BaseRepository
from repositories.organizations import OrganizationRepository
from repositories.contacts import ContactRepository
from repositories.emails import EmailRepository
from repositories.phones import PhoneRepository
from repositories.locations import LocationRepository
from repositories.leads import LeadRepository
from repositories.datasets import DatasetRepository, DatasetRecordRepository
from repositories.jobs import JobRepository
from repositories.sources import SourceRepository
from repositories.scrape_runs import ScrapeRunRepository
from repositories.agent_sessions import AgentRepository, AgentSessionRepository, AgentMessageRepository
from repositories.requirements import RequirementRepository
from repositories.queries import QueryRepository

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
