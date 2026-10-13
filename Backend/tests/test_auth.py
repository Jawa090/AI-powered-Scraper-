import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app import app
from Database.controller import session_scope
from Database.models.user import User

client = TestClient(app)

def test_login_success():
    # Admin
    res = client.post("/api/auth/login", json={"username": "Admin", "password": "Admin"})
    assert res.status_code == 200
    assert "accessToken" in res.json()
    assert res.json()["user"]["role"] == "admin"
    
    # User
    res = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    assert res.status_code == 200
    assert "accessToken" in res.json()
    assert res.json()["user"]["role"] == "user"

def test_login_failures():
    # Wrong password
    res = client.post("/api/auth/login", json={"username": "Admin", "password": "wrong"})
    assert res.status_code == 401
    
    # Forged token (not testing full decode, just passing bad token)
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer fake.token.here"})
    assert res.status_code == 401
    
    # Old raw token
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer usr-env-admin"})
    assert res.status_code == 401

    # Expired token
    import jwt
    import time
    from settings import settings
    expired_token = jwt.encode(
        {"sub": "usr-env-user", "role": "user", "iat": int(time.time()) - 200, "exp": int(time.time()) - 100},
        settings.JWT_SECRET,
        algorithm="HS256"
    )
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401

def test_admin_routes_forbidden_for_users():
    # Get user token
    res = client.post("/api/auth/login", json={"username": "User123", "password": "User123"})
    token = res.json()["accessToken"]
    
    # Try admin route
    res = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403

def test_admin_creates_user():
    # Clean up test user alice if already exists from prior test runs
    with session_scope() as session:
        session.execute(text("DELETE FROM users WHERE lower(username) = 'alice'"))
        session.commit()

    # Get admin token
    res = client.post("/api/auth/login", json={"username": "Admin", "password": "Admin"})
    token = res.json()["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Admin creates alice
    res = client.post("/api/admin/users", json={
        "username": "alice",
        "name": "Alice",
        "email": "alice@example.test",
        "password": "alicepassword"
    }, headers=headers)
    assert res.status_code == 200
    
    # Alice can log in
    res = client.post("/api/auth/login", json={"username": "alice", "password": "alicepassword"})
    assert res.status_code == 200
    assert "accessToken" in res.json()

def test_second_admin_api_fails():
    res = client.post("/api/auth/login", json={"username": "Admin", "password": "Admin"})
    token = res.json()["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}
    
    res = client.post("/api/admin/users", json={
        "username": "admin2",
        "email": "admin2@example.test",
        "password": "admin2password",
        "role": "admin"
    }, headers=headers)
    assert res.status_code == 400
    assert "Only one admin is allowed" in res.json()["detail"]

def test_second_admin_sql_fails():
    with session_scope() as session:
        session.execute(text("DELETE FROM users WHERE lower(username) = 'testadmin2'"))
        session.commit()

    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with session_scope() as session:
            new_user = User(
                id="usr-test-admin2",
                username="testadmin2",
                role="admin",
                auth_source="db",
                status="Active"
            )
            session.add(new_user)
            session.commit()
