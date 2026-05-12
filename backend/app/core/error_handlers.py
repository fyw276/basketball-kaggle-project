"""
Global exception handlers for the application
"""

import traceback
from typing import Union

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.api_response import error_payload
from app.core.exceptions import AppException
from app.core.logging import setup_logging

logger = setup_logging()


def create_error_response(
    status_code: int,
    message: str,
    error_type: str,
    details: dict = None,
    path: str = None,
) -> JSONResponse:
    """
    Create standardized error response

    Args:
        status_code: HTTP status code
        message: Error message
        error_type: Type of error
        details: Additional error details
        path: Request path

    Returns:
        JSONResponse with standardized error format
    """
    return JSONResponse(
        status_code=status_code,
        content=error_payload(
            message=message,
            error_type=error_type,
            status_code=status_code,
            details=details,
            path=path,
        ),
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handle custom application exceptions

    Args:
        request: FastAPI request
        exc: Application exception

    Returns:
        Standardized error response
    """
    logger.bind(
        status_code=exc.status_code,
        path=request.url.path,
        details=exc.details,
    ).error("Application error: {}", exc.message)

    return create_error_response(
        status_code=exc.status_code,
        message=exc.message,
        error_type=exc.__class__.__name__,
        details=exc.details,
        path=request.url.path,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handle HTTP exceptions

    Args:
        request: FastAPI request
        exc: HTTP exception

    Returns:
        Standardized error response
    """
    # exc.detail 常为 JSON/校验信息，含 {}；勿用 f-string，否则 Loguru 会当作占位符触发 KeyError
    logger.bind(
        status_code=exc.status_code,
        path=request.url.path,
    ).warning("HTTP error: {}", exc.detail)

    detail = exc.detail
    if isinstance(detail, dict):
        msg = str(detail.get("message") or "HTTP exception")
        payload = error_payload(
            message=msg,
            error_type="HTTPException",
            status_code=exc.status_code,
            details=detail,
            path=request.url.path,
        )

        # Promote client-facing fields for mobile/web parsers.
        error_obj = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error_obj, dict):
            for key in (
                "error_code",
                "retryable",
                "requires_upgrade",
                "remaining",
                "limit",
            ):
                if key in detail:
                    error_obj[key] = detail.get(key)

        return JSONResponse(status_code=exc.status_code, content=payload)

    return create_error_response(
        status_code=exc.status_code,
        message=str(detail),
        error_type="HTTPException",
        path=request.url.path,
    )


async def validation_exception_handler(
    request: Request,
    exc: Union[RequestValidationError, PydanticValidationError],
) -> JSONResponse:
    """
    Handle validation errors

    Args:
        request: FastAPI request
        exc: Validation exception

    Returns:
        Standardized error response
    """
    errors = []
    exc_errors_list = exc.errors()
    exc_body = getattr(exc, "body", None)

    for error in exc_errors_list:
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    # Safely log exc_body
    try:
        import json as _json

        _json.dumps(exc_body)
        body_for_log = exc_body
    except Exception:
        body_for_log = f"<non-serializable: {type(exc_body).__name__ if exc_body else 'None'}>"

    logger.bind(
        path=request.url.path,
        errors=errors,
        exc_errors=exc_errors_list,
        exc_body=body_for_log,
    ).warning(
        "Validation error: {} field(s) failed validation\n" "exc.errors() = {}\n" "exc.body = {}",
        len(errors),
        exc_errors_list,
        body_for_log,
    )

    # Only include body in details if it is JSON-serializable (avoid crashes in JSONResponse)
    details = {"errors": errors}

    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Validation error",
        error_type="ValidationError",
        details=details,
        path=request.url.path,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions

    Args:
        request: FastAPI request
        exc: Generic exception

    Returns:
        Standardized error response
    """
    # Log full traceback；异常信息可能含 {}，勿用 f-string 整段拼进 Loguru
    logger.bind(
        path=request.url.path,
        traceback_text=traceback.format_exc(),
    ).opt(
        exception=exc
    ).error("Unexpected error: {}", str(exc))

    # Don't expose internal error details in production
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred",
        error_type="InternalServerError",
        details={"error": str(exc)} if logger.level == "DEBUG" else None,
        path=request.url.path,
    )
