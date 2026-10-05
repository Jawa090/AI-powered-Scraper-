"""
tests/test_api_admin.py
───────────────────────
Unit tests for admin API routes.
"""

import pytest
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app import app
from services.auth import require_admin
from Database.models.user import User

client = TestClient(app)

def override_require_admin():
    return User(id="admin_user", role="admin")

def override_require_admin_forbidden():
    raise HTTPException(status_code=403, detail="Not enough permissions")

def override_require_admin_unauth():
    raise HTTPException(status_code=401, detail="Not authenticated")

class TestAdminAPI:
    def teardown_method(self):
        app.dependency_overrides.clear()
        
    @patch("routes.admin._db")
    def test_admin_access_allowed(self, mock_db):
        app.dependency_overrides[require_admin] = override_require_admin
        
        mock_db.session.execute.return_value.scalar_one.return_value = 0
        mock_db.session.scalars.return_value.all.return_value = []
        
        response = client.get("/api/admin/requests")
        assert response.status_code == 200
        
    def test_admin_access_forbidden_for_normal_user(self):
        app.dependency_overrides[require_admin] = override_require_admin_forbidden
        response = client.get("/api/admin/requests")
        assert response.status_code == 403

    def test_admin_access_unauthorized_for_anonymous(self):
        app.dependency_overrides[require_admin] = override_require_admin_unauth
        response = client.get("/api/admin/requests")
        assert response.status_code == 401
