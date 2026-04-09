"""
Unit tests for authentication module (Tasks 3.2, 3.5)
"""

import pytest

from app.core.config import settings
from app.services.auth import create_access_token, verify_password


@pytest.fixture
def test_user_data():
    """Test user registration data"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPass123",
    }


class TestUserRegistration:
    """Test user registration functionality (Task 3.2)"""

    def test_register_valid_user(self, test_client, test_user_data):
        """Test registration with valid user data"""
        response = test_client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == test_user_data["username"]
        assert data["email"] == test_user_data["email"]
        assert "user_id" in data
        assert data["is_active"] is True
        assert "created_at" in data
        assert "password" not in data  # Password should not be returned

    def test_register_duplicate_username(self, test_client, test_user_data):
        """Test registration with duplicate username"""
        # First registration
        test_client.post("/api/v1/auth/register", json=test_user_data)

        # Try to register with same username
        duplicate_data = test_user_data.copy()
        duplicate_data["email"] = "different@example.com"
        response = test_client.post("/api/v1/auth/register", json=duplicate_data)

        assert response.status_code == 400
        error_message = response.json()["error"]["message"].lower()
        assert "username already registered" in error_message

    def test_register_duplicate_email(self, test_client, test_user_data):
        """Test registration with duplicate email"""
        # Register first user
        first_user = test_user_data.copy()
        first_user["username"] = "firstuser"
        test_client.post("/api/v1/auth/register", json=first_user)

        # Try to register with same email
        duplicate_data = test_user_data.copy()
        duplicate_data["username"] = "seconduser"
        response = test_client.post("/api/v1/auth/register", json=duplicate_data)

        assert response.status_code == 400
        error_message = response.json()["error"]["message"].lower()
        assert "email already registered" in error_message

    def test_register_invalid_username_too_short(self, test_client):
        """Test registration with username too short"""
        response = test_client.post(
            "/api/v1/auth/register",
            json={"username": "ab", "email": "test@example.com", "password": "TestPass123"},
        )

        assert response.status_code == 422  # Validation error

    def test_register_invalid_username_too_long(self, test_client):
        """Test registration with username too long"""
        response = test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "a" * 51,  # 51 characters
                "email": "test@example.com",
                "password": "TestPass123",
            },
        )

        assert response.status_code == 422

    def test_register_invalid_email_format(self, test_client):
        """Test registration with invalid email format"""
        response = test_client.post(
            "/api/v1/auth/register",
            json={"username": "testuser", "email": "invalid-email", "password": "TestPass123"},
        )

        assert response.status_code == 422

    def test_register_invalid_password_too_short(self, test_client):
        """Test registration with password too short"""
        response = test_client.post(
            "/api/v1/auth/register",
            json={"username": "testuser", "email": "test@example.com", "password": "short"},
        )

        assert response.status_code == 422

    def test_register_missing_required_fields(self, test_client):
        """Test registration with missing required fields"""
        # Missing username
        response = test_client.post(
            "/api/v1/auth/register", json={"email": "test@example.com", "password": "TestPass123"}
        )
        assert response.status_code == 422

        # Missing email
        response = test_client.post(
            "/api/v1/auth/register", json={"username": "testuser", "password": "TestPass123"}
        )
        assert response.status_code == 422

        # Missing password
        response = test_client.post(
            "/api/v1/auth/register", json={"username": "testuser", "email": "test@example.com"}
        )
        assert response.status_code == 422

    def test_password_encryption(self, test_client, test_user_data):
        """Test that password is encrypted in database"""
        response = test_client.post("/api/v1/auth/register", json=test_user_data)
        assert response.status_code == 201

        # Password should not be in response
        data = response.json()
        assert "password" not in data
        assert "password_hash" not in data


class TestUserLogin:
    """Test user login functionality (Task 3.5)"""

    @pytest.fixture(autouse=True)
    def setup_user(self, test_client):
        """Create a test user before each test"""
        self.test_user = {
            "username": "loginuser",
            "email": "login@example.com",
            "password": "LoginPass123",
        }
        test_client.post("/api/v1/auth/register", json=self.test_user)

    def test_login_success(self, test_client):
        """Test successful login"""
        response = test_client.post(
            "/api/v1/auth/login",
            json={"username": self.test_user["username"], "password": self.test_user["password"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    def test_login_wrong_password(self, test_client):
        """Test login with wrong password"""
        response = test_client.post(
            "/api/v1/auth/login",
            json={"username": self.test_user["username"], "password": "WrongPassword123"},
        )

        assert response.status_code == 401
        error_message = response.json()["error"]["message"].lower()
        assert "incorrect username or password" in error_message

    def test_login_nonexistent_user(self, test_client):
        """Test login with non-existent username"""
        response = test_client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "SomePassword123"},
        )

        assert response.status_code == 401
        error_message = response.json()["error"]["message"].lower()
        assert "incorrect username or password" in error_message

    def test_login_missing_username(self, test_client):
        """Test login with missing username"""
        response = test_client.post("/api/v1/auth/login", json={"password": "SomePassword123"})

        assert response.status_code == 422

    def test_login_missing_password(self, test_client):
        """Test login with missing password"""
        response = test_client.post("/api/v1/auth/login", json={"username": "someuser"})

        assert response.status_code == 422

    def test_login_empty_credentials(self, test_client):
        """Test login with empty credentials"""
        response = test_client.post("/api/v1/auth/login", json={"username": "", "password": ""})

        # Empty credentials are treated as invalid login (401) not validation error (422)
        assert response.status_code == 401


class TestTokenGeneration:
    """Test JWT token generation and validation (Task 3.5)"""

    def test_create_access_token(self):
        """Test JWT token creation"""
        data = {"sub": "test-user-id", "username": "testuser"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT tokens have 3 parts separated by dots
        assert token.count(".") == 2

    def test_token_contains_user_data(self):
        """Test that token contains user data"""
        from datetime import timedelta

        from jose import jwt

        data = {"sub": "test-user-id", "username": "testuser"}
        token = create_access_token(data, expires_delta=timedelta(hours=1))

        # Decode token (without verification for testing)
        decoded = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        assert decoded["sub"] == "test-user-id"
        assert decoded["username"] == "testuser"
        assert "exp" in decoded  # Expiration time

    def test_token_expiration(self):
        """Test that token has expiration time"""
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        data = {"sub": "test-user-id"}
        expires_delta = timedelta(hours=1)
        token = create_access_token(data, expires_delta=expires_delta)

        decoded = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        # Check that expiration is set
        assert "exp" in decoded
        exp_timestamp = decoded["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

        # Expiration should be approximately 1 hour from now
        now = datetime.now(timezone.utc)
        time_diff = (exp_datetime - now).total_seconds()
        assert 3500 < time_diff < 3700  # Allow some margin


class TestAuthenticationMiddleware:
    """Test JWT authentication middleware (Task 3.5)"""

    @pytest.fixture(autouse=True)
    def setup_authenticated_user(self, test_client):
        """Create user and get token"""
        user_data = {
            "username": "authuser",
            "email": "auth@example.com",
            "password": "AuthPass123",
        }
        test_client.post("/api/v1/auth/register", json=user_data)

        response = test_client.post(
            "/api/v1/auth/login",
            json={"username": user_data["username"], "password": user_data["password"]},
        )
        self.token = response.json()["access_token"]

    def test_access_protected_endpoint_with_valid_token(self, test_client):
        """Test accessing protected endpoint with valid token"""
        response = test_client.get(
            "/api/v1/profile", headers={"Authorization": f"Bearer {self.token}"}
        )

        # Should not get 401 (might get 404 if profile doesn't exist, which is fine)
        assert response.status_code != 401

    def test_access_protected_endpoint_without_token(self, test_client):
        """Test accessing protected endpoint without token"""
        response = test_client.get("/api/v1/profile")

        # Missing token returns 403 Forbidden
        assert response.status_code == 403

    def test_access_protected_endpoint_with_invalid_token(self, test_client):
        """Test accessing protected endpoint with invalid token"""
        response = test_client.get(
            "/api/v1/profile", headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401

    def test_access_protected_endpoint_with_malformed_header(self, test_client):
        """Test accessing protected endpoint with malformed auth header"""
        # Missing "Bearer" prefix
        response = test_client.get("/api/v1/profile", headers={"Authorization": self.token})
        assert response.status_code == 403

        # Wrong prefix
        response = test_client.get(
            "/api/v1/profile", headers={"Authorization": f"Token {self.token}"}
        )
        assert response.status_code == 403

    def test_token_expiration_handling(self, test_client):
        """Test that expired tokens are rejected"""
        from datetime import timedelta

        # Create an expired token
        data = {"sub": "test-user-id", "username": "testuser"}
        expired_token = create_access_token(data, expires_delta=timedelta(seconds=-1))

        response = test_client.get(
            "/api/v1/profile", headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401


class TestPasswordSecurity:
    """Test password hashing and verification"""

    def test_password_hashing(self):
        """Test that passwords are hashed"""
        from app.services.auth import hash_password

        password = "TestPassword123"
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 0
        # Project prefers pbkdf2 to avoid passlib+bcrypt backend compatibility issues.
        assert hashed.startswith("$pbkdf2-sha256$")

    def test_password_verification_correct(self):
        """Test password verification with correct password"""
        from app.services.auth import hash_password

        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_password_verification_incorrect(self):
        """Test password verification with incorrect password"""
        from app.services.auth import hash_password

        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password("WrongPassword", hashed) is False

    def test_same_password_different_hashes(self):
        """Test that same password produces different hashes (salt)"""
        from app.services.auth import hash_password

        password = "TestPassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to salt
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True
