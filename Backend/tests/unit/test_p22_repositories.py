import pytest
from Database.controller import session_scope, Repositories

def test_repositories_registry():
    with session_scope() as s:
        repos = Repositories(s)
        assert hasattr(repos, 'agent_sessions')
        assert hasattr(repos, 'contacts')
        assert hasattr(repos, 'datasets')
        assert hasattr(repos, 'dataset_records')
        assert hasattr(repos, 'emails')
        assert hasattr(repos, 'jobs')
        assert hasattr(repos, 'leads')
        assert hasattr(repos, 'locations')
        assert hasattr(repos, 'organizations')
        assert hasattr(repos, 'phones')
        assert hasattr(repos, 'queries')
        assert hasattr(repos, 'requirements')
        assert hasattr(repos, 'scrape_runs')
        assert hasattr(repos, 'sources')
        
        assert repos.agent_sessions.session is s
