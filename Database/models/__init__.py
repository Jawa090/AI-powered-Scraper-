"""
Database Models Registry
Exports all 19 core platform entities registered with SQLAlchemy Base.
"""

from Database.models.department import Department
from Database.models.user import User
from Database.models.agent import Agent
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from Database.models.requirement import Requirement
from Database.models.query import Query
from Database.models.source import Source
from Database.models.scrape_run import ScrapeRun
from Database.models.job import Job
from Database.models.dataset import Dataset, DatasetRecord
from Database.models.organization import Organization
from Database.models.contact import Contact
from Database.models.email import Email
from Database.models.phone import Phone
from Database.models.location import Location
from Database.models.lead import Lead
from Database.models.action import AgentAction
from Database.models.query_result import QueryResult
from Database.models.lead_source import LeadSource
from Database.models.session_event import SessionEvent

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
    "QueryResult",
    "LeadSource",
    "SessionEvent",
]
