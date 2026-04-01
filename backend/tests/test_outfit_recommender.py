"""
Tests for outfit recommendation module
Tests outfit generation, scoring, and recommendation logic
"""

from uuid import uuid4

from app.models.garment import Garment
from app.services.outfit_recommender import OutfitCard, OutfitRecommender
from app.services.outfit_rules import CategoryRules, ColorRules, StyleRules


class TestOutfitRecommenderInitialization:
    """Test outfit recommender initialization"""

    def test_initialization_default(self):
        """Test initialization with default rules"""
        recommender = OutfitRecommender()

        assert recommender is not None
        assert recommender.color_rules is not None
        assert recommender.style_rules is not None
        assert recommender.category_rules is not None

    def test_initialization_custom_rules(self):
        """Test initialization with custom rules"""
        color_rules = ColorRules()
        style_rules = StyleRules()
        category_rules = CategoryRules()

        recommender = OutfitRecommender(
            color_rules=color_rules, style_rules=style_rules, category_rules=category_rules
        )

        assert recommender.color_rules is color_rules
        assert recommender.style_rules is style_rules
        assert recommender.category_rules is category_rules


class TestOutfitGeneration:
    """Test outfit generation logic"""

    def create_test_garment(
        self, category: str, color_name: str, styles: list, garment_id=None
    ) -> Garment:
        """Helper to create test garment"""
        if garment_id is None:
            garment_id = uuid4()

        color_map = {
            "白": {"hex": "#ffffff", "rgb": (255, 255, 255), "hsv": (0, 0, 100)},
            "黑": {"hex": "#000000", "rgb": (0, 0, 0), "hsv": (0, 0, 0)},
            "蓝": {"hex": "#0000ff", "rgb": (0, 0, 255), "hsv": (240, 100, 100)},
            "红": {"hex": "#ff0000", "rgb": (255, 0, 0), "hsv": (0, 100, 100)},
            "灰": {"hex": "#808080", "rgb": (128, 128, 128), "hsv": (0, 0, 50)},
        }

        color_info = color_map.get(color_name, color_map["白"])

        return Garment(
            garment_id=garment_id,
            user_id=uuid4(),
            category=category,
            main_color={
                "name": color_name,
                "hex_code": color_info["hex"],
                "rgb": color_info["rgb"],
                "hsv": color_info["hsv"],
            },
            secondary_colors=[],
            style_tags=styles,
            fit_type="标准",
            image_path=f"/test/{garment_id}.jpg",
            image_url=f"/uploads/test/{garment_id}.jpg",
            feature_vector=[0.1] * 1280,
        )

    def test_recommend_outfits_basic(self):
        """Test basic outfit recommendation"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约", "通勤"])
        wardrobe = [
            self.create_test_garment("裤子", "黑", ["正式"]),
            self.create_test_garment("裤子", "蓝", ["休闲"]),
        ]

        outfits = recommender.recommend_outfits(target, wardrobe, num_outfits=2)

        assert len(outfits) > 0
        assert len(outfits) <= 2
        assert all(isinstance(outfit, OutfitCard) for outfit in outfits)

    def test_recommend_outfits_empty_wardrobe(self):
        """Test recommendation with empty wardrobe"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约"])
        wardrobe = []

        outfits = recommender.recommend_outfits(target, wardrobe, num_outfits=3)

        assert len(outfits) == 0

    def test_recommend_outfits_no_matching_categories(self):
        """Test recommendation when wardrobe lacks required categories"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约"])
        # Wardrobe only has shoes (not required for top)
        wardrobe = [self.create_test_garment("鞋", "黑", ["休闲"])]

        outfits = recommender.recommend_outfits(target, wardrobe, num_outfits=3)

        # Should return empty since no required categories available
        assert len(outfits) == 0

    def test_recommend_outfits_with_shoes(self):
        """Test recommendation includes shoes when available"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约"])
        wardrobe = [
            self.create_test_garment("裤子", "黑", ["正式"]),
            self.create_test_garment("鞋", "黑", ["正式"]),
        ]

        outfits = recommender.recommend_outfits(target, wardrobe, num_outfits=3)

        assert len(outfits) > 0
        # Some outfits should include shoes
        has_shoes = any(any(item.category == "鞋" for item in outfit.items) for outfit in outfits)
        assert has_shoes

    def test_recommend_outfits_num_outfits_parameter(self):
        """Test num_outfits parameter controls output count"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约"])
        wardrobe = [
            self.create_test_garment("裤子", "黑", ["正式"]),
            self.create_test_garment("裤子", "蓝", ["休闲"]),
            self.create_test_garment("裤子", "灰", ["通勤"]),
        ]

        outfits_1 = recommender.recommend_outfits(target, wardrobe, num_outfits=1)
        outfits_3 = recommender.recommend_outfits(target, wardrobe, num_outfits=3)

        assert len(outfits_1) == 1
        assert len(outfits_3) >= 1
        assert len(outfits_3) <= 3


class TestOutfitScoring:
    """Test outfit scoring logic"""

    def create_test_garment(self, category: str, color_name: str, styles: list) -> Garment:
        """Helper to create test garment"""
        color_map = {
            "白": {"hex": "#ffffff", "rgb": (255, 255, 255), "hsv": (0, 0, 100)},
            "黑": {"hex": "#000000", "rgb": (0, 0, 0), "hsv": (0, 0, 0)},
            "蓝": {"hex": "#0000ff", "rgb": (0, 0, 255), "hsv": (240, 100, 100)},
        }

        color_info = color_map.get(color_name, color_map["白"])

        return Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category=category,
            main_color={
                "name": color_name,
                "hex_code": color_info["hex"],
                "rgb": color_info["rgb"],
                "hsv": color_info["hsv"],
            },
            secondary_colors=[],
            style_tags=styles,
            fit_type="标准",
            image_path="/test/image.jpg",
            image_url="/uploads/test/image.jpg",
            feature_vector=[0.1] * 1280,
        )

    def test_score_outfit_basic(self):
        """Test basic outfit scoring"""
        recommender = OutfitRecommender()

        garments = [
            self.create_test_garment("上衣", "白", ["简约"]),
            self.create_test_garment("裤子", "黑", ["简约"]),
        ]

        score_info = recommender._score_outfit(garments)

        assert "color_harmony_score" in score_info
        assert "color_harmony_type" in score_info
        assert "style_consistency" in score_info
        assert "overall_score" in score_info

        assert 0.0 <= score_info["color_harmony_score"] <= 1.0
        assert 0.0 <= score_info["style_consistency"] <= 1.0
        assert 0.0 <= score_info["overall_score"] <= 1.0

    def test_score_outfit_high_harmony(self):
        """Test scoring outfit with high color harmony"""
        recommender = OutfitRecommender()

        # Neutral colors should have high harmony
        garments = [
            self.create_test_garment("上衣", "白", ["简约"]),
            self.create_test_garment("裤子", "黑", ["简约"]),
        ]

        score_info = recommender._score_outfit(garments)

        # Neutral colors should score high
        assert score_info["color_harmony_score"] >= 0.8

    def test_score_outfit_style_match(self):
        """Test scoring outfit with matching styles"""
        recommender = OutfitRecommender()

        # Same style tags
        garments = [
            self.create_test_garment("上衣", "白", ["简约", "通勤"]),
            self.create_test_garment("裤子", "黑", ["简约", "通勤"]),
        ]

        score_info = recommender._score_outfit(garments)

        # Perfect style match should score 1.0
        assert score_info["style_consistency"] == 1.0

    def test_score_outfit_single_garment(self):
        """Test scoring with single garment"""
        recommender = OutfitRecommender()

        garments = [self.create_test_garment("上衣", "白", ["简约"])]

        score_info = recommender._score_outfit(garments)

        # Should return neutral scores
        assert score_info["overall_score"] == 0.5

    def test_score_outfit_multiple_garments(self):
        """Test scoring with multiple garments"""
        recommender = OutfitRecommender()

        garments = [
            self.create_test_garment("上衣", "白", ["简约"]),
            self.create_test_garment("裤子", "黑", ["简约"]),
            self.create_test_garment("鞋", "黑", ["简约"]),
        ]

        score_info = recommender._score_outfit(garments)

        # Should calculate average scores across all pairs
        assert 0.0 <= score_info["overall_score"] <= 1.0


class TestOutfitCardGeneration:
    """Test outfit card generation"""

    def create_test_garment(self, category: str, color_name: str, styles: list) -> Garment:
        """Helper to create test garment"""
        return Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category=category,
            main_color={
                "name": color_name,
                "hex_code": "#ffffff",
                "rgb": (255, 255, 255),
                "hsv": (0, 0, 100),
            },
            secondary_colors=[],
            style_tags=styles,
            fit_type="标准",
            image_path="/test/image.jpg",
            image_url="/uploads/test/image.jpg",
            feature_vector=[0.1] * 1280,
        )

    def test_create_outfit_card(self):
        """Test creating outfit card"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约"])
        garments = [
            target,
            self.create_test_garment("裤子", "黑", ["简约"]),
        ]

        score_info = {
            "color_harmony_score": 0.9,
            "color_harmony_type": "中性色搭配",
            "style_consistency": 1.0,
            "overall_score": 0.95,
        }

        card = recommender._create_outfit_card(
            outfit_id="test_1", garments=garments, target_garment=target, score_info=score_info
        )

        assert isinstance(card, OutfitCard)
        assert card.outfit_id == "test_1"
        assert len(card.items) == 2
        assert card.color_harmony_score == 0.9
        assert card.style_consistency == 1.0
        assert card.overall_score == 0.95

    def test_outfit_card_has_target_role(self):
        """Test that outfit card identifies target garment"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约"])
        garments = [
            target,
            self.create_test_garment("裤子", "黑", ["简约"]),
        ]

        score_info = {
            "color_harmony_score": 0.9,
            "color_harmony_type": "中性色搭配",
            "style_consistency": 1.0,
            "overall_score": 0.95,
        }

        card = recommender._create_outfit_card(
            outfit_id="test_1", garments=garments, target_garment=target, score_info=score_info
        )

        # One item should have role "target"
        target_items = [item for item in card.items if item.role == "target"]
        assert len(target_items) == 1
        assert target_items[0].garment_id == target.garment_id

    def test_outfit_card_occasion(self):
        """Test outfit card occasion determination"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["正式"])
        garments = [
            target,
            self.create_test_garment("裤子", "黑", ["正式"]),
        ]

        score_info = {
            "color_harmony_score": 0.9,
            "color_harmony_type": "中性色搭配",
            "style_consistency": 1.0,
            "overall_score": 0.95,
        }

        card = recommender._create_outfit_card(
            outfit_id="test_1", garments=garments, target_garment=target, score_info=score_info
        )

        # Should map "正式" to appropriate occasion
        assert card.occasion in ["正式场合", "日常"]

    def test_outfit_card_description(self):
        """Test outfit card description generation"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣", "白", ["简约"])
        garments = [
            target,
            self.create_test_garment("裤子", "黑", ["简约"]),
        ]

        score_info = {
            "color_harmony_score": 0.9,
            "color_harmony_type": "中性色搭配",
            "style_consistency": 1.0,
            "overall_score": 0.95,
        }

        card = recommender._create_outfit_card(
            outfit_id="test_1", garments=garments, target_garment=target, score_info=score_info
        )

        # Description should be non-empty string
        assert isinstance(card.description, str)
        assert len(card.description) > 0


class TestOutfitRecommenderHelpers:
    """Test helper methods"""

    def create_test_garment(self, category: str) -> Garment:
        """Helper to create test garment"""
        return Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category=category,
            main_color={
                "name": "白",
                "hex_code": "#ffffff",
                "rgb": (255, 255, 255),
                "hsv": (0, 0, 100),
            },
            secondary_colors=[],
            style_tags=["简约"],
            fit_type="标准",
            image_path="/test/image.jpg",
            image_url="/uploads/test/image.jpg",
            feature_vector=[0.1] * 1280,
        )

    def test_group_by_category(self):
        """Test grouping wardrobe by category"""
        recommender = OutfitRecommender()

        wardrobe = [
            self.create_test_garment("上衣"),
            self.create_test_garment("上衣"),
            self.create_test_garment("裤子"),
            self.create_test_garment("鞋"),
        ]

        grouped = recommender._group_by_category(wardrobe)

        assert "上衣" in grouped
        assert "裤子" in grouped
        assert "鞋" in grouped
        assert len(grouped["上衣"]) == 2
        assert len(grouped["裤子"]) == 1
        assert len(grouped["鞋"]) == 1

    def test_determine_role(self):
        """Test determining garment role"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣")
        other = self.create_test_garment("裤子")

        role_target = recommender._determine_role(target, target)
        role_other = recommender._determine_role(other, target)

        assert role_target == "target"
        assert role_other == "bottom"

    def test_determine_occasion(self):
        """Test determining occasion from styles"""
        recommender = OutfitRecommender()

        garments = [
            Garment(
                garment_id=uuid4(),
                user_id=uuid4(),
                category="上衣",
                main_color={
                    "name": "白",
                    "hex_code": "#ffffff",
                    "rgb": (255, 255, 255),
                    "hsv": (0, 0, 100),
                },
                secondary_colors=[],
                style_tags=["正式", "通勤"],
                fit_type="标准",
                image_path="/test/image.jpg",
                image_url="/uploads/test/image.jpg",
                feature_vector=[0.1] * 1280,
            )
        ]

        occasion = recommender._determine_occasion(garments)

        # Should map to appropriate occasion
        assert isinstance(occasion, str)
        assert len(occasion) > 0

    def test_generate_description(self):
        """Test generating outfit description"""
        recommender = OutfitRecommender()

        garments = [
            Garment(
                garment_id=uuid4(),
                user_id=uuid4(),
                category="上衣",
                main_color={
                    "name": "白",
                    "hex_code": "#ffffff",
                    "rgb": (255, 255, 255),
                    "hsv": (0, 0, 100),
                },
                secondary_colors=[],
                style_tags=["简约"],
                fit_type="标准",
                image_path="/test/image.jpg",
                image_url="/uploads/test/image.jpg",
                feature_vector=[0.1] * 1280,
            ),
            Garment(
                garment_id=uuid4(),
                user_id=uuid4(),
                category="裤子",
                main_color={
                    "name": "黑",
                    "hex_code": "#000000",
                    "rgb": (0, 0, 0),
                    "hsv": (0, 0, 0),
                },
                secondary_colors=[],
                style_tags=["简约"],
                fit_type="标准",
                image_path="/test/image.jpg",
                image_url="/uploads/test/image.jpg",
                feature_vector=[0.1] * 1280,
            ),
        ]

        score_info = {
            "color_harmony_score": 0.9,
            "color_harmony_type": "中性色搭配",
            "style_consistency": 1.0,
            "overall_score": 0.95,
        }

        description = recommender._generate_description(garments, score_info)

        assert isinstance(description, str)
        assert len(description) > 0
        # Should mention colors and categories
        assert "白" in description or "黑" in description


class TestOutfitRecommenderEdgeCases:
    """Test edge cases and boundary conditions"""

    def create_test_garment(self, category: str) -> Garment:
        """Helper to create test garment"""
        return Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category=category,
            main_color={
                "name": "白",
                "hex_code": "#ffffff",
                "rgb": (255, 255, 255),
                "hsv": (0, 0, 100),
            },
            secondary_colors=[],
            style_tags=["简约"],
            fit_type="标准",
            image_path="/test/image.jpg",
            image_url="/uploads/test/image.jpg",
            feature_vector=[0.1] * 1280,
        )

    def test_recommend_with_large_wardrobe(self):
        """Test recommendation with large wardrobe"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣")
        # Create 50 pants
        wardrobe = [self.create_test_garment("裤子") for _ in range(50)]

        outfits = recommender.recommend_outfits(target, wardrobe, num_outfits=3)

        # Should still generate recommendations
        assert len(outfits) > 0
        assert len(outfits) <= 3

    def test_recommend_with_no_styles(self):
        """Test recommendation with garments having no style tags"""
        recommender = OutfitRecommender()

        target = Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category="上衣",
            main_color={
                "name": "白",
                "hex_code": "#ffffff",
                "rgb": (255, 255, 255),
                "hsv": (0, 0, 100),
            },
            secondary_colors=[],
            style_tags=[],  # No styles
            fit_type="标准",
            image_path="/test/image.jpg",
            image_url="/uploads/test/image.jpg",
            feature_vector=[0.1] * 1280,
        )

        wardrobe = [
            Garment(
                garment_id=uuid4(),
                user_id=uuid4(),
                category="裤子",
                main_color={
                    "name": "黑",
                    "hex_code": "#000000",
                    "rgb": (0, 0, 0),
                    "hsv": (0, 0, 0),
                },
                secondary_colors=[],
                style_tags=[],  # No styles
                fit_type="标准",
                image_path="/test/image.jpg",
                image_url="/uploads/test/image.jpg",
                feature_vector=[0.1] * 1280,
            )
        ]

        outfits = recommender.recommend_outfits(target, wardrobe, num_outfits=1)

        # Should still generate recommendations
        assert len(outfits) > 0

    def test_recommend_outfits_sorted_by_score(self):
        """Test that recommendations are sorted by score"""
        recommender = OutfitRecommender()

        target = self.create_test_garment("上衣")
        wardrobe = [self.create_test_garment("裤子") for _ in range(5)]

        outfits = recommender.recommend_outfits(target, wardrobe, num_outfits=5)

        # Check that outfits are sorted by overall_score (descending)
        if len(outfits) > 1:
            for i in range(len(outfits) - 1):
                assert outfits[i].overall_score >= outfits[i + 1].overall_score
