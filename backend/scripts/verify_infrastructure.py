"""
Infrastructure verification script
Tests database connection, Redis cache, and authentication functionality
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.cache import cache  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.db.utils import check_db_connection  # noqa: E402
from app.services.auth import hash_password, verify_password  # noqa: E402


def print_section(title):
    """Print section header"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_database():
    """Test database connection"""
    print_section("Database Connection Test")

    try:
        # Test engine connection
        with engine.connect() as conn:
            result = conn.execute("SELECT version()")
            version = result.fetchone()[0]
            print("✓ Database engine connection successful")
            print(f"  PostgreSQL version: {version[:50]}...")

        # Test session connection
        db = SessionLocal()
        if check_db_connection(db):
            print("✓ Database session connection successful")
        else:
            print("✗ Database session connection failed")
            return False
        db.close()

        # Check if tables exist
        from sqlalchemy import inspect

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected_tables = ["users", "user_profiles", "garments"]

        print(f"\n  Found {len(tables)} tables:")
        for table in tables:
            status = "✓" if table in expected_tables else "•"
            print(f"  {status} {table}")

        missing_tables = set(expected_tables) - set(tables)
        if missing_tables:
            print(f"\n  ⚠ Missing tables: {', '.join(missing_tables)}")
            print("  Run 'python scripts/init_db.py' to create tables")

        return True

    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


def test_redis():
    """Test Redis connection"""
    print_section("Redis Cache Test")

    try:
        # Test connection
        if not cache.ping():
            print("✗ Redis connection failed")
            return False
        print("✓ Redis connection successful")

        # Test set/get operations
        test_key = "test:verify"
        test_value = {"status": "ok", "timestamp": "2024-01-01"}

        if not cache.set(test_key, test_value, expire=60):
            print("✗ Redis set operation failed")
            return False
        print("✓ Redis set operation successful")

        retrieved = cache.get(test_key)
        if retrieved != test_value:
            print(f"✗ Redis get operation failed: {retrieved}")
            return False
        print("✓ Redis get operation successful")

        # Test delete
        if not cache.delete(test_key):
            print("✗ Redis delete operation failed")
            return False
        print("✓ Redis delete operation successful")

        return True

    except Exception as e:
        print(f"✗ Redis test failed: {e}")
        return False


def test_authentication():
    """Test authentication functionality"""
    print_section("Authentication Test")

    try:
        # Test password hashing
        password = "test_password_123"
        hashed = hash_password(password)
        print("✓ Password hashing successful")

        # Test password verification
        if not verify_password(password, hashed):
            print("✗ Password verification failed")
            return False
        print("✓ Password verification successful")

        # Test wrong password
        if verify_password("wrong_password", hashed):
            print("✗ Password verification should fail for wrong password")
            return False
        print("✓ Wrong password correctly rejected")

        # Test JWT token
        from app.services.auth import create_access_token, decode_access_token

        token_data = {"sub": "test-user-id", "username": "testuser"}
        token = create_access_token(token_data)
        print("✓ JWT token creation successful")

        # Decode token
        decoded = decode_access_token(token)
        if not decoded or decoded.get("sub") != "test-user-id":
            print(f"✗ JWT token decoding failed: {decoded}")
            return False
        print("✓ JWT token decoding successful")

        return True

    except Exception as e:
        print(f"✗ Authentication test failed: {e}")
        return False


def test_models():
    """Test that models are properly imported"""
    print_section("Models Import Test")

    try:
        from app.models import Garment, User, UserProfile  # noqa: F401

        print("✓ User model imported")
        print("✓ UserProfile model imported")
        print("✓ Garment model imported")

        return True

    except Exception as e:
        print(f"✗ Models import failed: {e}")
        return False


def test_api_schemas():
    """Test that API schemas are properly defined"""
    print_section("API Schemas Test")

    try:
        from app.schemas import (  # noqa: F401
            Token,
            UserCreate,
            UserLogin,
            UserProfileCreate,
            UserResponse,
        )

        print("✓ User schemas imported")
        print("✓ UserProfile schemas imported")
        print("✓ Token schemas imported")

        # Test schema validation
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
        }
        UserCreate(**user_data)  # noqa: F841
        print("✓ UserCreate schema validation successful")

        return True

    except Exception as e:
        print(f"✗ API schemas test failed: {e}")
        return False


def main():
    """Run all verification tests"""
    print("\n" + "=" * 60)
    print("  INFRASTRUCTURE VERIFICATION")
    print("  Smart Outfit Assistant")
    print("=" * 60)
    print(f"\nEnvironment: {settings.ENVIRONMENT}")
    print(f"Debug mode: {settings.DEBUG}")
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")
    print(f"Redis: {settings.REDIS_URL}")

    results = {
        "Database": test_database(),
        "Redis": test_redis(),
        "Authentication": test_authentication(),
        "Models": test_models(),
        "API Schemas": test_api_schemas(),
    }

    # Print summary
    print_section("Verification Summary")
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("  ✓ ALL TESTS PASSED")
        print("  Infrastructure is ready!")
    else:
        print("  ✗ SOME TESTS FAILED")
        print("  Please fix the issues above")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
