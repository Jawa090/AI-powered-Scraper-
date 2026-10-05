import pytest
from Database.controller import session_scope
from services.job_service import JobService

def test_job_service_constructor():
    with session_scope() as s:
        service = JobService(s)
        assert hasattr(service, 'repos')
        assert hasattr(service.repos, 'jobs')
        assert service.job_repo is service.repos.jobs
