"""
Tests for API error handling
"""

import pytest
from fastapi import Request

from app.core.error_handlers import (
    app_exception_handler,
    create_error_response,
    generic_exception_handler,
    http_exception_handler,
)
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ImageProcessingError,
    NotFoundError,
    ValidationError,
)


def test_create_error_response():
    """Test standardized error response creation"""
    response = create_error_response(
        status_code=400,
        message="Test error",
        error_type="TestError",
        details={"field": "test"},
        path="/api/test",
    )

    assert response.status_code == 400
    content = response.body.decode()
    assert "Test error" in content
    assert "TestError" in content
    assert "field" in content


def test_validation_error():
    """Test ValidationError exception"""
    error = ValidationError("Invalid input", details={"field": "username"})

    assert error.status_code == 400
    assert error.message == "Invalid input"
    assert error.details["field"] == "username"


def test_authentication_error():
    """Test AuthenticationError exception"""
    error = AuthenticationError("Invalid credentials")

    assert error.status_code == 401
    assert error.message == "Invalid credentials"


def test_authorization_error():
    """Test AuthorizationError exception"""
    error = AuthorizationError("Access denied")

    assert error.status_code == 403
    assert error.message == "Access denied"


def test_not_found_error():
    """Test NotFoundError exception"""
    error = NotFoundError("User not found")

    assert error.status_code == 404
    assert error.message == "User not found"


def test_conflict_error():
    """Test ConflictError exception"""
    error = ConflictError("Username already exists")

    assert error.status_code == 409
    assert error.message == "Username already exists"


def test_image_processing_error():
    """Test ImageProcessingError exception"""
    error = ImageProcessingError("Invalid image format")

    assert error.status_code == 400
    assert error.message == "Invalid image format"


@pytest.mark.asyncio
async def test_app_exception_handler():
    """Test custom application exception handler"""
    from unittest.mock import Mock

    request = Mock(spec=Request)
    request.url.path = "/api/test"

    exc = ValidationError("Test validation error", details={"field": "test"})
    response = await app_exception_handler(request, exc)

    assert response.status_code == 400
    content = response.body.decode()
    assert "Test validation error" in content
    assert "ValidationError" in content


@pytest.mark.asyncio
async def test_http_exception_handler():
    """Test HTTP exception handler"""
    from unittest.mock import Mock

    from starlette.exceptions import HTTPException

    request = Mock(spec=Request)
    request.url.path = "/api/test"

    exc = HTTPException(status_code=404, detail="Not found")
    response = await http_exception_handler(request, exc)

    assert response.status_code == 404
    content = response.body.decode()
    assert "Not found" in content


@pytest.mark.asyncio
async def test_generic_exception_handler():
    """Test generic exception handler"""
    from unittest.mock import Mock

    request = Mock(spec=Request)
    request.url.path = "/api/test"

    exc = Exception("Unexpected error")
    response = await generic_exception_handler(request, exc)

    assert response.status_code == 500
    content = response.body.decode()
    assert "unexpected error" in content.lower()


def test_error_response_format():
    """Test that error responses follow the standard format"""
    response = create_error_response(
        status_code=400,
        message="Test error",
        error_type="TestError",
        details={"key": "value"},
        path="/api/test",
    )

    import json

    content = json.loads(response.body.decode())

    # Check structure
    assert "error" in content
    assert "type" in content["error"]
    assert "message" in content["error"]
    assert "status_code" in content["error"]
    assert "details" in content["error"]
    assert "path" in content["error"]

    # Check values
    assert content["error"]["type"] == "TestError"
    assert content["error"]["message"] == "Test error"
    assert content["error"]["status_code"] == 400
    assert content["error"]["details"]["key"] == "value"
    assert content["error"]["path"] == "/api/test"


def test_error_response_without_details():
    """Test error response without optional details"""
    response = create_error_response(
        status_code=500,
        message="Internal error",
        error_type="InternalError",
    )

    import json

    content = json.loads(response.body.decode())

    assert "error" in content
    assert content["error"]["message"] == "Internal error"
    assert "details" not in content["error"]
    assert "path" not in content["error"]
