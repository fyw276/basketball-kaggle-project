from datetime import datetime
from uuid import uuid4

from app.schemas.garment import ColorSchema
from app.schemas.user_profile import UserProfileResponse
from app.services.suitability_scorer_3d import SuitabilityScorer3D


def _profile(style_preference=None):
    return UserProfileResponse(
        profile_id=uuid4(),
        user_id=uuid4(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        height=170,
        body_type="矩形",
        skin_tone="黄皮",
        style_preference=style_preference or ["正式", "简约"],
        budget_range="中等",
        avoid_body_parts=[],
    )


def _white():
    return ColorSchema(
        name="白色",
        rgb=(255, 255, 255),
        hsv=(0.0, 0.0, 1.0),
        hex_code="#ffffff",
        confidence=1.0,
    )


def test_new_chinese_style_participates_in_selected_scene_scoring():
    scorer = SuitabilityScorer3D()
    profile = _profile()

    formal = scorer.calculate_score(
        garment_color=_white(),
        secondary_colors=[],
        garment_fit="标准",
        garment_styles=["新中式"],
        garment_category="上衣",
        user_profile=profile,
        selected_scene="正式场合",
    )
    sport = scorer.calculate_score(
        garment_color=_white(),
        secondary_colors=[],
        garment_fit="标准",
        garment_styles=["新中式"],
        garment_category="上衣",
        user_profile=profile,
        selected_scene="运动健身",
    )

    assert formal.scene_score > sport.scene_score
    assert formal.suitability_score > sport.suitability_score
    assert "正式场合" in formal.explanation["scene"]
    assert "运动健身" in sport.explanation["scene"]


def test_body_and_style_explanations_include_selected_scene_context():
    scorer = SuitabilityScorer3D()
    profile = _profile(["简约", "正式"])

    formal = scorer.calculate_score(
        garment_color=_white(),
        secondary_colors=[],
        garment_fit="标准",
        garment_styles=["简约"],
        garment_category="上衣",
        user_profile=profile,
        selected_scene="正式场合",
    )
    leisure = scorer.calculate_score(
        garment_color=_white(),
        secondary_colors=[],
        garment_fit="标准",
        garment_styles=["简约"],
        garment_category="上衣",
        user_profile=profile,
        selected_scene="休闲娱乐",
    )

    assert formal.explanation["body"] != leisure.explanation["body"]
    assert formal.explanation["style"] != leisure.explanation["style"]
    assert "正式场合" in formal.explanation["body"]
    assert "休闲娱乐" in leisure.explanation["style"]
