import pytest
from fastapi.testclient import TestClient
from app import app
from Database.controller import session_scope
from Database.models.job import Job
from Database.models.session import AgentSession

client = TestClient(app)

def test_user_cannot_read_others_job_and_session():
    # Login as User123
    res1 = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    token1 = res1.json()["accessToken"]
    user1_id = res1.json()["user"]["id"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    # Create Alice
    res_admin = client.post("/api/auth/login", json={"username": "Admin", "password": "Admin"})
    token_admin = res_admin.json()["accessToken"]
    import uuid
    test_user = f"user_{uuid.uuid4().hex[:8]}"
    client.post("/api/admin/users", json={
        "username": test_user,
        "name": "Test User",
        "email": test_user + "@example.test",
        "password": "testpassword"
    }, headers={"Authorization": f"Bearer {token_admin}"})

    # Login as new user
    res2 = client.post("/api/auth/login", json={"username": test_user, "password": "testpassword"})
    token2 = res2.json()["accessToken"]
    user2_id = res2.json()["user"]["id"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Insert a job and session for User123
    test_job_id = f"job-{uuid.uuid4().hex[:8]}"
    test_sess_id = f"sess-{uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        j = Job(id=test_job_id, name="Test Job", status="Completed", created_by=user1_id, department_id="dept-default")
        sess = AgentSession(id=test_sess_id, user_id=user1_id, department_id="dept-default", agent_id="agent-master", status="archived")
        session.add(j)
        session.add(sess)
        session.commit()

    # User123 can read their job
    res = client.get(f"/api/jobs/{test_job_id}", headers=headers1)
    assert res.status_code == 200

    # Alice cannot read User123's job
    res = client.get(f"/api/jobs/{test_job_id}", headers=headers2)
    assert res.status_code == 404

    # The owner can read archived history, while new writes are rejected
    res = client.post("/api/bot/chat", json={"sessionId": test_sess_id, "message": "hello"}, headers=headers1)
    # Archived conversations preserve history without accepting new writes.
    assert res.status_code == 409
    assert client.get(f"/api/bot/sessions/{test_sess_id}/messages", headers=headers1).status_code == 200

    # Alice cannot chat with User123's session
    res = client.post("/api/bot/chat", json={"sessionId": test_sess_id, "message": "hello"}, headers=headers2)
    assert res.status_code == 403
    
    # Admin can read User123's job
    res = client.get(f"/api/jobs/{test_job_id}", headers={"Authorization": f"Bearer {token_admin}"})
    assert res.status_code == 200
