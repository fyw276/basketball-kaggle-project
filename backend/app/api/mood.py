"""
情绪推荐 API endpoints
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.garment import get_garments_by_user
from app.services.mood_recommender import MoodRecommender

router = APIRouter(prefix="/mood", tags=["Mood Recommendation"])


class MoodRecommendRequest(BaseModel):
    """情绪推荐请求"""

    mood: str = Field(
        ...,
        description=(
            "用户当前情绪: happy, excited, confident, relaxed, romantic, energetic, neutral, focused, "
            "sad, anxious, angry, tired, stressed, lonely"
        ),
    )
    include_wardrobe: bool = Field(default=False, description="是否从衣橱中筛选匹配单品")


class MoodRecommendResponse(BaseModel):
    """情绪推荐响应"""

    mood: str = Field(..., description="情绪类型")
    mood_cn: str = Field(..., description="情绪中文名")
    recommended_styles: List[str] = Field(..., description="推荐风格")
    recommended_colors: dict = Field(..., description="推荐颜色及权重")
    recommended_occasions: List[str] = Field(..., description="推荐场景")
    advice: str = Field(..., description="搭配建议")
    color_explanation: str = Field(..., description="颜色选择说明")
    matching_garments: List[dict] = Field(
        default_factory=list, description="衣橱中匹配的单品（如果 include_wardrobe=True）"
    )
    mood_intensity_color: str = Field(..., description="适合的情绪主题色")


class MoodLogRequest(BaseModel):
    """记录情绪日志"""

    mood: str = Field(..., description="情绪类型")
    note: Optional[str] = Field(None, description="备注")
    recommended_outfit_id: Optional[str] = Field(None, description="推荐的穿搭ID")


class MoodLogResponse(BaseModel):
    """情绪日志响应"""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")


@router.get("/moods", response_model=List[dict])
async def get_available_moods():
    """
    获取所有可用的情绪类型

    Returns:
        List of available mood types with labels
    """
    recommender = MoodRecommender()
    return recommender.get_all_moods()


@router.post("/recommend", response_model=MoodRecommendResponse)
async def recommend_by_mood(
    request: MoodRecommendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    根据情绪推荐穿搭

    根据用户当前情绪，返回：
    1. 推荐风格
    2. 推荐颜色
    3. 推荐场景
    4. 搭配建议
    5. 匹配的衣橱单品（可选）

    心理学依据：
    - 暖色调（红橙黄）提升情绪，适合悲伤、孤独时
    - 冷色调（蓝绿紫）镇静，适合焦虑、愤怒时
    - 明亮的颜色提神，适合疲惫时
    """
    recommender = MoodRecommender()
    result = recommender.recommend(request.mood)

    response_data = {
        "mood": result.mood,
        "mood_cn": result.mood_cn,
        "recommended_styles": result.recommended_styles,
        "recommended_colors": result.recommended_colors,
        "recommended_occasions": result.recommended_occasions,
        "advice": result.advice,
        "color_explanation": result.color_explanation,
        "mood_intensity_color": recommender.get_mood_intensity_color(request.mood),
        "matching_garments": [],
    }

    # 如果需要，从衣橱中筛选匹配的单品
    if request.include_wardrobe:
        from app.services.mood_filter import MoodFilter

        mood_filter = MoodFilter()
        garments = get_garments_by_user(db, current_user.user_id, limit=200)
        matching = mood_filter.filter_by_mood(garments, result)
        response_data["matching_garments"] = [
            {
                "garment_id": str(g.garment_id),
                "category": g.category,
                "main_color": g.main_color.get("name") if isinstance(g.main_color, dict) else None,
                "style_tags": g.style_tags or [],
                "image_url": g.image_url,
                "match_score": m.get("total_score", m.get("score", 0)),
            }
            for g, m in matching
        ]

    return response_data


@router.get("/quick-recall", response_model=List[dict])
async def get_quick_recall_moods(
    current_user: User = Depends(get_current_user),
):
    """
    获取快捷选择的心情选项

    简化版：只显示 6 种核心情绪
    """
    quick_moods = [
        {"value": "happy", "label": "开心", "icon": "😊", "color": "#FFD700"},
        {"value": "relaxed", "label": "放松", "icon": "😌", "color": "#87CEEB"},
        {"value": "confident", "label": "自信", "icon": "😎", "color": "#000000"},
        {"value": "sad", "label": "难过", "icon": "😢", "color": "#6A5ACD"},
        # 与「难过」同一引擎，文案强调「想心情更好」
        {"value": "sad", "label": "心情不好 · 想暖一点", "icon": "🌤️", "color": "#FF9F43"},
        {"value": "tired", "label": "疲惫", "icon": "😫", "color": "#DDA0DD"},
        {"value": "stressed", "label": "压力大", "icon": "😰", "color": "#778899"},
        {"value": "lonely", "label": "孤独 · 想被陪伴感", "icon": "🫂", "color": "#E8A0BF"},
    ]
    return quick_moods


@router.post("/log", response_model=MoodLogResponse)
async def log_mood(
    request: MoodLogRequest,
    current_user: User = Depends(get_current_user),
):
    """
    记录用户情绪日志

    用于追踪用户情绪模式和穿搭偏好关联
    """
    # 这里可以扩展为保存到数据库
    # 目前仅返回成功消息
    return MoodLogResponse(status="success", message=f"情绪 '{request.mood}' 已记录")


@router.get("/insights", response_model=dict)
async def get_mood_insights(
    current_user: User = Depends(get_current_user),
):
    """
    获取用户情绪洞察

    分析用户历史情绪记录，生成洞察报告
    """
    # TODO: 从数据库获取历史情绪数据
    # 暂时返回示例数据
    return {
        "total_records": 0,
        "dominant_mood": None,
        "mood_distribution": {},
        "outfit_satisfaction_by_mood": {},
        "recommendations": "记录更多情绪数据后，将为您提供更精准的穿搭建议",
    }
