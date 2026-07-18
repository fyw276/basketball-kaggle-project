"""Tests for lower-garment category routing and high-quality mode upgrades."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from app.services.body_mask import create_lower_body_polygon_mask
from app.services.tryon_v2.category_utils import (
    is_lower_garment_category,
    map_to_catvton_cloth_type,
    prefer_high_quality_mode_for_lower,
)
from app.services.tryon_v2.catvton_engine_client import _catvton_category_hint
from app.services.tryon_v2.preprocess import _looks_like_pants_shape, evaluate_lower_garment_qc


def test_lower_keywords_map_to_catvton_lower():
    for cat in (
        "bottom",
        "lower",
        "pants",
        "jeans",
        "trousers",
        "shorts",
        "下装",
        "裤子",
        "长裤",
        "短裤",
        "牛仔裤",
    ):
        assert is_lower_garment_category(cat) is True
        assert map_to_catvton_cloth_type(cat) == "lower"
        assert _catvton_category_hint(cat) == "lower"


def test_top_keywords_stay_upper():
    for cat in ("top", "upper", "上装", "上衣", "T恤"):
        assert is_lower_garment_category(cat) is False
        assert map_to_catvton_cloth_type(cat) == "upper"


def test_prefer_high_quality_mode_for_lower_upgrades_warp_modes():
    assert prefer_high_quality_mode_for_lower("bottom", "stable_fast") == "detail_fidelity"
    assert prefer_high_quality_mode_for_lower("pants", "paste") == "detail_fidelity"
    assert prefer_high_quality_mode_for_lower("牛仔裤", "blend") == "detail_fidelity"
    assert prefer_high_quality_mode_for_lower("bottom", "hybrid") == "hybrid"
    assert prefer_high_quality_mode_for_lower("bottom", "detail_fidelity") == "detail_fidelity"
    # Tops must not be upgraded.
    assert prefer_high_quality_mode_for_lower("top", "stable_fast") == "stable_fast"


def test_pants_shape_and_qc_on_synthetic_pants():
    img = Image.new("RGBA", (200, 360), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    # Waist + two legs with a crotch gap.
    draw.rectangle((40, 20, 160, 90), fill=(40, 70, 140, 255))
    draw.rectangle((40, 90, 90, 330), fill=(40, 70, 140, 255))
    draw.rectangle((110, 90, 160, 330), fill=(40, 70, 140, 255))
    assert _looks_like_pants_shape(img) is True
    qc = evaluate_lower_garment_qc(img)
    assert qc["pants_shape"] is True
    assert "score" in qc


def test_lower_body_polygon_covers_legs_not_face():
    # Normalized keypoints for a standing person.
    kpts = {
        "left_hip": (0.42, 0.48),
        "right_hip": (0.58, 0.48),
        "left_knee": (0.43, 0.68),
        "right_knee": (0.57, 0.68),
        "left_ankle": (0.44, 0.90),
        "right_ankle": (0.56, 0.90),
    }
    mask = create_lower_body_polygon_mask(kpts, pw=100, ph=200, feather_radius=0)
    assert mask.shape == (200, 100)
    assert mask.dtype == np.uint8
    # Face / upper torso should stay mostly zero.
    assert float(mask[:60, :].mean()) < 5.0
    # Lower legs / crotch region should be filled.
    assert float(mask[100:180, 35:65].mean()) > 100.0


def test_lower_body_polygon_pads_outward_for_mediapipe_facing_camera():
    """MediaPipe person-left has larger image-x when facing camera; pad must go outward."""
    kpts = {
        "left_shoulder": (0.58, 0.30),
        "right_shoulder": (0.40, 0.30),
        "left_hip": (0.53, 0.54),
        "right_hip": (0.44, 0.54),
        "left_knee": (0.53, 0.71),
        "right_knee": (0.44, 0.71),
        "left_ankle": (0.53, 0.85),
        "right_ankle": (0.46, 0.85),
    }
    mask = create_lower_body_polygon_mask(kpts, pw=1236, ph=1498, feather_radius=0)
    ys, xs = np.where(mask > 127)
    assert xs.size > 0
    width = int(xs.max() - xs.min())
    # Must be wider than raw hip span (~110px); previously collapsed to ~100px center strip.
    assert width >= 280
    coverage = float((mask > 127).mean())
    assert coverage >= 0.07
    # Still must not paint the face band.
    assert float(mask[: int(1498 * 0.12), int(1236 * 0.25) : int(1236 * 0.75)].mean()) < 5.0
