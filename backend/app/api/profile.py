"""
User profile API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user_profile import (
    VALID_BODY_PARTS,
    VALID_BODY_TYPES,
    VALID_BUDGET_RANGES,
    VALID_GENDERS,
    VALID_SKIN_TONES,
    VALID_STYLE_PREFERENCES,
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.user_profile import create_profile, get_profile_by_user_id, update_profile

router = APIRouter(prefix="/profile", tags=["User Profile"])

BUDGET_RANGE_ALIASES = {
    "经济实惠": "经济",
    "中等消费": "中等",
    "高端品质": "高端",
}


def normalize_profile_data(profile_data: UserProfileCreate | UserProfileUpdate):
    """Normalize legacy/mobile display values before strict enum validation."""
    budget_range = getattr(profile_data, "budget_range", None)
    if budget_range in BUDGET_RANGE_ALIASES:
        profile_data.budget_range = BUDGET_RANGE_ALIASES[budget_range]


def validate_profile_data(profile_data: UserProfileCreate | UserProfileUpdate):
    """
    Validate profile data against allowed values

    Args:
        profile_data: Profile data to validate

    Raises:
        HTTPException: If validation fails
    """
    normalize_profile_data(profile_data)

    # Validate gender
    if hasattr(profile_data, "gender") and profile_data.gender:
        if profile_data.gender not in VALID_GENDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid gender. Must be one of: {', '.join(VALID_GENDERS)}",
            )

    # Validate body type
    if hasattr(profile_data, "body_type") and profile_data.body_type:
        if profile_data.body_type not in VALID_BODY_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid body_type. Must be one of: {', '.join(VALID_BODY_TYPES)}",
            )

    # Validate skin tone
    if hasattr(profile_data, "skin_tone") and profile_data.skin_tone:
        if profile_data.skin_tone not in VALID_SKIN_TONES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid skin_tone. Must be one of: {', '.join(VALID_SKIN_TONES)}",
            )

    # Validate style preferences
    if hasattr(profile_data, "style_preference") and profile_data.style_preference:
        invalid_styles = [
            s for s in profile_data.style_preference if s not in VALID_STYLE_PREFERENCES
        ]
        if invalid_styles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid style preferences: {', '.join(invalid_styles)}. "
                f"Must be from: {', '.join(VALID_STYLE_PREFERENCES)}",
            )

    # Validate budget range
    if hasattr(profile_data, "budget_range") and profile_data.budget_range:
        if profile_data.budget_range not in VALID_BUDGET_RANGES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid budget_range. Must be one of: {', '.join(VALID_BUDGET_RANGES)}",
            )

    # Validate avoid body parts
    if hasattr(profile_data, "avoid_body_parts") and profile_data.avoid_body_parts:
        invalid_parts = [p for p in profile_data.avoid_body_parts if p not in VALID_BODY_PARTS]
        if invalid_parts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid body parts: {', '.join(invalid_parts)}. "
                f"Must be from: {', '.join(VALID_BODY_PARTS)}",
            )


@router.post("", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
@router.post(
    "/",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_user_profile(
    profile_in: UserProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create user profile

    Args:
        profile_in: Profile creation data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created profile

    Raises:
        HTTPException: If profile already exists or validation fails
    """
    # Check if profile already exists
    existing_profile = get_profile_by_user_id(db, current_user.user_id)
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User profile already exists. Use PUT to update.",
        )

    # Validate profile data
    validate_profile_data(profile_in)

    # Create profile
    profile = create_profile(db, current_user.user_id, profile_in)

    return profile


@router.get("", response_model=UserProfileResponse)
@router.get("/", response_model=UserProfileResponse, include_in_schema=False)
def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current user's profile

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        User profile

    Raises:
        HTTPException: If profile not found
    """
    profile = get_profile_by_user_id(db, current_user.user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    return profile


@router.put("", response_model=UserProfileResponse)
@router.put("/", response_model=UserProfileResponse, include_in_schema=False)
def update_user_profile(
    profile_in: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update user profile

    Args:
        profile_in: Profile update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated profile

    Raises:
        HTTPException: If profile not found or validation fails
    """
    # Get existing profile
    profile = get_profile_by_user_id(db, current_user.user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Use POST to create.",
        )

    # Validate profile data
    validate_profile_data(profile_in)

    # Update profile
    updated_profile = update_profile(db, profile, profile_in)

    return updated_profile
