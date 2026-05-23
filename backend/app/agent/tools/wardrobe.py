"""Wardrobe tools: list_wardrobe, search_wardrobe."""

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.tools.registry import register_tool


@register_tool(
    name="list_wardrobe",
    description="查看用户的衣橱列表，支持分页和品类过滤。返回衣物名称、颜色、风格标签等信息。",
    parameters_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "品类过滤：上衣/裤子/裙子/外套/鞋/包"},
            "page": {"type": "integer", "description": "页码，从1开始", "default": 1},
            "page_size": {"type": "integer", "description": "每页数量，最大20", "default": 10},
        },
    },
    mcp_name="list_wardrobe",
    category="wardrobe",
)
async def list_wardrobe(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.services.garment import count_garments_by_user, get_garments_by_user

    page = max(1, int(kw.get("page", 1)))
    page_size = min(20, max(1, int(kw.get("page_size", 10))))
    category = kw.get("category")
    uid = UUID(user_id)
    total = count_garments_by_user(db, uid, category=category)
    garments = get_garments_by_user(
        db, uid, skip=(page - 1) * page_size, limit=page_size, category=category
    )
    items = []
    for g in garments:
        items.append(
            {
                "garment_id": str(g.garment_id),
                "name": g.name or "",
                "category": g.category,
                "main_color": g.main_color,
                "style_tags": g.style_tags or [],
                "fit_type": g.fit_type or "",
                "image_url": g.image_url,
                "notes": g.notes or "",
                "wear_count": g.wearing_count or "0",
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@register_tool(
    name="search_wardrobe",
    description="按关键词、品类、风格标签、颜色搜索衣橱单品。",
    parameters_schema={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "关键词（匹配名称/备注）"},
            "category": {"type": "string", "description": "品类：上衣/裤子/裙子/外套/鞋/包"},
            "style_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "风格标签列表",
            },
            "color_name": {"type": "string", "description": "主颜色名称，如：蓝/红/黑"},
        },
    },
    mcp_name=None,
    category="wardrobe",
)
async def search_wardrobe(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.schemas.garment import GarmentSearchQuery
    from app.services.garment import search_garments

    query = GarmentSearchQuery(
        keyword=kw.get("keyword"),
        category=kw.get("category"),
        style_tags=kw.get("style_tags"),
        color_name=kw.get("color_name"),
    )
    garments, total = search_garments(db, UUID(user_id), query)
    items = []
    for g in garments[:20]:
        items.append(
            {
                "garment_id": str(g.garment_id),
                "name": g.name or "",
                "category": g.category,
                "main_color": g.main_color,
                "style_tags": g.style_tags or [],
                "fit_type": g.fit_type or "",
                "image_url": g.image_url,
            }
        )
    return {"total": total, "items": items}
