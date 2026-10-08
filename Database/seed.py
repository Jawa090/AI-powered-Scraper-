"""Idempotent reference data seed using the public scraper catalogue."""
try:
    import _paths
except ImportError:
    from Backend import _paths
from Database.controller import session_scope
from Database.models.department import Department
from Database.models.agent import Agent
from services.auth import sync_env_users
from services.sources import sync_sources


def seed():
    with session_scope() as session:
        if not session.get(Department, "dept-default"):
            session.add(Department(id="dept-default", name="Default", code="DEFAULT"))
        session.flush()
        sync_env_users(session)
        if not session.get(Agent, "agent-master"):
            session.add(Agent(id="agent-master", name="Data Agent", code="master", department_id="dept-default"))
        sync_sources(session)


if __name__ == "__main__":
    seed()
