"""Lightweight exception contract tests."""

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)


def test_validation_error_contract():
    exc = ValidationError("invalid", details={"field": "username"})
    assert exc.status_code == 400
    assert exc.message == "invalid"
    assert exc.details["field"] == "username"


def test_authentication_error_contract():
    exc = AuthenticationError("bad token")
    assert exc.status_code == 401
    assert exc.message == "bad token"


def test_authorization_error_contract():
    exc = AuthorizationError("forbidden")
    assert exc.status_code == 403
    assert exc.message == "forbidden"


def test_not_found_error_contract():
    exc = NotFoundError("missing")
    assert exc.status_code == 404
    assert exc.message == "missing"


def test_conflict_error_contract():
    exc = ConflictError("duplicate")
    assert exc.status_code == 409
    assert exc.message == "duplicate"
