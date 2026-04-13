"""Thin rule-based intent router for MCP / Agent demos (not a fixed LLM chain)."""

from typing import List, Tuple

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.api_response import success_response

router = APIRouter(prefix="/agent", tags=["Agent"])


# (keywords, tool_names, label)
_INTENT_RULES: List[Tuple[List[str], List[str], str]] = [
    (["天气", "气温", "下雨", "刮风", "冷", "热"], ["get_weather_by_city"], "weather"),
    (["衣橱", "衣柜", "衣服列表", "我的衣服"], ["list_wardrobe"], "wardrobe"),
    (["相似", "重复", "撞衫"], ["analyze_similarity"], "similarity"),
    (["适合", "合身", "肤色"], ["analyze_suitability"], "suitability"),
    (["场景", "约会", "通勤", "运动", "搭配推荐"], ["recommend_outfits"], "outfit_scene"),
    (
        ["智能穿搭", "今天穿", "心情", "生成穿搭"],
        ["upload_smart_outfit_reference", "generate_smart_outfit"],
        "smart_outfit",
    ),
    (["情绪", "心情", "难过", "开心"], ["list_mood_types", "recommend_by_mood"], "mood"),
    (["试衣", "试穿", "虚拟"], ["virtual_try_on"], "tryon"),
    (["收藏", "套装"], ["list_outfit_collections"], "collections"),
    (["健康", "服务"], ["health"], "health"),
]


class IntentRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="用户自然语言需求")


class IntentResponse(BaseModel):
    suggested_mcp_tools: List[str]
    intent_label: str
    notes: str


def route_intent_rules(query: str) -> IntentResponse:
    q = (query or "").strip().lower()
    if not q:
        return IntentResponse(
            suggested_mcp_tools=["health"],
            intent_label="empty",
            notes="empty query; default health check",
        )
    best_tools: List[str] = []
    best_label = "general"
    for keywords, tools, label in _INTENT_RULES:
        if any(k.lower() in q for k in keywords):
            best_tools = tools
            best_label = label
            break
    if not best_tools:
        best_tools = ["list_wardrobe", "recommend_outfits"]
        best_label = "general"
        notes = "no keyword hit; fallback wardrobe + outfit recommendation tools"
    else:
        notes = "matched keyword rule; Host should choose actual tools per runtime context"
    return IntentResponse(
        suggested_mcp_tools=best_tools,
        intent_label=best_label,
        notes=notes,
    )


@router.post("/intent", response_model=None)
async def post_intent(body: IntentRequest):
    """返回建议调用的 MCP 工具名列表（薄规则，非写死多步 Prompt）。"""
    out = route_intent_rules(body.query)
    return success_response(out.model_dump(), message="ok")
