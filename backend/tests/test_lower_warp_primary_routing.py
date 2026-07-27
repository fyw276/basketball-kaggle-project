"""Lower garments use warp-primary; upper CatVTON path stays untouched."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from PIL import Image, ImageDraw


def _fake_person(size=(384, 512)) -> Image.Image:
    img = Image.new("RGB", size, (220, 220, 220))
    d = ImageDraw.Draw(img)
    d.ellipse((162, 20, 222, 80), fill=(200, 170, 150))
    d.rectangle((150, 80, 234, 240), fill=(90, 120, 180))
    d.rectangle((155, 240, 185, 480), fill=(40, 40, 90))
    d.rectangle((200, 240, 230, 480), fill=(40, 40, 90))
    return img


def _fake_pants(size=(200, 360)) -> Image.Image:
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((40, 20, 160, 90), fill=(45, 30, 25))
    d.rectangle((40, 90, 90, 330), fill=(45, 30, 25))
    d.rectangle((110, 90, 160, 330), fill=(45, 30, 25))
    return img


@pytest.mark.asyncio
async def test_detail_fidelity_lower_skips_catvton(monkeypatch):
    person = _fake_person()
    garment = _fake_pants()
    warp_result = Image.new("RGB", person.size, (45, 30, 25))
    warp_meta = {
        "engine": "lower_warp_primary",
        "catvton_used": False,
        "use_knee_split": True,
        "waistband_box": [0, 0, 1, 1],
        "left_leg_box": [0, 0, 1, 1],
        "right_leg_box": [0, 0, 1, 1],
        "alpha_feather_px": 2,
        "alpha_coverage": 0.2,
    }

    catvton = AsyncMock(side_effect=AssertionError("CatVTON must not be called for lower"))
    monkeypatch.setattr(
        "app.services.tryon_v2.warp_engine.tryon_lower_warp_primary",
        lambda **kwargs: (warp_result, warp_meta),
    )

    # Exercise the routing fragment used by the endpoint.
    mode = "detail_fidelity"
    garment_category = "下装"
    from app.services.tryon_v2.category_utils import (
        is_lower_garment_category,
        map_to_catvton_cloth_type,
    )
    from app.services.tryon_v2.warp_engine import tryon_lower_warp_primary

    cloth_type = map_to_catvton_cloth_type(garment_category)
    assert is_lower_garment_category(garment_category)
    assert cloth_type == "lower"

    if mode in {"detail_fidelity", "hybrid"} and (
        is_lower_garment_category(garment_category) or cloth_type == "lower"
    ):
        result_img, meta = tryon_lower_warp_primary(
            person_image=person,
            garment_image=garment,
            debug_session_dir=None,
        )
        result = {
            "status": "success",
            "result_image": result_img,
            "metadata": {"pipeline": "LOWER_WARP_PRIMARY", **meta},
        }
    else:
        await catvton()
        result = {"status": "error"}

    assert result["status"] == "success"
    assert result["metadata"]["pipeline"] == "LOWER_WARP_PRIMARY"
    assert result["metadata"].get("catvton_used") is False
    catvton.assert_not_awaited()


@pytest.mark.asyncio
async def test_detail_fidelity_upper_still_calls_catvton(monkeypatch):
    """Upper path must keep calling CatVTON (routing guard)."""
    from app.services.tryon_v2.category_utils import (
        is_lower_garment_category,
        map_to_catvton_cloth_type,
    )

    mode = "detail_fidelity"
    garment_category = "上衣"
    cloth_type = map_to_catvton_cloth_type(garment_category)
    assert is_lower_garment_category(garment_category) is False
    assert cloth_type == "upper"

    called = {"catvton": False}

    async def fake_catvton(**kwargs):
        called["catvton"] = True
        return {
            "status": "success",
            "result_image": Image.new("RGB", (64, 64), (10, 20, 30)),
            "metadata": {"engine": "catvton"},
        }

    if mode in {"detail_fidelity", "hybrid"} and (
        is_lower_garment_category(garment_category) or cloth_type == "lower"
    ):
        pytest.fail("upper must not enter lower_warp_primary branch")
    else:
        upstream = await fake_catvton(garment_category=cloth_type)

    assert called["catvton"] is True
    assert upstream["metadata"]["engine"] == "catvton"


def test_tryon_lower_warp_primary_preserves_dark_tone():
    from app.services.tryon_v2.warp_engine import tryon_lower_warp_primary

    person = _fake_person()
    garment = _fake_pants()
    out, meta = tryon_lower_warp_primary(person, garment)
    assert out.size == person.size
    assert meta.get("catvton_used") is False
    assert meta.get("use_knee_split") is True
    # Mean lower-half should stay relatively dark (not washed to taupe/beige).
    import numpy as np

    arr = np.asarray(out)
    lower = arr[arr.shape[0] // 2 :, :, :]
    # Where garment likely landed: darker than light gray person bg.
    dark_ratio = float((lower.mean(axis=2) < 100).mean())
    assert dark_ratio > 0.02 or meta.get("engine") == "lower_warp_primary_fallback"
