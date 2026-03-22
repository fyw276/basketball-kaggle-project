"""
Database initialization script
Creates all tables defined in SQLAlchemy models
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.models import Garment, User, UserProfile  # noqa: E402, F401


def init_db():
    """Initialize database by creating all tables"""
    print(f"Initializing database at: {settings.DATABASE_URL}")
    print("Creating tables...")

    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✓ All tables created successfully!")

        # Print created tables
        print("\nCreated tables:")
        for table in Base.metadata.sorted_tables:
            print(f"  - {table.name}")

    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_db()
