"""
Guardrail tests for virtual try-on API.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from PIL import Image


def _jpeg_bytes(
    size: tuple[int, int] = (256, 256), color: tuple[int, int, int] = (255, 255, 255)
) -> bytes:
    im = Image.new("RGB", size=size, color=color)
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_tryon_requires_auth(client: TestClient):
    # Dependency get_current_user should reject before any heavy processing.
    res = client.post("/api/v1/tryon/garment")
    # Some auth backends return 403 (forbidden) instead of 401 (unauthorized).
    assert res.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_tryon_rejects_garment_with_face(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """
    When garment image is detected as containing a face,
    the service should reject to prevent ghosting.
    We simulate this by monkeypatching the singleton try-on service.
    """

    class _StubService:
        def tryon_garment(self, **kwargs):
            return {
                "result_image": None,
                "status": "error",
                "message": "衣服图检测到人像，请上传无模特的白底商品图，否则会出现重影。",
                "metadata": {"reason": "garment_contains_face"},
            }

    def _stub_get_tryon_service():
        return _StubService()

    import app.services.virtual_tryon as virtual_tryon  # local import for monkeypatch

    monkeypatch.setattr(virtual_tryon, "get_tryon_service", _stub_get_tryon_service)

    garment_bytes = _jpeg_bytes(color=(250, 250, 250))
    person_bytes = _jpeg_bytes(color=(220, 220, 220))

    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }
    res = client.post(
        "/api/v1/tryon/garment", headers=auth_headers, files=files, data={"prompt": "front view"}
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    body = res.json()
    # Project uses a unified error envelope: { error: { message, ... } }
    assert "error" in body
    msg = body["error"].get("message") if isinstance(body["error"], dict) else str(body["error"])
    assert "检测到人像" in str(msg)


def test_tryon_error_envelope_contains_error_code_and_retryable(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """E2E contract: error envelope should expose client-facing try-on fields."""

    async def _stub_bailian_tryon(**kwargs):
        return {
            "result_image": None,
            "status": "error",
            "message": "Error: 429 quota exceeded",
            "metadata": {},
        }

    async def _stub_remote_vton(**kwargs):
        return None

    class _StubService:
        def tryon_garment(self, **kwargs):
            return {
                "result_image": None,
                "status": "error",
                "message": "Error: 429 quota exceeded",
                "metadata": {},
            }

    def _stub_get_tryon_service():
        return _StubService()

    import app.services.bailian_tryon_client as bailian_tryon_client
    import app.services.virtual_tryon as virtual_tryon
    import app.services.vton_remote_client as vton_remote_client

    monkeypatch.setattr(bailian_tryon_client, "call_bailian_tryon", _stub_bailian_tryon)
    monkeypatch.setattr(vton_remote_client, "call_remote_vton", _stub_remote_vton)
    monkeypatch.setattr(virtual_tryon, "get_tryon_service", _stub_get_tryon_service)

    garment_bytes = _jpeg_bytes(color=(250, 250, 250))
    person_bytes = _jpeg_bytes(color=(220, 220, 220))

    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }
    res = client.post("/api/v1/tryon/garment", headers=auth_headers, files=files)

    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = res.json()
    err = body.get("error") if isinstance(body, dict) else None
    assert isinstance(err, dict)
    assert err.get("error_code") == "TRYON_UPSTREAM_QUOTA"
    assert err.get("retryable") is True
