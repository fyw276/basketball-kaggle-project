"""
Pydantic schemas for request/response validation
"""

from app.schemas.user import Token, TokenData, UserCreate, UserLogin, UserResponse, UserUpdate
from app.schemas.user_profile import (
    VALID_BODY_PARTS,
    VALID_BODY_TYPES,
    VALID_BUDGET_RANGES,
    VALID_SKIN_TONES,
    VALID_STYLE_PREFERENCES,
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)

__all__ = [
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    "Token",
    "TokenData",
    "UserProfileCreate",
    "UserProfileUpdate",
    "UserProfileResponse",
    "VALID_BODY_TYPES",
    "VALID_SKIN_TONES",
    "VALID_STYLE_PREFERENCES",
    "VALID_BUDGET_RANGES",
    "VALID_BODY_PARTS",
]
