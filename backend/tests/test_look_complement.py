from types import SimpleNamespace
from uuid import uuid4

from app.services.look_complement import LookComplementService


def _part_result(role):
    return {"part_role": role, "matched_garments": []}


def _garment(category):
    return SimpleNamespace(
        garment_id=uuid4(),
        name=f"{category} item",
        category=category,
        image_url="/uploads/item.jpg",
        style_tags=[],
        main_color={"name": "black"},
    )


def test_infer_missing_categories_for_top_bottom_only():
    missing = LookComplementService().infer_missing_categories(
        [_part_result("top"), _part_result("bottom")]
    )

    assert missing == ["shoes"]


def test_recommend_missing_items_returns_shoes_for_commute():
    service = LookComplementService()
    recommendations = service.recommend_missing_items(
        [_part_result("top"), _part_result("bottom")],
        [_garment("shoes")],
        scene_hint="commute",
    )

    assert recommendations
    assert recommendations[0]["part_role"] == "shoes"


def test_recommend_missing_items_returns_bag_for_formal_scene():
    service = LookComplementService()
    recommendations = service.recommend_missing_items(
        [_part_result("top"), _part_result("bottom"), _part_result("shoes")],
        [_garment("bag")],
        scene_hint="formal",
    )

    assert recommendations
    assert recommendations[0]["part_role"] == "bag"


def test_empty_parts_returns_empty_recommendations():
    assert LookComplementService().recommend_missing_items([], [_garment("shoes")]) == []
