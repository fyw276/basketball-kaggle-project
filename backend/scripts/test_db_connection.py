"""
Test database connection script
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.db.utils import check_db_connection  # noqa: E402


def test_connection():
    """Test database connection"""
    print(f"Testing database connection to: {settings.DATABASE_URL}")
    print("-" * 60)

    # Test engine connection
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT version()")
            version = result.fetchone()[0]
            print("✓ Engine connection successful!")
            print(f"  PostgreSQL version: {version}")
    except Exception as e:
        print(f"✗ Engine connection failed: {e}")
        return False

    # Test session connection
    try:
        db = SessionLocal()
        if check_db_connection(db):
            print("✓ Session connection successful!")
        else:
            print("✗ Session connection failed!")
            return False
        db.close()
    except Exception as e:
        print(f"✗ Session connection failed: {e}")
        return False

    print("-" * 60)
    print("All database connection tests passed!")
    return True


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
