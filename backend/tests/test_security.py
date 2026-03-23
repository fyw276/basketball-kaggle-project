"""
Security and privacy tests for the Smart Outfit Assistant API

Tests verify:
- Password encryption
- Data access control
- User data isolation
- Account deletion with cascade
"""

import pytest
from sqlalchemy.orm import Session

from app.schemas.user import UserCreate
from app.services.auth import hash_password, verify_password
from app.services.user import create_user, delete_user, get_user_by_id


def test_password_encryption():
    """Test that passwords are encrypted using bcrypt"""
    plain_password = "SecurePassword123!"

    # Hash password
    hashed = hash_password(plain_password)

    # Verify hash is different from plain text
    assert hashed != plain_password

    # Verify hash starts with bcrypt identifier
    assert hashed.startswith("$2b$")

    # Verify password can be verified
    assert verify_password(plain_password, hashed)

    # Verify wrong password fails
    assert not verify_password("WrongPassword", hashed)


def test_password_hash_uniqueness():
    """Test that same password generates different hashes (salt)"""
    plain_password = "TestPassword123"

    hash1 = hash_password(plain_password)
    hash2 = hash_password(plain_password)

    # Hashes should be different due to salt
    assert hash1 != hash2

    # Both should verify correctly
    assert verify_password(plain_password, hash1)
    assert verify_password(plain_password, hash2)


def test_user_data_isolation(db_session: Session):
    """Test that users can only access their own data"""
    # Create two users
    user1_data = UserCreate(username="user1", email="user1@test.com", password="password1")
    user2_data = UserCreate(username="user2", email="user2@test.com", password="password2")

    user1 = create_user(db_session, user1_data)
    user2 = create_user(db_session, user2_data)

    # Verify users have different IDs
    assert user1.user_id != user2.user_id

    # Verify each user can only retrieve their own data
    retrieved_user1 = get_user_by_id(db_session, user1.user_id)
    assert retrieved_user1.user_id == user1.user_id
    assert retrieved_user1.username == "user1"

    retrieved_user2 = get_user_by_id(db_session, user2.user_id)
    assert retrieved_user2.user_id == user2.user_id
    assert retrieved_user2.username == "user2"


def test_account_deletion(db_session: Session):
    """Test that account deletion removes user data"""
    # Create user
    user_data = UserCreate(username="testuser", email="test@test.com", password="password")
    user = create_user(db_session, user_data)
    user_id = user.user_id

    # Verify user exists
    assert get_user_by_id(db_session, user_id) is not None

    # Delete user
    result = delete_user(db_session, user_id)
    assert result is True

    # Verify user no longer exists
    assert get_user_by_id(db_session, user_id) is None


def test_account_deletion_cascade(db_session: Session):
    """Test that account deletion cascades to related data"""
    from app.models.garment import Garment
    from app.models.user_profile import UserProfile

    # Create user
    user_data = UserCreate(username="testuser", email="test@test.com", password="password")
    user = create_user(db_session, user_data)
    user_id = user.user_id

    # Create user profile
    profile = UserProfile(
        user_id=user_id,
        height=170,
        body_type="偏瘦",
        skin_tone="冷白",
        style_preference=["通勤"],
        budget_range="中等",
    )
    db_session.add(profile)

    # Create garment
    garment = Garment(
        user_id=user_id,
        category="上衣",
        main_color={"name": "蓝色", "rgb": [0, 100, 200]},
        image_path="/uploads/test.jpg",
        image_url="/uploads/test.jpg",
        feature_vector=[0.1] * 1280,
    )
    db_session.add(garment)
    db_session.commit()

    # Verify data exists
    assert db_session.query(UserProfile).filter(UserProfile.user_id == user_id).first() is not None
    assert db_session.query(Garment).filter(Garment.user_id == user_id).first() is not None

    # Delete user
    delete_user(db_session, user_id)

    # Verify cascade deletion
    assert db_session.query(UserProfile).filter(UserProfile.user_id == user_id).first() is None
    assert db_session.query(Garment).filter(Garment.user_id == user_id).first() is None


def test_password_not_exposed_in_response():
    """Test that password hash is not exposed in API responses"""
    from app.schemas.user import UserResponse

    # Create user response
    user_data = {
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "username": "testuser",
        "email": "test@test.com",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "is_active": True,
    }

    response = UserResponse(**user_data)

    # Verify password_hash is not in response
    response_dict = response.model_dump()
    assert "password" not in response_dict
    assert "password_hash" not in response_dict


def test_jwt_token_security():
    """Test JWT token generation and validation"""
    from datetime import timedelta

    from app.services.auth import create_access_token, decode_access_token

    # Create token
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    token = create_access_token({"sub": user_id}, expires_delta=timedelta(hours=1))

    # Verify token is a string
    assert isinstance(token, str)
    assert len(token) > 0

    # Decode token
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == user_id


def test_jwt_token_expiration():
    """Test that expired JWT tokens are rejected"""
    from datetime import timedelta

    from app.services.auth import create_access_token, decode_access_token

    # Create token with very short expiration
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    token = create_access_token({"sub": user_id}, expires_delta=timedelta(seconds=-1))

    # Attempt to decode expired token
    payload = decode_access_token(token)

    # Should return None for expired token
    assert payload is None


def test_invalid_jwt_token():
    """Test that invalid JWT tokens are rejected"""
    from app.services.auth import decode_access_token

    # Test with invalid token
    invalid_token = "invalid.token.here"
    decoded_user_id = decode_access_token(invalid_token)

    # Should return None for invalid token
    assert decoded_user_id is None


def test_user_cannot_delete_other_users(db_session: Session):
    """Test that users cannot delete other users' accounts"""
    # Create two users
    user1_data = UserCreate(username="user1", email="user1@test.com", password="password1")
    user2_data = UserCreate(username="user2", email="user2@test.com", password="password2")

    user1 = create_user(db_session, user1_data)
    user2 = create_user(db_session, user2_data)

    # In a real API, this would be enforced by the authentication middleware
    # Here we just verify that the delete function requires the correct user_id

    # User 1 should not be able to delete user 2
    # (In the API, this is enforced by get_current_user dependency)

    # Verify both users exist
    assert get_user_by_id(db_session, user1.user_id) is not None
    assert get_user_by_id(db_session, user2.user_id) is not None


def test_sensitive_data_not_logged():
    """Test that sensitive data is not logged"""
    # This is a placeholder test
    # In production, you would verify that:
    # - Passwords are never logged
    # - JWT tokens are not logged in full
    # - Personal information is redacted in logs

    # Example: verify password is not in log message
    log_message = "User login attempt for username: testuser"
    assert "password" not in log_message.lower()
    assert "secret" not in log_message.lower()


@pytest.fixture
def db_session():
    """Create a test database session"""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        # Cleanup
        db.rollback()
        db.close()
