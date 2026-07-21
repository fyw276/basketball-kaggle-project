"""SCHP lower masks must treat LIP 'dress' as replaceable lower clothing."""

from __future__ import annotations

import numpy as np

from app.services.human_parsing import LIP_LABELS, SCHPResult


def test_bottom_region_includes_dress_and_excludes_from_torso_upper():
    h, w = 40, 30
    parsing = np.zeros((h, w), dtype=np.int32)
    parsing[10:35, 8:22] = LIP_LABELS.index("dress")
    parsing[2:8, 10:20] = LIP_LABELS.index("upper_clothes")
    parsing[5:9, 5:10] = LIP_LABELS.index("face")

    result = SCHPResult(parsing, LIP_LABELS, source="unit_test")
    bottom = result.bottom_region()
    torso = result.torso_upper

    assert float(bottom[10:35, 8:22].mean()) > 0.9
    assert float(bottom[2:8, 10:20].mean()) < 0.1
    assert float(torso[2:8, 10:20].mean()) > 0.9
    assert float(torso[10:35, 8:22].mean()) < 0.1


def test_solid_leg_blob_raw_is_rejected_for_lower():
    """CatVTON often paints a skirt-like solid panel; must not pass as raw."""
    from PIL import Image, ImageDraw

    from app.services.tryon_v2.fidelity_guard import (
        evaluate_raw_catvton_quality,
        extract_engine_decision_features,
    )

    person = Image.new("RGB", (256, 384), (230, 230, 230))
    ImageDraw.Draw(person).rectangle((100, 40, 156, 360), fill=(190, 170, 160))

    garment = Image.new("RGB", (180, 320), (255, 255, 255))
    d = ImageDraw.Draw(garment)
    # Pants with visible fold contrast so source texture score is non-trivial.
    d.rectangle((40, 20, 140, 300), fill=(55, 40, 32))
    for y in range(40, 290, 12):
        d.line((50, y, 130, y + 4), fill=(90, 70, 55), width=2)

    raw = person.copy()
    # Solid panel over both legs — no crotch split.
    ImageDraw.Draw(raw).polygon(
        [(95, 150), (165, 150), (170, 340), (90, 340)],
        fill=(55, 40, 32),
    )
    mask = Image.new("L", (256, 384), 0)
    ImageDraw.Draw(mask).polygon(
        [(95, 150), (165, 150), (170, 340), (90, 340)],
        fill=255,
    )

    q = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="下装",
        features=extract_engine_decision_features(garment),
        raw_mask_image=mask,
    )
    assert q.decision == "strong_spatial", (q.decision, q.reason)
    assert q.artifact_passed is False
    assert any(
        k in q.reason
        for k in (
            "solid_leg_blob",
            "texture_collapsed",
            "flat_color_block",
            "lower_",
        )
    )
