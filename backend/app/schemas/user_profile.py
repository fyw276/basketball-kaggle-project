"""
User profile schemas for request/response validation
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserProfileBase(BaseModel):
    """Base user profile schema"""

    height: int = Field(..., ge=100, le=250, description="Height in centimeters")
    body_type: str = Field(
        ...,
        description="Body type: 偏瘦/微胖/梨形/倒三角/沙漏/矩形",
    )
    skin_tone: str = Field(
        ...,
        description="Skin tone: 冷白/黄皮/小麦/深色",
    )
    style_preference: List[str] = Field(
        ...,
        min_length=1,
        description="Style preferences: 通勤/学院/甜酷/简约/街头/复古等",
    )
    budget_range: str = Field(
        ...,
        description="Budget range: 经济/中等/高端",
    )
    avoid_body_parts: List[str] = Field(
        default_factory=list,
        description="Body parts to avoid emphasizing: 肩/腰/臀/大腿/小腿等",
    )


class UserProfileCreate(UserProfileBase):
    """Schema for creating user profile"""

    pass


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile"""

    height: Optional[int] = Field(None, ge=100, le=250)
    body_type: Optional[str] = None
    skin_tone: Optional[str] = None
    style_preference: Optional[List[str]] = Field(None, min_length=1)
    budget_range: Optional[str] = None
    avoid_body_parts: Optional[List[str]] = None


class UserProfileResponse(UserProfileBase):
    """Schema for user profile response"""

    profile_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Enums for validation
VALID_BODY_TYPES = ["偏瘦", "微胖", "梨形", "倒三角", "沙漏", "矩形"]
VALID_SKIN_TONES = ["冷白", "黄皮", "小麦", "深色"]
VALID_STYLE_PREFERENCES = [
    "通勤",
    "学院",
    "甜酷",
    "简约",
    "街头",
    "复古",
    "休闲",
    "正式",
    "运动",
    "度假",
]
VALID_BUDGET_RANGES = ["经济", "中等", "高端"]
VALID_BODY_PARTS = ["肩", "腰", "臀", "大腿", "小腿", "手臂", "胸部"]
