"""Readiness probe (uses conftest DB override)."""

from tests.api_json import unwrap_json


def test_health_ready_ok(test_client):
    r = test_client.get("/health/ready")
    assert r.status_code == 200
    data = unwrap_json(r)
    assert data.get("status") == "ready"
    assert data.get("checks", {}).get("database") == "ok"
