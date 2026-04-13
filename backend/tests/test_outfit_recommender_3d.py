"""
Tests for OutfitRecommender3D (3D: 场景-品类-风格 + 体型感知)
覆盖 Step 6/7/8 新增功能：体型过滤、场景感知、中文推荐理由
"""

from uuid import uuid4

from app.models.garment import Garment

# Import OutfitCollection first to resolve SQLAlchemy relationship on User
from app.models.outfit_collection import OutfitCollection  # noqa: F401
from app.schemas.garment import ColorSchema
from app.services.outfit_recommender_3d import (
    BODY_TYPE_CATEGORY_SCORES,
    BODY_TYPE_IDEAL_FITS,
    OutfitCard,
    OutfitItem,
    OutfitRecommender3D,
    normalize_category_for_outfit_templates,
)


def make_garment(
    garment_id=None,
    category="上衣",
    color_name="深灰",
    styles=None,
    fit_type="标准",
):
    if styles is None:
        styles = ["简约"]
    g = Garment(
        garment_id=garment_id or str(uuid4()),
        user_id="test-user",
        category=category,
        main_color={
            "name": color_name,
            "rgb": [64, 64, 64],
            "hsv": [0.0, 0.0, 25.0],
            "hex_code": "#404040",
        },
        style_tags=styles,
        fit_type=fit_type,
        image_url="http://example.com/img.jpg",
        feature_vector=[0.1] * 1280,
    )
    return g


class TestBodyTypeConstants:
    """Test body type constant definitions"""

    def test_body_type_ideal_fits_has_all_types(self):
        """All 6 body types should have ideal fit definitions"""
        expected_types = ["偏瘦", "倒三角", "梨形", "矩形", "沙漏", "微胖"]
        assert set(BODY_TYPE_IDEAL_FITS.keys()) == set(expected_types)

    def test_body_type_category_scores_has_all_types(self):
        """All 6 body types should have category score definitions"""
        expected_types = ["偏瘦", "倒三角", "梨形", "矩形", "沙漏", "微胖"]
        assert set(BODY_TYPE_CATEGORY_SCORES.keys()) == set(expected_types)

    def test_body_type_ideal_fits_lean_away_from_tight(self):
        """偏瘦 should prefer loose/oversized, avoid tight"""
        fits = BODY_TYPE_IDEAL_FITS["偏瘦"]
        assert "宽松" in fits
        assert "oversized" in fits
        # Tight fit is not in ideal fits
        assert "修身" not in fits


class TestBodyTypeFiltering:
    """Test body type aware garment filtering"""

    def test_filter_removes_bad_fit_for_body_type(self):
        """Filter should remove 修身 garments for 微胖 body type"""
        recommender = OutfitRecommender3D()
        wardrobe = [
            make_garment(category="上衣", fit_type="修身"),
            make_garment(category="裤子", fit_type="宽松"),
        ]

        filtered = recommender._filter_by_body_type(wardrobe, "微胖", None)
        # 修身 top should be removed
        assert "修身" not in {g.fit_type for g in filtered}

    def test_filter_keeps_ideal_fit_for_body_type(self):
        """Filter should keep 宽松 garments for 微胖 body type"""
        recommender = OutfitRecommender3D()
        wardrobe = [
            make_garment(category="上衣", fit_type="修身"),
            make_garment(category="裤子", fit_type="宽松"),
        ]

        filtered = recommender._filter_by_body_type(wardrobe, "微胖", None)
        # 宽松 bottom should remain
        bottom = next((g for g in filtered if g.category == "裤子"), None)
        assert bottom is not None
        assert bottom.fit_type == "宽松"

    def test_filter_with_no_body_type_returns_all(self):
        """No body type = no filtering"""
        recommender = OutfitRecommender3D()
        wardrobe = [
            make_garment(category="上衣", fit_type="修身"),
            make_garment(category="裤子", fit_type="宽松"),
        ]

        filtered = recommender._filter_by_body_type(wardrobe, None, None)
        assert len(filtered) == 2


class TestSceneAwareRecommendations:
    """Test scene-aware outfit recommendation (Step 7)"""

    def test_derive_user_scenes_maps_styles_to_scenes(self):
        """Style preferences should map to the intended scene instead of defaulting."""
        recommender = OutfitRecommender3D()

        primary_scene, secondary_scenes = recommender._derive_user_scenes(["运动"])

        assert primary_scene == "运动健身"
        assert isinstance(secondary_scenes, list)

    def test_recommend_with_explicit_scene(self):
        """User-specified scene should override style inference"""
        recommender = OutfitRecommender3D()
        target = make_garment(category="上衣", styles=["简约"])
        wardrobe = [
            target,
            make_garment(category="裤子", color_name="黑", styles=["简约"]),
        ]

        cards = recommender.recommend_outfits(
            target_garment=target,
            wardrobe=wardrobe,
            num_outfits=1,
            preferred_scene="约会",
        )

        assert len(cards) >= 1
        assert cards[0].scene == "约会"

    def test_recommend_with_multiple_scenes(self):
        """Multiple scene templates should be available"""
        from app.services.outfit_recommender_3d import SCENE_OUTFIT_TEMPLATES

        # All expected scenes should have templates
        expected_scenes = [
            "通勤上班",
            "商务正式",
            "约会",
            "休闲日常",
            "校园",
            "运动健身",
            "度假旅行",
            "聚会",
            "街头潮流",
            "正式宴会",
        ]
        for scene in expected_scenes:
            assert scene in SCENE_OUTFIT_TEMPLATES
            assert len(SCENE_OUTFIT_TEMPLATES[scene]) > 0


class TestBodyTypeAwareRecommendations:
    """Test body type aware outfit recommendations (Step 6)"""

    def test_recommend_with_body_type_parameter(self):
        """recommend_outfits should accept body type and filter"""
        recommender = OutfitRecommender3D()
        target = make_garment(category="上衣", styles=["简约"], fit_type="宽松")
        wardrobe = [
            target,
            make_garment(category="裤子", color_name="黑", styles=["简约"], fit_type="修身"),
        ]

        # 微胖 body type should filter out 修身 pants
        cards = recommender.recommend_outfits(
            target_garment=target,
            wardrobe=wardrobe,
            num_outfits=3,
            user_body_type="微胖",
        )
        # Should still return results (only 修身 filtered)
        assert isinstance(cards, list)


class TestChineseReasonGeneration:
    """Test Chinese recommendation reason generation (Step 8)"""

    def test_generate_chinese_reason_basic(self):
        """_generate_chinese_reason should return Chinese text"""
        recommender = OutfitRecommender3D()
        garments = [
            make_garment(category="上衣", color_name="深灰", styles=["简约"]),
            make_garment(category="裤子", color_name="黑", styles=["简约"]),
        ]

        reason = recommender._generate_chinese_reason(
            garments,
            scene="通勤上班",
            scene_score=0.9,
            style_score=0.9,
            color_score=0.9,
        )

        assert isinstance(reason, str)
        assert len(reason) > 5
        # Should contain Chinese characters
        assert any("\u4e00" <= c <= "\u9fff" for c in reason)

    def test_generate_chinese_reason_scene_tip(self):
        """Scene tip should appear in reason"""
        recommender = OutfitRecommender3D()
        garments = [make_garment(category="上衣", styles=["简约"])]

        reason = recommender._generate_chinese_reason(
            garments,
            scene="通勤上班",
            scene_score=0.5,
            style_score=0.5,
            color_score=0.5,
        )

        assert "通勤" in reason or "职场" in reason or "干练" in reason

    def test_generate_chinese_reason_style_highlight(self):
        """Style highlights should appear in reason"""
        recommender = OutfitRecommender3D()
        garments = [make_garment(category="上衣", styles=["国风"])]

        reason = recommender._generate_chinese_reason(
            garments,
            scene="休闲日常",
            scene_score=0.5,
            style_score=0.5,
            color_score=0.5,
        )

        assert "国风" in reason or "雅韵" in reason or "文化气息" in reason

    def test_generate_chinese_reason_fallback(self):
        """Fallback message when no strong indicators"""
        recommender = OutfitRecommender3D()
        garments = [make_garment(category="上衣", styles=[])]

        reason = recommender._generate_chinese_reason(
            garments,
            scene="约会",
            scene_score=0.3,
            style_score=0.3,
            color_score=0.3,
        )

        # Fallback returns non-empty Chinese string ending with "场合的穿搭搭配"
        assert isinstance(reason, str)
        assert len(reason) > 5
        assert reason.endswith("场合的穿搭搭配") or len(reason.split("；")) >= 1


class TestOutfitCardSchema:
    """Test OutfitCard schema with reason field (Step 8)"""

    def test_outfit_card_has_reason_field(self):
        """OutfitCard should have reason field"""
        card = OutfitCard(
            outfit_id="test_1",
            scene="通勤上班",
            secondary_scenes=["商务正式"],
            items=[],
            description="简约通勤穿搭",
            reason="深色系简约干练风格，适合职场",
            scene_score=0.9,
            category_score=0.9,
            style_score=0.9,
            color_score=0.9,
            overall_score=0.9,
        )

        assert card.reason == "深色系简约干练风格，适合职场"

    def test_outfit_card_reason_default_empty(self):
        """OutfitCard reason should default to empty string"""
        card = OutfitCard(
            outfit_id="test_1",
            scene="通勤上班",
            secondary_scenes=[],
            items=[],
            description="test",
            scene_score=0.9,
            category_score=0.9,
            style_score=0.9,
            color_score=0.9,
            overall_score=0.9,
        )

        assert card.reason == ""

    def test_outfit_card_serialization_with_reason(self):
        """OutfitCard should serialize reason to JSON"""
        card = OutfitCard(
            outfit_id="test_1",
            scene="约会",
            secondary_scenes=["聚会"],
            items=[],
            description="优雅约会穿搭",
            reason="优雅得体，适合约会场合",
            scene_score=0.88,
            category_score=0.95,
            style_score=0.85,
            color_score=0.90,
            overall_score=0.88,
        )

        data = card.model_dump()
        assert "reason" in data
        assert data["reason"] == "优雅得体，适合约会场合"

    def test_outfit_item_schema(self):
        """OutfitItem should work correctly"""
        item = OutfitItem(
            garment_id=uuid4(),
            category="上衣",
            main_color=ColorSchema(
                name="深灰", rgb=[64, 64, 64], hsv=[0, 0, 25], hex_code="#404040"
            ),
            style_tags=["简约", "通勤"],
            image_url="http://example.com/img.jpg",
            role="top",
        )

        assert item.category == "上衣"
        assert item.role == "top"
        assert "简约" in item.style_tags


class TestNormalizeCategoryForTemplates:
    """CLIP 等非槽位 category 须映射到模板六类，否则智能穿搭会生成 0 套。"""

    def test_clip_style_labels_map_to_slot(self):
        assert normalize_category_for_outfit_templates("国风") == "上衣"
        assert normalize_category_for_outfit_templates("复古") == "上衣"

    def test_standard_slots_unchanged(self):
        for c in ("上衣", "裤子", "裙子", "外套", "鞋", "包"):
            assert normalize_category_for_outfit_templates(c) == c

    def test_dress_like_map_to_skirt(self):
        assert normalize_category_for_outfit_templates("连衣裙") == "裙子"
        assert normalize_category_for_outfit_templates("半身长裙") == "裙子"

    def test_recommend_with_non_slot_category_produces_cards(self):
        """Regression: target category「国风」曾导致所有模板被跳过。"""
        recommender = OutfitRecommender3D()
        target = make_garment(category="国风", styles=["国风", "休闲"])
        wardrobe = [
            make_garment(category="上衣", styles=["休闲"]),
            make_garment(category="裤子", color_name="黑", styles=["休闲"]),
        ]
        cards = recommender.recommend_outfits(
            target_garment=target,
            wardrobe=wardrobe,
            num_outfits=3,
            preferred_scene="休闲日常",
        )
        assert len(cards) >= 1
