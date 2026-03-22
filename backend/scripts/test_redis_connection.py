"""
Test Redis connection script
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.cache import cache  # noqa: E402
from app.core.config import settings  # noqa: E402


def test_redis():
    """Test Redis connection and basic operations"""
    print(f"Testing Redis connection to: {settings.REDIS_URL}")
    print("-" * 60)

    # Test connection
    try:
        if cache.ping():
            print("✓ Redis connection successful!")
        else:
            print("✗ Redis connection failed!")
            return False
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        return False

    # Test set operation
    try:
        test_key = "test:connection"
        test_value = {"message": "Hello Redis!"}
        if cache.set(test_key, test_value, expire=60):
            print("✓ Set operation successful!")
        else:
            print("✗ Set operation failed!")
            return False
    except Exception as e:
        print(f"✗ Set operation failed: {e}")
        return False

    # Test get operation
    try:
        retrieved = cache.get(test_key)
        if retrieved == test_value:
            print("✓ Get operation successful!")
        else:
            print(f"✗ Get operation failed! Expected {test_value}, got {retrieved}")
            return False
    except Exception as e:
        print(f"✗ Get operation failed: {e}")
        return False

    # Test exists operation
    try:
        if cache.exists(test_key):
            print("✓ Exists operation successful!")
        else:
            print("✗ Exists operation failed!")
            return False
    except Exception as e:
        print(f"✗ Exists operation failed: {e}")
        return False

    # Test TTL operation
    try:
        ttl = cache.ttl(test_key)
        if 0 < ttl <= 60:
            print(f"✓ TTL operation successful! (TTL: {ttl}s)")
        else:
            print(f"✗ TTL operation failed! Got TTL: {ttl}")
            return False
    except Exception as e:
        print(f"✗ TTL operation failed: {e}")
        return False

    # Test delete operation
    try:
        if cache.delete(test_key):
            print("✓ Delete operation successful!")
        else:
            print("✗ Delete operation failed!")
            return False
    except Exception as e:
        print(f"✗ Delete operation failed: {e}")
        return False

    # Verify deletion
    try:
        if not cache.exists(test_key):
            print("✓ Deletion verified!")
        else:
            print("✗ Key still exists after deletion!")
            return False
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False

    print("-" * 60)
    print("All Redis tests passed!")
    return True


if __name__ == "__main__":
    success = test_redis()
    sys.exit(0 if success else 1)
