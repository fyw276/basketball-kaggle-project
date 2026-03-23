"""
User API endpoints
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.user import UserResponse
from app.services.user import delete_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current user information

    Args:
        current_user: Current authenticated user

    Returns:
        Current user information
    """
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete current user account and all associated data

    This endpoint permanently deletes:
    - User account
    - User profile
    - All garments in wardrobe
    - All uploaded images

    This action cannot be undone.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        204 No Content on success
    """
    # Delete user (cascade will handle related data)
    delete_user(db, current_user.user_id)

    return None
