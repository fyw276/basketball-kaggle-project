"""
User profile service
Handles user profile CRUD operations
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile
from app.schemas.user_profile import UserProfileCreate, UserProfileUpdate


def get_profile_by_user_id(db: Session, user_id: UUID) -> Optional[UserProfile]:
    """
    Get user profile by user ID

    Args:
        db: Database session
        user_id: User ID

    Returns:
        UserProfile object or None if not found
    """
    return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()


def create_profile(db: Session, user_id: UUID, profile_in: UserProfileCreate) -> UserProfile:
    """
    Create a new user profile

    Args:
        db: Database session
        user_id: User ID
        profile_in: Profile creation data

    Returns:
        Created profile object
    """
    db_profile = UserProfile(
        user_id=user_id,
        gender=profile_in.gender,
        gender_expression=profile_in.gender_expression,
        explore_cross_gender=profile_in.explore_cross_gender,
        height=profile_in.height,
        body_type=profile_in.body_type,
        skin_tone=profile_in.skin_tone,
        style_preference=profile_in.style_preference,
        budget_range=profile_in.budget_range,
        avoid_body_parts=profile_in.avoid_body_parts,
    )

    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)

    return db_profile


def update_profile(db: Session, profile: UserProfile, profile_in: UserProfileUpdate) -> UserProfile:
    """
    Update user profile

    Args:
        db: Database session
        profile: Existing profile object
        profile_in: Profile update data

    Returns:
        Updated profile object
    """
    update_data = profile_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile


def delete_profile(db: Session, user_id: UUID) -> bool:
    """
    Delete user profile

    Args:
        db: Database session
        user_id: User ID

    Returns:
        True if deleted, False if not found
    """
    profile = get_profile_by_user_id(db, user_id)
    if profile:
        db.delete(profile)
        db.commit()
        return True
    return False
