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
    error_response = {
        "error": {
            "type": error_type,
            "message": message,
            "status_code": status_code,
        }
    }

    if details:
        error_response["error"]["details"] = details

    if path:
        error_response["error"]["path"] = path

    return JSONResponse(
        status_code=status_code,
        content=error_response,
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
    logger.error(
        f"Application error: {exc.message}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "details": exc.details,
        },
    )

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
    logger.warning(
        f"HTTP error: {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )

    return create_error_response(
        status_code=exc.status_code,
        message=str(exc.detail),
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
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.warning(
        f"Validation error: {len(errors)} field(s) failed validation",
        extra={
            "path": request.url.path,
            "errors": errors,
        },
    )

    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Validation error",
        error_type="ValidationError",
        details={"errors": errors},
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
    # Log full traceback for debugging
    logger.error(
        f"Unexpected error: {str(exc)}",
        extra={
            "path": request.url.path,
            "traceback": traceback.format_exc(),
        },
        exc_info=True,
    )

    # Don't expose internal error details in production
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred",
        error_type="InternalServerError",
        details={"error": str(exc)} if logger.level == "DEBUG" else None,
        path=request.url.path,
    )
