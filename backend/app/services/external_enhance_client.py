"""External enhancement client for hybrid inference."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


def call_external_enhance(payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    """Call external enhancement API and return normalized json response."""
    base_url = (settings.EXTERNAL_API_BASE_URL or "").strip()
    path = (settings.EXTERNAL_API_PATH or "/infer").strip() or "/infer"
    if not base_url:
        raise RuntimeError("EXTERNAL_API_BASE_URL is empty")

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if settings.EXTERNAL_API_KEY:
        headers["Authorization"] = f"Bearer {settings.EXTERNAL_API_KEY}"

    timeout_sec = max(float(timeout_ms) / 1000.0, 0.1)
    with httpx.Client(timeout=timeout_sec) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("External enhancement response must be a JSON object")
        return data
