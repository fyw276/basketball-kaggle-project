"""Helpers for tests against the unified API JSON envelope."""

from __future__ import annotations

from typing import Any


def unwrap_json(response: Any) -> Any:
    """
    Return the inner payload for successful API responses.

    Success responses are wrapped as:
    ``{ "success": true, "data": <payload>, "error": null, "message": "ok" }``

    Error envelopes, FastAPI validation bodies, and OpenAPI docs are returned as-is.
    """
    body = response.json()
    if not isinstance(body, dict):
        return body
    if body.get("success") is True and "data" in body and "error" in body:
        return body["data"]
    return body
