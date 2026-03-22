"""
Database utility functions
"""

from typing import Generic, Optional, Type, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class CRUDBase(Generic[ModelType]):
    """
    Base class for CRUD operations

    Provides common database operations for any model
    """

    def __init__(self, model: Type[ModelType]):
        """
        Initialize CRUD object with model class

        Args:
            model: SQLAlchemy model class
        """
        self.model = model

    def get(self, db: Session, id: any) -> Optional[ModelType]:
        """
        Get a single record by ID

        Args:
            db: Database session
            id: Record ID

        Returns:
            Model instance or None if not found
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """
        Get multiple records with pagination

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances
        """
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: dict) -> ModelType:
        """
        Create a new record

        Args:
            db: Database session
            obj_in: Dictionary of field values

        Returns:
            Created model instance
        """
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, *, db_obj: ModelType, obj_in: dict) -> ModelType:
        """
        Update an existing record

        Args:
            db: Database session
            db_obj: Existing model instance
            obj_in: Dictionary of field values to update

        Returns:
            Updated model instance
        """
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, id: any) -> Optional[ModelType]:
        """
        Delete a record by ID

        Args:
            db: Database session
            id: Record ID

        Returns:
            Deleted model instance or None if not found
        """
        obj = db.query(self.model).get(id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj


def check_db_connection(db: Session) -> bool:
    """
    Check if database connection is working

    Args:
        db: Database session

    Returns:
        True if connection is working, False otherwise
    """
    try:
        db.execute("SELECT 1")
        return True
    except SQLAlchemyError:
        return False


def create_tables(engine):
    """
    Create all tables in the database

    Args:
        engine: SQLAlchemy engine
    """
    Base.metadata.create_all(bind=engine)


def drop_tables(engine):
    """
    Drop all tables in the database

    WARNING: This will delete all data!

    Args:
        engine: SQLAlchemy engine
    """
    Base.metadata.drop_all(bind=engine)
