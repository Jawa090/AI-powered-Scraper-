"""Integration test verifying /health/ready readiness check against test database."""
import pytest


@pytest.mark.integration
def test_health_ready_endpoint(client):
    """Integration test verifying /health/ready returns 200 with ready status."""
    response = client.get("/health/ready")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data.get("status") == "ready"
    assert data.get("database") == "connected"
