"""Auto-category fallback tests for try-on preprocessing."""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from app.services.tryon_v2 import preprocess


def _make_pants_rgba() -> Image.Image:
    rgba = Image.new("RGBA", (300, 620), (255, 255, 255, 0))
    px = rgba.load()
    for y in range(30, 135):
        for x in range(82, 218):
            px[x, y] = (100, 145, 185, 255)
    for y in range(135, 575):
        for x in range(70, 142):
            px[x, y] = (95, 140, 180, 255)
        for x in range(158, 230):
            px[x, y] = (95, 140, 180, 255)
    return rgba


def test_low_confidence_unknown_tall_garment_falls_back_to_bottom(monkeypatch):
    """Tall product images should not stay auto/unknown when the classifier is unsure."""

    garment = Image.new("RGB", (300, 900), (255, 255, 255))
    rgba = Image.new("RGBA", (120, 420), (20, 30, 45, 255))

    monkeypatch.setattr(
        preprocess,
        "cutout_garment_rgba",
        lambda image, cloth_type="upper": SimpleNamespace(rgba=rgba, cropped=rgba),
    )
    monkeypatch.setattr(preprocess, "align_garment", lambda image, **_: image)
    monkeypatch.setattr(preprocess, "_recognize_category", lambda _: ("上衣", 0.09))

    result = preprocess.preprocess_garment_image(garment)

    assert result.metadata["cloth_type_used"] == "lower"
    assert result.tryon_category == "bottom"


def test_high_confidence_accessory_pants_silhouette_forces_bottom(monkeypatch):
    """Jeans misclassified as shoes should still route through lower-body CatVTON."""

    garment = Image.new("RGB", (768, 768), (255, 255, 255))
    rgba = _make_pants_rgba()

    monkeypatch.setattr(
        preprocess,
        "cutout_garment_rgba",
        lambda image, cloth_type="upper": SimpleNamespace(rgba=rgba, cropped=rgba),
    )
    monkeypatch.setattr(preprocess, "align_garment", lambda image, **_: image)
    monkeypatch.setattr(preprocess, "_recognize_category", lambda _: ("鞋", 0.48))

    result = preprocess.preprocess_garment_image(garment)

    assert result.metadata["pants_shape"] is True
    assert result.metadata["cloth_type_used"] == "lower"
    assert result.tryon_category == "bottom"


def test_pants_shape_detector_requires_split_legs():
    """Tall single-piece garments should not be treated as pants solely by aspect."""

    dress = Image.new("RGBA", (260, 620), (255, 255, 255, 0))
    px = dress.load()
    for y in range(30, 575):
        for x in range(85, 178):
            px[x, y] = (80, 80, 120, 255)

    assert preprocess._looks_like_pants_shape(_make_pants_rgba()) is True
    assert preprocess._looks_like_pants_shape(dress) is False
