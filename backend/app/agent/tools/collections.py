"""Outfit collection tool: list_collections."""

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.tools.registry import register_tool


@register_tool(
    name="list_collections",
    description="查看用户的套装收藏列表。",
    parameters_schema={
        "type": "object",
        "properties": {
            "page": {"type": "integer", "description": "页码", "default": 1},
            "page_size": {"type": "integer", "description": "每页数量", "default": 10},
        },
    },
    mcp_name="list_outfit_collections",
    category="collections",
)
async def list_collections(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.services.outfit_collection import get_collections_by_user

    page = max(1, int(kw.get("page", 1)))
    page_size = min(20, max(1, int(kw.get("page_size", 10))))
    uid = UUID(user_id)

    items, total = get_collections_by_user(db, uid, skip=(page - 1) * page_size, limit=page_size)
    collections = []
    for c in items:
        collections.append(
            {
                "collection_id": str(c.collection_id),
                "name": c.name,
                "scene": c.scene,
                "description": c.description or "",
                "worn_times": c.worn_times or "0",
                "created_at": c.created_at.isoformat(),
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": collections}
