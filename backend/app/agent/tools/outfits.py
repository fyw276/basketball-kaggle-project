"""Outfit recommendation tool: recommend_outfits."""

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.tools.registry import register_tool


@register_tool(
    name="recommend_outfits",
    description="根据场景从用户衣橱中推荐搭配方案。可指定场景（通勤/约会/运动等）和推荐套数。如不指定garment_id则自动选择。",
    parameters_schema={
        "type": "object",
        "properties": {
            "garment_id": {
                "type": "string",
                "description": "基于哪件衣物推荐（可选，不填则自动选择）",
            },
            "scene": {"type": "string", "description": "场景标签，如：通勤/约会/运动/休闲"},
            "num_outfits": {"type": "integer", "description": "推荐套数，1-5", "default": 3},
        },
    },
    mcp_name="recommend_outfits",
    category="outfits",
)
async def recommend_outfits(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.models.user_profile import UserProfile
    from app.services.garment import get_garment_by_id, get_garments_by_user
    from app.services.outfit_recommender_3d import OutfitRecommender3D

    scene = kw.get("scene", "")
    num_outfits = min(5, max(1, int(kw.get("num_outfits", 3))))
    garment_id = kw.get("garment_id")
    uid = UUID(user_id)

    wardrobe = get_garments_by_user(db, uid, limit=200)
    if not wardrobe:
        return {"error": "Wardrobe is empty, cannot recommend outfits."}

    if garment_id:
        target = get_garment_by_id(db, UUID(garment_id))
        if not target:
            return {"error": f"Garment {garment_id} not found"}
    else:
        target = wardrobe[0]

    profile = db.query(UserProfile).filter(UserProfile.user_id == uid).first()

    recommender = OutfitRecommender3D()
    results = recommender.recommend_outfits(
        target_garment=target,
        wardrobe=wardrobe,
        num_outfits=num_outfits,
        user_style_preferences=getattr(profile, "style_preference", None) if profile else None,
        user_body_type=getattr(profile, "body_type", None) if profile else None,
        avoid_body_parts=getattr(profile, "avoid_body_parts", None) if profile else None,
        preferred_scene=scene or None,
        user_gender=getattr(profile, "gender", None) if profile else None,
    )
    outfits = []
    for card in results:
        items = []
        for item in card.get("items", []):
            items.append(
                {
                    "garment_id": str(item.get("garment_id", "")),
                    "category": item.get("category", ""),
                    "role": item.get("role", ""),
                    "name": item.get("name", ""),
                }
            )
        outfits.append(
            {
                "items": items,
                "scene": card.get("scene", ""),
                "score": card.get("overall_score", 0),
                "reason": card.get("reason", ""),
            }
        )
    return {"outfits": outfits, "scene_filter": scene}
