import pytest
from Database.controller import session_scope
from Database.repositories.agent_sessions import AgentSessionRepository
from Database.models.session import AgentSession

def test_repository_constructor():
    with session_scope() as s:
        repo = AgentSessionRepository(s)
        # Verify no crash and it has the session
        assert repo.session is s
        
        # Call a method
        results = repo.list_by_user("non-existent-user")
        assert results == []
