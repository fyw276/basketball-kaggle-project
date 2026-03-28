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
    """Base garment schema - 无性别推荐系统"""

    name: Optional[str] = Field(None, description="服装名称（如：蓝色条纹衬衫）")
    category: str = Field(..., description="Category: 上衣/裤子/裙子/外套/鞋/包")
    main_color: ColorSchema = Field(..., description="Main color")
    secondary_colors: List[ColorSchema] = Field(
        default_factory=list, description="Secondary colors"
    )
    style_tags: List[str] = Field(default_factory=list, description="Style tags: 通勤/休闲/正式等")
    fit_type: Optional[str] = Field(None, description="Fit type: 修身/宽松/标准/oversized")
    # 无性别推荐系统新增字段
    gender_label: str = Field(
        default="neutral",
        description="性别标签: male/female/neutral",
    )
    neutral_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="中性化程度: 0=完全性别化，1=完全中性",
    )
    notes: Optional[str] = Field(None, description="User notes")
    is_favorite: bool = Field(default=False, description="是否收藏")
    wearing_count: int = Field(default=0, ge=0, description="穿搭次数（用于智能推荐）")


class GarmentCreate(GarmentBase):
    """Schema for creating garment (without image processing)"""

    image_path: str = Field(..., description="Local image path")
    image_url: str = Field(..., description="Image URL")
    feature_vector: List[float] = Field(
        ..., min_length=1280, max_length=1280, description="1280-dim feature vector"
    )


class GarmentUpdate(BaseModel):
    """Schema for updating garment"""

    name: Optional[str] = None
    category: Optional[str] = None
    main_color: Optional[ColorSchema] = None
    secondary_colors: Optional[List[ColorSchema]] = None
    style_tags: Optional[List[str]] = None
    fit_type: Optional[str] = None
    gender_label: Optional[str] = Field(None, description="male/female/neutral")
    neutral_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    notes: Optional[str] = None
    is_favorite: Optional[bool] = None


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
VALID_GENDER_LABELS = ["male", "female", "neutral"]  # 无性别推荐系统
VALID_CATEGORIES = [
    # 基础品类
    "上衣",  # T-shirt, 衬衫, 毛衣, 卫衣, 针织衫
    "裤子",  # 牛仔裤, 西裤, 休闲裤, 运动裤
    "裙子",  # 连衣裙, 半裙, 短裙
    "外套",  # 夹克, 西装, 风衣, 大衣, 羽绒服
    "鞋",  # 运动鞋, 高跟鞋, 靴子, 休闲鞋
    "包",  # 手提包, 双肩包, 单肩包
    # 国风/汉服专用品类
    "汉服",  # 汉服整套（曲裾/直裾/圆领袍等）
    "国风",  # 新中式服装（旗袍/唐装/禅意风）
    "马面裙",  # 马面裙（单独作为品类）
    "上衣(汉)",  # 汉服上衣（上襦/衫/袄）
    "下装(汉)",  # 汉服下装（裙/裤）
]

VALID_FIT_TYPES = ["修身", "标准", "宽松", "oversized"]

VALID_STYLE_TAGS = [
    # 基础风格
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
    # 国风/汉服/民族风格
    "国风",
    "汉服",
    "新中式",
    "民族",
    "禅意",
    "古风",
    "优雅",
    "朋克",
]


# ──────────────────────────────────────────────────────────────────────────────
# 套装收藏 Schema
# ──────────────────────────────────────────────────────────────────────────────


class OutfitCollectionCreate(BaseModel):
    """创建套装收藏"""

    name: str = Field(..., description="套装名称（如：通勤商务装）", min_length=1, max_length=50)
    scene: str = Field(..., description="场景标签（如：通勤上班/约会）")
    description: Optional[str] = Field(None, description="套装描述/备注")
    garment_ids: List[str] = Field(..., description="服装ID列表", min_length=1)


class OutfitCollectionItem(BaseModel):
    """套装中的单件服装"""

    garment_id: UUID
    category: str
    name: Optional[str] = None
    image_url: str
    role: str = Field(default="other", description="角色：top/bottom/outer/shoes/bag/other")


class OutfitCollectionResponse(BaseModel):
    """套装收藏响应"""

    collection_id: UUID
    user_id: UUID
    name: str
    scene: str
    description: Optional[str]
    items: List[OutfitCollectionItem]
    overall_score: Optional[float] = Field(None, ge=0, le=1, description="综合评分（0-1）")
    worn_times: int = Field(default=0, description="穿搭次数")
    last_worn_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OutfitCollectionListResponse(BaseModel):
    """套装收藏列表"""

    total: int
    page: int
    page_size: int
    items: List[OutfitCollectionResponse]


# ──────────────────────────────────────────────────────────────────────────────
# 服装搜索 Schema
# ──────────────────────────────────────────────────────────────────────────────


class GarmentSearchQuery(BaseModel):
    """服装搜索查询条件 - 无性别推荐系统"""

    keyword: Optional[str] = Field(None, description="关键词（匹配名称/备注）")
    category: Optional[str] = Field(None, description="品类过滤")
    style_tags: Optional[List[str]] = Field(None, description="风格标签过滤（AND匹配）")
    color_name: Optional[str] = Field(None, description="主颜色名称（如：蓝/红/黑）")
    is_favorite: Optional[bool] = Field(None, description="仅收藏的服装")
    season: Optional[str] = Field(None, description="季节（春夏/秋冬/全年）")
    min_worn: Optional[int] = Field(None, ge=0, description="最小穿搭次数")
    # 无性别推荐系统：可按中性化程度过滤
    min_neutral_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="最小中性化程度（0-1）"
    )
    sort_by: str = Field(
        default="created_at",
        description="排序字段：created_at/worn_times/category/neutral_score",
    )
    sort_order: str = Field(default="desc", description="asc或desc")
