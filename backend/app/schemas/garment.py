"""
Garment schemas for request/response validation
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ColorSchema(BaseModel):
    """Color schema"""

    name: str = Field(..., description="Standard color name")
    rgb: tuple[int, int, int] = Field(..., description="RGB values (0-255)")
    hsv: tuple[float, float, float] = Field(..., description="HSV values")
    hex_code: str = Field(..., description="Hex color code")


class GarmentBase(BaseModel):
    """Base garment schema"""

    category: str = Field(..., description="Category: 上衣/裤子/裙子/外套/鞋/包")
    main_color: ColorSchema = Field(..., description="Main color")
    secondary_colors: List[ColorSchema] = Field(
        default_factory=list, description="Secondary colors"
    )
    style_tags: List[str] = Field(default_factory=list, description="Style tags: 通勤/休闲/正式等")
    fit_type: Optional[str] = Field(None, description="Fit type: 修身/宽松/标准/oversized")
    notes: Optional[str] = Field(None, description="User notes")


class GarmentCreate(GarmentBase):
    """Schema for creating garment (without image processing)"""

    image_path: str = Field(..., description="Local image path")
    image_url: str = Field(..., description="Image URL")
    feature_vector: List[float] = Field(
        ..., min_length=1280, max_length=1280, description="1280-dim feature vector"
    )


class GarmentUpdate(BaseModel):
    """Schema for updating garment"""

    category: Optional[str] = None
    main_color: Optional[ColorSchema] = None
    secondary_colors: Optional[List[ColorSchema]] = None
    style_tags: Optional[List[str]] = None
    fit_type: Optional[str] = None
    notes: Optional[str] = None


class GarmentResponse(GarmentBase):
    """Schema for garment response"""

    garment_id: UUID
    user_id: UUID
    image_path: str
    image_url: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GarmentListResponse(BaseModel):
    """Schema for garment list response with pagination"""

    total: int
    page: int
    page_size: int
    items: List[GarmentResponse]


# Valid values
VALID_CATEGORIES = ["上衣", "裤子", "裙子", "外套", "鞋", "包"]
VALID_FIT_TYPES = ["修身", "宽松", "标准", "oversized"]
VALID_STYLE_TAGS = [
    "通勤",
    "休闲",
    "正式",
    "运动",
    "街头",
    "复古",
    "学院",
    "甜酷",
    "简约",
    "度假",
]
