"""
Shared pytest configuration and fixtures for all test modules
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Transformers may mis-detect a broken/namespace tensorflow and crash when checking tf.Tensor.
# Force-disable TF integration for this test suite (we use torch-based paths).
# NOTE: transformers computes availability at import time; USE_TORCH is respected there.
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("USE_TF", "0")

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

# Import all models to register them with Base.metadata
from app.models import garment, outfit_collection, user, user_profile  # noqa: F401,E402

# Use a temp file for test DB so Windows doesn't lock it between runs
_test_db_fd, TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)
SQLALCHEMY_TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"


@pytest.fixture(scope="session")
def test_engine():
    """Create a single test database engine for the entire test session"""
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            pass


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
