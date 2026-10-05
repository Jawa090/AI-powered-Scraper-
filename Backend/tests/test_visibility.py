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
        sess = AgentSession(id=test_sess_id, user_id=user1_id, department_id="dept-default", agent_id="agent-master")
        session.add(j)
        session.add(sess)
        session.commit()

    # User123 can read their job
    res = client.get(f"/api/jobs/{test_job_id}", headers=headers1)
    assert res.status_code == 200

    # Alice cannot read User123's job
    res = client.get(f"/api/jobs/{test_job_id}", headers=headers2)
    assert res.status_code == 404

    # User123 can chat with their session
    res = client.post("/api/bot/chat", json={"sessionId": test_sess_id, "message": "hello"}, headers=headers1)
    # 503, 500 or 200 is fine, we just care it doesn't give 403
    assert res.status_code in [200, 500, 503] 

    # Alice cannot chat with User123's session
    res = client.post("/api/bot/chat", json={"sessionId": test_sess_id, "message": "hello"}, headers=headers2)
    assert res.status_code == 403
    
    # Admin can read User123's job
    res = client.get(f"/api/jobs/{test_job_id}", headers={"Authorization": f"Bearer {token_admin}"})
    assert res.status_code == 200
