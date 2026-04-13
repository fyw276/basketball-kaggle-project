"""External enhancement client for hybrid inference."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

_external_enhance_available: bool = True
_external_enhance_reason: str = "not_checked"


def set_external_enhance_available(is_available: bool, reason: str = "") -> None:
    """Set runtime availability flag for external enhancement."""
    global _external_enhance_available, _external_enhance_reason
    _external_enhance_available = bool(is_available)
    _external_enhance_reason = reason or ("ok" if is_available else "unavailable")


def get_external_enhance_status() -> tuple[bool, str]:
    """Get runtime availability and reason."""
    return _external_enhance_available, _external_enhance_reason


def is_external_enhance_available() -> bool:
    """Return whether external enhancement is available at runtime."""
    return _external_enhance_available


def probe_external_enhance(timeout_ms: int) -> tuple[bool, str]:
    """Probe external enhancement endpoint and update runtime availability."""
    base_url = (settings.EXTERNAL_API_BASE_URL or "").strip()
    if not settings.EXTERNAL_ENHANCE_ENABLED:
        set_external_enhance_available(False, "disabled_by_config")
        return False, "disabled_by_config"

    if not base_url:
        set_external_enhance_available(False, "empty_base_url")
        return False, "empty_base_url"

    if not settings.EXTERNAL_HEALTHCHECK_ENABLED:
        set_external_enhance_available(True, "healthcheck_disabled")
        return True, "healthcheck_disabled"

    health_path = (settings.EXTERNAL_API_HEALTH_PATH or "/health").strip() or "/health"
    health_url = f"{base_url.rstrip('/')}/{health_path.lstrip('/')}"
    infer_path = (settings.EXTERNAL_API_PATH or "/infer").strip() or "/infer"
    infer_url = f"{base_url.rstrip('/')}/{infer_path.lstrip('/')}"

    timeout_sec = max(float(timeout_ms) / 1000.0, 0.1)
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            try:
                response = client.get(health_url)
                if response.status_code < 500:
                    set_external_enhance_available(True, f"health_status_{response.status_code}")
                    return True, f"health_status_{response.status_code}"
            except Exception:
                # Fallback: infer endpoint may exist without dedicated health endpoint.
                pass

            response = client.options(infer_url)
            if response.status_code < 500:
                set_external_enhance_available(True, f"infer_options_{response.status_code}")
                return True, f"infer_options_{response.status_code}"
    except Exception as exc:
        set_external_enhance_available(False, f"probe_failed:{exc}")
        return False, f"probe_failed:{exc}"

    set_external_enhance_available(False, "probe_unhealthy")
    return False, "probe_unhealthy"


def call_external_enhance(payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    """Call external enhancement API and return normalized json response."""
    from app.observability.dependency_metrics import (
        classify_external_exception,
        record_dependency_outcome,
    )

    try:
        if not _external_enhance_available:
            raise RuntimeError(f"External enhancement unavailable: {_external_enhance_reason}")

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
        record_dependency_outcome("external_enhance", "success")
        return data
    except Exception as e:
        if isinstance(e, RuntimeError) and "unavailable" in str(e).lower():
            record_dependency_outcome("external_enhance", "degraded")
        elif isinstance(e, RuntimeError):
            record_dependency_outcome("external_enhance", "failure")
        else:
            record_dependency_outcome("external_enhance", classify_external_exception(e))
        raise
