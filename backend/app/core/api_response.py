"""Standard API response helpers."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def success_response(
    data: Any = None, *, message: str = "ok", status_code: int = 200
) -> JSONResponse:
    """Return the standard success envelope."""
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "data": data, "error": None, "message": message},
    )


def error_payload(
    *,
    message: str,
    error_type: str,
    status_code: int,
    details: Any = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Build the standard error envelope payload."""
    error: dict[str, Any] = {
        "type": error_type,
        "message": message,
        "status_code": status_code,
    }
    if details is not None:
        error["details"] = details
    if path:
        error["path"] = path
    return {"success": False, "data": None, "error": error, "message": message}
