"""Lightweight auth/security tests for CI fast feedback."""

from datetime import timedelta

from app.services.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_encryption():
    plain_value = "SecureValue123!"

    hashed = hash_password(plain_value)

    assert hashed != plain_value
    assert hashed.startswith("$2")
    assert verify_password(plain_value, hashed)
    assert not verify_password("WrongPassword", hashed)


def test_password_hash_uniqueness():
    plain_value = "TestValue123"

    hash1 = hash_password(plain_value)
    hash2 = hash_password(plain_value)

    assert hash1 != hash2
    assert verify_password(plain_value, hash1)
    assert verify_password(plain_value, hash2)


def test_jwt_token_security():
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    token = create_access_token({"sub": user_id}, expires_delta=timedelta(hours=1))

    assert isinstance(token, str)
    assert len(token) > 0

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == user_id


def test_jwt_token_expiration():
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    token = create_access_token({"sub": user_id}, expires_delta=timedelta(seconds=-1))

    payload = decode_access_token(token)
    assert payload is None


def test_invalid_jwt_token():
    payload = decode_access_token("invalid.token.here")
    assert payload is None
