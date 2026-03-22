"""
User service
Handles user CRUD operations
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth import hash_password


def get_user_by_id(db: Session, user_id: UUID) -> Optional[User]:
    """
    Get user by ID

    Args:
        db: Database session
        user_id: User ID

    Returns:
        User object or None if not found
    """
    return db.query(User).filter(User.user_id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """
    Get user by username

    Args:
        db: Database session
        username: Username

    Returns:
        User object or None if not found
    """
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get user by email

    Args:
        db: Database session
        email: Email address

    Returns:
        User object or None if not found
    """
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, user_in: UserCreate) -> User:
    """
    Create a new user

    Args:
        db: Database session
        user_in: User creation data

    Returns:
        Created user object
    """
    # Hash the password
    hashed_password = hash_password(user_in.password)

    # Create user object
    db_user = User(
        username=user_in.username,
        email=user_in.email,
        password_hash=hashed_password,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


def update_user(db: Session, user: User, user_in: UserUpdate) -> User:
    """
    Update user information

    Args:
        db: Database session
        user: Existing user object
        user_in: User update data

    Returns:
        Updated user object
    """
    update_data = user_in.model_dump(exclude_unset=True)

    # Hash password if provided
    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def delete_user(db: Session, user_id: UUID) -> bool:
    """
    Delete a user

    Args:
        db: Database session
        user_id: User ID

    Returns:
        True if deleted, False if not found
    """
    user = get_user_by_id(db, user_id)
    if user:
        db.delete(user)
        db.commit()
        return True
    return False


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate a user

    Args:
        db: Database session
        username: Username
        password: Plain text password

    Returns:
        User object if authentication successful, None otherwise
    """
    from app.services.auth import verify_password

    user = get_user_by_username(db, username)
    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user
