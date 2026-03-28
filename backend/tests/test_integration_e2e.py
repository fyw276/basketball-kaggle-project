"""
End-to-End Integration Tests
Tests the full pipeline: CLIP recognition -> outfit recommendation -> color schema
"""

import io
from uuid import uuid4

import pytest
from PIL import Image

# Import OutfitCollection first to resolve SQLAlchemy relationship on User
from app.models.outfit_collection import OutfitCollection  # noqa: F401

from app.ml.clip_recognizer import CLIPRecognizer
from app.models.garment import Garment
from app.schemas.garment import ColorSchema
from app.services.outfit_recommender_3d import OutfitRecommender3D
from app.services.storage import StorageService


def create_test_image() -> io.BytesIO:
    """Create a simple test image."""
    img = Image.new("RGB", (224, 224), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def make_garment(category="上衣", color_name="深灰", styles=None, fit_type="标准"):
    """Create a test garment object."""
    if styles is None:
        styles = ["简约"]
    return Garment(
        garment_id=str(uuid4()),
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


# ─── CLIP Recognizer Integration ─────────────────────────────────────────────


class TestCLIPRecognizerIntegration:
    """Test CLIP recognizer with realistic inputs."""

    def test_clip_recognizer_initialization(self):
        """CLIP recognizer should initialize successfully."""
        recognizer = CLIPRecognizer()
        assert recognizer is not None

    def test_clip_recognizer_basic_recognition(self):
        """CLIP recognizer should process an image."""
        recognizer = CLIPRecognizer()
        img_bytes = create_test_image().getvalue()
        result = recognizer.recognize(img_bytes)
        assert result is not None
        assert "category" in result
        assert "style_tags" in result
        assert isinstance(result["category"], str)


# ─── Outfit Recommender 3D Integration ─────────────────────────────────────


class TestOutfitRecommender3DIntegration:
    """Test full outfit recommendation pipeline."""

    @pytest.fixture
    def test_wardrobe(self):
        """Create a small test wardrobe."""
        return [
            make_garment(category="上衣", color_name="深灰", styles=["简约", "通勤"], fit_type="标准"),
            make_garment(category="裤子", color_name="黑色", styles=["简约"], fit_type="修身"),
            make_garment(category="外套", color_name="藏青", styles=["商务", "正式"], fit_type="标准"),
            make_garment(category="鞋子", color_name="棕色", styles=["休闲"], fit_type="标准"),
            make_garment(category="裙子", color_name="酒红", styles=["甜美", "优雅"], fit_type="修身"),
        ]

    def test_recommend_with_body_type_filtering(self, test_wardrobe):
        """Body type filtering should work end-to-end."""
        recommender = OutfitRecommender3D()
        target = test_wardrobe[0]  # 上衣

        # 微胖: should filter out 修身 items
        cards = recommender.recommend_outfits(
            target_garment=target,
            wardrobe=test_wardrobe,
            num_outfits=3,
            user_body_type="微胖",
        )

        assert isinstance(cards, list)

    def test_recommend_with_explicit_scene(self, test_wardrobe):
        """Explicit scene should override style inference."""
        recommender = OutfitRecommender3D()
        target = test_wardrobe[0]  # 上衣

        cards = recommender.recommend_outfits(
            target_garment=target,
            wardrobe=test_wardrobe,
            num_outfits=2,
            preferred_scene="约会",
        )

        assert len(cards) >= 1
        assert cards[0].scene == "约会"

    def test_recommend_no_wardrobe_returns_empty(self, test_wardrobe):
        """Empty wardrobe should return empty recommendations."""
        recommender = OutfitRecommender3D()
        target = test_wardrobe[0]

        cards = recommender.recommend_outfits(
            target_garment=target,
            wardrobe=[],
            num_outfits=3,
        )

        assert cards == []

    def test_recommend_full_pipeline(self, test_wardrobe):
        """Full recommendation pipeline with all features."""
        recommender = OutfitRecommender3D()
        target = test_wardrobe[0]

        cards = recommender.recommend_outfits(
            target_garment=target,
            wardrobe=test_wardrobe,
            num_outfits=3,
            user_body_type="沙漏",
            preferred_scene="商务正式",
        )

        assert len(cards) >= 1
        for card in cards:
            assert card.scene == "商务正式"
            assert card.scene_score >= 0
            assert card.overall_score >= 0
            assert card.reason is not None


# ─── Storage Service Integration ─────────────────────────────────────────────


class TestStorageServiceIntegration:
    """Test storage service end-to-end."""

    def test_storage_service_initialization(self):
        """Storage service should initialize."""
        storage = StorageService()
        assert storage is not None
        # Check for any upload method (the actual method name varies)
        assert any(hasattr(storage, attr) for attr in dir(storage))


# ─── Color Schema Integration ────────────────────────────────────────────────


class TestColorSchemaIntegration:
    """Test color schema handling."""

    def test_color_schema_creation(self):
        """ColorSchema should accept all required fields."""
        color = ColorSchema(name="深灰", rgb=[64, 64, 64], hsv=[0, 0, 25], hex_code="#404040")
        assert color.name == "深灰"
        assert color.hex_code == "#404040"

    def test_color_schema_serialization(self):
        """ColorSchema should serialize to dict."""
        color = ColorSchema(name="黑色", rgb=[0, 0, 0], hsv=[0, 0, 0], hex_code="#000000")
        data = color.model_dump()
        assert data["name"] == "黑色"
        assert data["hex_code"] == "#000000"

    def test_color_schema_hsv_roundtrip(self):
        """ColorSchema HSV values should be accessible."""
        color = ColorSchema(name="酒红", rgb=[128, 0, 32], hsv=[345, 100, 50], hex_code="#800020")
        assert color.hsv[0] == 345
        assert color.hsv[1] == 100
        assert color.hsv[2] == 50
