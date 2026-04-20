"""Regression tests for structured try-on HTTP error envelope."""

import asyncio
import json
from types import SimpleNamespace

from app.core.error_handlers import http_exception_handler


class DummyHTTPException(Exception):
    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail


def _fake_request(path: str = "/api/v1/tryon/garment"):
    return SimpleNamespace(url=SimpleNamespace(path=path))


def test_http_exception_handler_preserves_structured_tryon_fields():
    request = _fake_request()
    exc = DummyHTTPException(
        status_code=503,
        detail={
            "message": "试衣服务额度暂时不足，请稍后重试。",
            "error_code": "TRYON_UPSTREAM_QUOTA",
            "retryable": True,
        },
    )

    response = asyncio.run(http_exception_handler(request, exc))
    assert response.status_code == 503

    payload = json.loads(response.body.decode("utf-8"))
    err = payload.get("error") or {}

    assert err.get("type") == "HTTPException"
    assert err.get("error_code") == "TRYON_UPSTREAM_QUOTA"
    assert err.get("retryable") is True


def test_http_exception_handler_keeps_string_detail_behavior():
    request = _fake_request()
    exc = DummyHTTPException(status_code=404, detail="Not found")

    response = asyncio.run(http_exception_handler(request, exc))
    assert response.status_code == 404

    payload = json.loads(response.body.decode("utf-8"))
    err = payload.get("error") or {}

    assert err.get("type") == "HTTPException"
    assert "Not found" in str(err.get("message"))
