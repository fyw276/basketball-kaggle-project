"""
Tests for main application
"""

from fastapi.testclient import TestClient
from starlette.responses import Response

from app.main import ApiEnvelopeMiddleware, app
from tests.api_json import unwrap_json

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint returns correct information"""
    response = client.get("/")
    assert response.status_code == 200
    data = unwrap_json(response)
    assert "name" in data
    assert "version" in data
    assert "status" in data
    assert data["status"] == "running"


def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = unwrap_json(response)
    assert data["status"] == "healthy"
    assert "version" in data


def test_docs_available():
    """Test that API documentation is available"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema():
    """Test that OpenAPI schema is available"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert "paths" in data


def test_envelope_middleware_leaves_204_body_empty():
    """204 responses must not be wrapped with a JSON envelope body."""
    from fastapi import FastAPI

    local_app = FastAPI()
    local_app.add_middleware(ApiEnvelopeMiddleware)

    @local_app.delete("/resource")
    def delete_resource():
        return Response(status_code=204)

    response = TestClient(local_app).delete("/resource")

    assert response.status_code == 204
    assert response.content == b""
