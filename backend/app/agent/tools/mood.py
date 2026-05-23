"""Mood tools: mood_recommend, list_mood_types."""

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.agent.tools.registry import register_tool


@register_tool(
    name="mood_recommend",
    description="根据用户当前情绪推荐穿搭风格、颜色和场合。",
    parameters_schema={
        "type": "object",
        "properties": {
            "mood": {
                "type": "string",
                "description": "情绪类型，如：happy/sad/anxious/confident/relaxed/tired",
            },
        },
        "required": ["mood"],
    },
    mcp_name="recommend_by_mood",
    category="mood",
)
async def mood_recommend(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.services.mood_recommender import MoodRecommender

    mood = kw.get("mood", "neutral")
    rec = MoodRecommender().recommend(mood)
    return {
        "mood": rec.mood,
        "mood_cn": rec.mood_cn,
        "recommended_styles": rec.recommended_styles,
        "recommended_colors": rec.recommended_colors,
        "recommended_occasions": rec.recommended_occasions,
        "advice": rec.advice,
        "color_explanation": rec.color_explanation,
    }


@register_tool(
    name="list_mood_types",
    description="查看所有支持的情绪类型列表。",
    parameters_schema={"type": "object", "properties": {}},
    mcp_name="list_mood_types",
    category="mood",
)
async def list_mood_types(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.services.mood_recommender import MoodRecommender

    moods = MoodRecommender().get_all_moods()
    return {"moods": moods}
