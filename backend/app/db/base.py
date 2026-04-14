"""
Database base configuration
"""

from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


# Import models after Base is defined to avoid circular imports
# These imports are needed for Base.metadata.create_all() to work
def import_models():
    """Import all models to register them with Base.metadata"""
    from app.models import (  # noqa: F401
        feedback_event,
        garment,
        memory_snippet,
        outfit_collection,
        subscription,
        user,
        user_profile,
    )
