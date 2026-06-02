from uuid import uuid4

from app.models.garment import Garment
from app.schemas.garment import ColorSchema
from app.services import smart_outfit_generator as sog
from app.services.outfit_recommender_3d import OutfitRecommender3D


def _color(name="白"):
    return {
        "name": name,
        "rgb": [240, 240, 240],
        "hsv": [0.0, 0.0, 94.0],
        "hex_code": "#f0f0f0",
        "confidence": 0.8,
    }


def _garment(category, color="白", styles=None):
    return Garment(
        garment_id=uuid4(),
        user_id=uuid4(),
        category=category,
        main_color=_color(color),
        secondary_colors=[],
        style_tags=styles or ["休闲"],
        fit_type="标准",
        image_path="",
        image_url=f"/uploads/test/{category}.jpg",
        feature_vector=[0.1] * 1280,
    )


def test_fixed_reference_pants_never_recommends_skirt():
    recommender = OutfitRecommender3D()
    target = _garment("裤子", "粉", ["休闲"])
    wardrobe = [
        _garment("上衣", "白", ["休闲"]),
        _garment("裙子", "白", ["休闲"]),
        _garment("外套", "白", ["休闲"]),
    ]

    cards = recommender.recommend_outfits(
        target_garment=target,
        wardrobe=wardrobe,
        num_outfits=3,
        preferred_scene="度假旅行",
        fixed_reference_category="裤子",
    )

    assert cards
    for card in cards:
        categories = {item.category for item in card.items}
        assert "裤子" in categories
        assert "裙子" not in categories


def test_reference_summary_low_confidence_does_not_trust_wrong_category(monkeypatch):
    monkeypatch.setattr(
        sog,
        "_recognize_reference_image_nonblocking",
        lambda _: {
            "category": "外套",
            "category_confidence": 0.18,
            "style_tags": ["休闲"],
            "fit_type": None,
            "feature_vector": [0.1] * 1280,
        },
    )

    class _FakeColorExtractor:
        def __init__(self, n_colors=3):
            pass

        def extract_colors(self, image_bytes):
            return [ColorSchema(**_color("白"))]

    monkeypatch.setattr(sog, "ColorExtractor", _FakeColorExtractor)

    out = sog.build_reference_recognition_summary(b"fake")

    assert out["recognized_category"] == "外套"
    assert out["category"] == "上衣"
    assert out["reference_low_confidence"] is True


def test_reference_summary_user_color_override(monkeypatch):
    monkeypatch.setattr(
        sog,
        "_recognize_reference_image_nonblocking",
        lambda _: {
            "category": "裤子",
            "category_confidence": 0.9,
            "style_tags": ["休闲"],
            "fit_type": None,
            "feature_vector": [0.1] * 1280,
        },
    )

    class _FakeColorExtractor:
        def __init__(self, n_colors=3):
            pass

        def extract_colors(self, image_bytes):
            return [ColorSchema(**_color("白"))]

    monkeypatch.setattr(sog, "ColorExtractor", _FakeColorExtractor)

    out = sog.build_reference_recognition_summary(
        b"fake",
        reference_category="裤子",
        reference_color_name="粉",
    )

    assert out["category"] == "裤子"
    assert out["category_source"] == "user"
    assert out["main_color"]["name"] == "粉"
    assert out["main_color"]["confidence"] == 1.0
