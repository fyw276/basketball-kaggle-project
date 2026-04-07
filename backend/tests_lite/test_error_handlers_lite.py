"""Lightweight tests for async error handlers."""

import asyncio
from types import SimpleNamespace

from app.core.error_handlers import app_exception_handler, http_exception_handler
from app.core.exceptions import ValidationError


class DummyHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def _fake_request(path: str = "/api/v1/test"):
    return SimpleNamespace(url=SimpleNamespace(path=path))


def test_app_exception_handler_returns_standardized_payload():
    request = _fake_request("/api/v1/demo")
    exc = ValidationError("invalid payload", details={"field": "username"})

    response = asyncio.run(app_exception_handler(request, exc))

    assert response.status_code == 400
    body = response.body.decode()
    assert "ValidationError" in body
    assert "invalid payload" in body
    assert "/api/v1/demo" in body


def test_http_exception_handler_returns_standardized_payload():
    request = _fake_request("/api/v1/not-found")
    exc = DummyHTTPException(status_code=404, detail="Not found")

    response = asyncio.run(http_exception_handler(request, exc))

    assert response.status_code == 404
    body = response.body.decode()
    assert "HTTPException" in body
    assert "Not found" in body
    assert "/api/v1/not-found" in body
