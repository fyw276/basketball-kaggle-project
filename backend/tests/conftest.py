"""
Shared pytest configuration and fixtures for all test modules
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Import all models to register them with Base.metadata
from app.models import garment, outfit_collection, user, user_profile  # noqa: F401

# Use file-based SQLite database for tests (will be deleted after session)
TEST_DB_PATH = "test_database.db"
SQLALCHEMY_TEST_DATABASE_URL = f"sqlite:///./{TEST_DB_PATH}"


@pytest.fixture(scope="session")
def test_engine():
    """Create a single test database engine for the entire test session"""
    # Remove existing test database if it exists
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    # Clean up test database file
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Create a session factory for the test session"""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def test_client(test_session_factory):
    """Create a test client with database override for the entire test session"""

    def override_get_db():
        """Override database dependency for testing"""
        try:
            db = test_session_factory()
            yield db
        finally:
            db.close()

    # Override the dependency
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    # Clean up override after session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="function", autouse=True)
def setup_database(test_engine):
    """Clean database tables before each test function"""
    # Clear all tables before each test
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    # Tables will be cleaned before next test


@pytest.fixture
def client(test_client):
    """Provide test client for each test function"""
    return test_client


@pytest.fixture
def auth_headers(client):
    """Create a test user and return authentication headers"""
    # Register user
    user_data = {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "Test123!@#",
    }
    client.post("/api/v1/auth/register", json=user_data)

    # Login to get token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": user_data["username"], "password": user_data["password"]},
    )
    token = login_response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def second_user_headers(client):
    """Create a second test user and return authentication headers"""
    # Register second user
    user_data = {
        "username": "testuser2",
        "email": "testuser2@example.com",
        "password": "Test123!@#",
    }
    client.post("/api/v1/auth/register", json=user_data)

    # Login to get token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": user_data["username"], "password": user_data["password"]},
    )
    token = login_response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}
