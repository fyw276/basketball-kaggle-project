from __future__ import annotations

from PIL import Image

from app.services.tryon_v2.occlusion_blend import build_change_mask, occlusion_validity_score
from app.services.tryon_v2.qc import evaluate_qc


def test_qc_passes_for_reasonable_local_change():
    person = Image.new("RGB", (256, 384), color=(180, 180, 180))
    result = Image.new("RGB", (256, 384), color=(180, 180, 180))
    # Simulate moderate garment replacement in lower body.
    for x in range(96, 160):
        for y in range(180, 330):
            result.putpixel((x, y), (130, 130, 130))

    qc = evaluate_qc(person, result, threshold=0.6)

    assert qc.passed is True
    assert qc.scores["identity_preserve_score"] >= 0.85
    assert qc.scores["qc_aggregate_score"] >= 0.6


def test_qc_fails_for_heavy_changed_output():
    person = Image.new("RGB", (256, 384), color=(200, 200, 200))
    # Simulate severe artifact / identity drift
    result = Image.new("RGB", (256, 384), color=(5, 5, 5))

    qc = evaluate_qc(person, result, threshold=0.6)

    assert qc.passed is False
    assert qc.scores["qc_aggregate_score"] < 0.6


def test_build_change_mask_detects_modified_region():
    person = Image.new("RGB", (64, 64), color=(120, 120, 120))
    result = Image.new("RGB", (64, 64), color=(120, 120, 120))
    for x in range(20, 44):
        for y in range(20, 44):
            result.putpixel((x, y), (220, 220, 220))

    mask = build_change_mask(person, result)
    assert mask.shape == (64, 64)
    assert float(mask.mean()) > 0.05


def test_occlusion_validity_score_lower_for_over_changed_output():
    person = Image.new("RGB", (256, 384), color=(180, 180, 180))
    mild = Image.new("RGB", (256, 384), color=(180, 180, 180))
    severe = Image.new("RGB", (256, 384), color=(15, 15, 15))

    # Mild local change in lower-body ROI
    for x in range(90, 165):
        for y in range(180, 330):
            mild.putpixel((x, y), (130, 130, 130))

    score_mild = occlusion_validity_score(person, mild)
    score_severe = occlusion_validity_score(person, severe)

    assert 0.0 <= score_mild <= 1.0
    assert 0.0 <= score_severe <= 1.0
    assert score_mild >= score_severe
