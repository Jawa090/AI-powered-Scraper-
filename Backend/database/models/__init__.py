"""
Database Models Registry
Exports all 19 core platform entities registered with SQLAlchemy Base.
"""

from database.models.department import Department
from database.models.user import User
from database.models.agent import Agent
from database.models.session import AgentSession
from database.models.message import AgentMessage
from database.models.requirement import Requirement
from database.models.query import Query
from database.models.source import Source
from database.models.scrape_run import ScrapeRun
from database.models.job import Job
from database.models.dataset import Dataset, DatasetRecord
from database.models.organization import Organization
from database.models.contact import Contact
from database.models.email import Email
from database.models.phone import Phone
from database.models.location import Location
from database.models.lead import Lead
from database.models.action import AgentAction

__all__ = [
    "Department",
    "User",
    "Agent",
    "AgentSession",
    "AgentMessage",
    "Requirement",
    "Query",
    "Source",
    "ScrapeRun",
    "Job",
    "Dataset",
    "DatasetRecord",
    "Organization",
    "Contact",
    "Email",
    "Phone",
    "Location",
    "Lead",
    "AgentAction",
]
