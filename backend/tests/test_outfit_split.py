"""Tests for outfit split planner."""

import io

from PIL import Image


def test_plan_outfit_split_safe_always_returns_items():
    from app.services.outfit_split import plan_outfit_split_safe

    img = Image.new("RGB", (400, 800), color=(120, 100, 90))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    b = buf.getvalue()
    plan = plan_outfit_split_safe(img, b)
    assert len(plan) >= 1
    for row in plan:
        assert len(row) == 3
        cat, box, conf = row
        assert isinstance(cat, str)
        assert len(box) == 4
        assert 0 <= conf <= 1.0


def test_coerce_valid_categories():
    from app.schemas.garment import VALID_CATEGORIES
    from app.services.outfit_split import plan_outfit_split_safe

    img = Image.new("RGB", (300, 600), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    plan = plan_outfit_split_safe(img, buf.getvalue())
    for cat, _, _ in plan:
        assert cat in VALID_CATEGORIES, cat
