"""Lightweight tests for standardized error response shape."""

import json

from app.core.error_handlers import create_error_response


def test_create_error_response_with_details_and_path():
    response = create_error_response(
        status_code=400,
        message="Bad input",
        error_type="ValidationError",
        details={"field": "username"},
        path="/api/v1/test",
    )

    assert response.status_code == 400

    body = json.loads(response.body.decode())
    assert body["error"]["type"] == "ValidationError"
    assert body["error"]["message"] == "Bad input"
    assert body["error"]["status_code"] == 400
    assert body["error"]["details"]["field"] == "username"
    assert body["error"]["path"] == "/api/v1/test"


def test_create_error_response_without_optional_fields():
    response = create_error_response(
        status_code=500,
        message="Internal error",
        error_type="InternalServerError",
    )

    assert response.status_code == 500

    body = json.loads(response.body.decode())
    assert body["error"]["type"] == "InternalServerError"
    assert body["error"]["message"] == "Internal error"
    assert body["error"]["status_code"] == 500
    assert "details" not in body["error"]
    assert "path" not in body["error"]
