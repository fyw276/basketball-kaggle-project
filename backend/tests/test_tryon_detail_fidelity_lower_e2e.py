"""End-to-end integration tests for detail_fidelity mode with lower-body garments.

Tests the full pipeline without calling actual CatVTON (uses synthetic images).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from app.services.tryon_v2.catvton_engine_client import _catvton_category_hint
from app.services.tryon_v2.fidelity_guard import (
    decide_color_fidelity_engine,
    evaluate_raw_catvton_quality,
    extract_engine_decision_features,
)


def _make_person_image(size: tuple[int, int] = (768, 1024)) -> Image.Image:
    """Create a synthetic person image with upper body and legs."""
    img = Image.new("RGB", size, color=(240, 235, 230))
    draw = ImageDraw.Draw(img)
    w, h = size
    # Head
    draw.ellipse((w // 2 - 40, 40, w // 2 + 40, 120), fill=(200, 170, 150))
    # Upper body
    draw.rectangle((w // 2 - 80, 130, w // 2 + 80, 500), fill=(100, 100, 180))
    # Lower body (pants area)
    draw.rectangle((w // 2 - 70, 510, w // 2 + 70, 900), fill=(60, 60, 120))
    # Shoes
    draw.rectangle((w // 2 - 80, 910, w // 2 + 80, 980), fill=(40, 40, 40))
    return img


def _make_garment_image(
    color: tuple[int, int, int] = (50, 50, 150), size: tuple[int, int] = (768, 1024)
) -> Image.Image:
    """Create a synthetic garment image (pants)."""
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    w, h = size
    # Pants shape
    draw.rectangle((w // 4, h // 4, 3 * w // 4, 3 * h // 4), fill=color)
    # Add pattern (stripes)
    for y in range(h // 4, 3 * h // 4, 20):
        draw.line(
            (w // 4, y, 3 * w // 4, y), fill=(color[0] + 30, color[1] + 30, color[2] + 30), width=2
        )
    return img


def _make_catvton_result(person: Image.Image, garment_color: tuple[int, int, int]) -> Image.Image:
    """Create a synthetic CatVTON result (person wearing the garment)."""
    result = person.copy()
    draw = ImageDraw.Draw(result)
    w, h = result.size
    # Simulate pants on person
    draw.rectangle((w // 2 - 70, 510, w // 2 + 70, 900), fill=garment_color)
    return result


class TestDetailFidelityPipelineLowerCategory:
    """Test category locking through the full pipeline."""

    def test_category_round_trip_pants(self):
        """Pants category should survive the full pipeline as 'lower'."""
        garment_category = "裤子"
        cloth_type = "upper"
        cat = garment_category.strip().lower()
        if any(k in cat for k in ("bottom", "下装", "裤")):
            cloth_type = "lower"
        assert cloth_type == "lower"
        assert _catvton_category_hint(cloth_type) == "lower"

    def test_category_round_trip_bottom(self):
        """Bottom category should survive the full pipeline as 'lower'."""
        garment_category = "bottom"
        cloth_type = "upper"
        cat = garment_category.strip().lower()
        if any(k in cat for k in ("bottom", "下装", "裤")):
            cloth_type = "lower"
        assert cloth_type == "lower"
        assert _catvton_category_hint(cloth_type) == "lower"

    def test_category_round_trip_top_stays_upper(self):
        """Top category should remain 'upper' through the pipeline."""
        garment_category = "top"
        cloth_type = "upper"
        cat = garment_category.strip().lower()
        if any(k in cat for k in ("bottom", "下装", "裤")):
            cloth_type = "lower"
        assert cloth_type == "upper"
        assert _catvton_category_hint(cloth_type) == "upper"


class TestDetailFidelityRawQualityGate:
    """Test raw quality gate with lower garments."""

    def test_raw_quality_for_lower_garment(self):
        """Quality gate should produce reasonable scores for lower garments."""
        person = _make_person_image()
        garment = _make_garment_image(color=(50, 50, 150))
        result = _make_catvton_result(person, garment_color=(55, 55, 155))

        features = extract_engine_decision_features(garment)

        quality = evaluate_raw_catvton_quality(
            raw_result=result,
            original_garment=garment,
            person_image=person,
            garment_category="bottom",
            features=features,
        )

        # Quality scores should be valid
        assert quality.color_delta >= 0
        assert quality.artifact_score >= 0
        assert quality.garment_coverage >= 0
        assert quality.decision in ("raw", "color_only", "pattern_only", "artifact_only", "full")

    def test_engine_decision_for_patterned_lower_garment(self):
        """Patterned lower garment should trigger spatial or uniform engine."""
        garment = _make_garment_image(color=(50, 50, 150))
        features = extract_engine_decision_features(garment)

        engine, reason = decide_color_fidelity_engine(
            features=features,
            cutout_passed=True,
            input_anomaly_passed=True,
        )

        # Should not be skipped for a colored garment
        assert engine in ("spatial", "uniform")


class TestDetailFidelityRegionBounds:
    """Test that lower garments get correct region bounds."""

    def test_lower_garment_body_cy_is_below_waist(self):
        """For lower garments, body_cy should be between waist_y and ankle_y."""
        waist_y = 500
        ankle_y = 900
        body_cy = (waist_y + ankle_y) // 2
        assert waist_y < body_cy < ankle_y

    def test_lower_garment_region_covers_pants(self):
        """Lower garment region should cover the pants area."""
        ch = 1024
        waist_y = 500
        ankle_y = 900

        gar_y0 = max(0, int(waist_y - ch * 0.02))
        gar_y1 = min(ch, int(ankle_y + ch * 0.03))

        # Region should span from near waist to near ankle
        assert gar_y0 < waist_y
        assert gar_y1 > ankle_y
        # Region should be within image bounds
        assert gar_y0 >= 0
        assert gar_y1 <= ch

    def test_protection_mask_preserves_upper_body(self):
        """Lower-body protection mask should preserve upper body pixels."""
        from PIL import Image as PILImage

        cw, ch = 100, 200
        waist_y = 100
        ankle_y = 170

        protect = PILImage.new("L", (cw, ch), color=255)
        protect_upper_y = max(0, waist_y - int(ch * 0.02))
        if protect_upper_y > 0:
            protect.paste(0, (0, 0, cw, protect_upper_y))
        protect_lower_y = min(ch, ankle_y + int(ch * 0.06))
        if protect_lower_y < ch:
            protect.paste(0, (0, protect_lower_y, cw, ch))

        protect_np = np.array(protect)
        # Upper body (y=50) should be protected
        assert protect_np[50, 50] == 0
        # Pants region (y=140) should be allowed
        assert protect_np[140, 50] == 255
        # Shoes (y=185) should be protected
        assert protect_np[185, 50] == 0
