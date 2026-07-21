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


def test_flat_color_block_raw_is_rejected():
    from PIL import Image, ImageDraw

    from app.services.tryon_v2.fidelity_guard import (
        evaluate_raw_catvton_quality,
        extract_engine_decision_features,
    )

    person = Image.new("RGB", (256, 384), (220, 220, 220))
    ImageDraw.Draw(person).rectangle((90, 40, 166, 360), fill=(180, 160, 150))

    garment = Image.new("RGB", (200, 360), (255, 255, 255))
    ImageDraw.Draw(garment).rectangle((40, 20, 160, 340), fill=(60, 40, 30))

    # Simulate CatVTON color-block paste: solid rectangle over legs.
    raw = person.copy()
    ImageDraw.Draw(raw).rectangle((80, 140, 176, 330), fill=(60, 40, 30))
    mask = Image.new("L", (256, 384), 0)
    ImageDraw.Draw(mask).rectangle((80, 140, 176, 330), fill=255)

    q = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="下装",
        features=extract_engine_decision_features(garment),
        raw_mask_image=mask,
    )
    assert q.decision != "raw"
    assert "flat_color_block" in q.reason or q.artifact_passed is False
