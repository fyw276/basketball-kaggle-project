from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from app.services.tryon_v2.fidelity_guard import (
    EngineDecisionFeatures,
    decide_color_fidelity_engine,
    detect_post_cf_artifacts,
    estimate_pattern_enhance_strength,
    evaluate_cutout_alpha_qc,
    evaluate_raw_catvton_quality,
    extract_engine_decision_features,
    repair_raw_catvton_artifacts,
    score_input_anomaly,
    should_force_lower_structured_pattern_recovery,
)


def _solid_image(color: tuple[int, int, int], size: tuple[int, int] = (256, 256)) -> Image.Image:
    return Image.new("RGB", size=size, color=color)


def test_extract_engine_decision_features_white_garment():
    img = _solid_image((245, 245, 245))
    feats = extract_engine_decision_features(img)
    assert feats.is_white_garment is True
    assert 0.0 <= feats.sat_mean <= 0.1


def test_dark_low_saturation_garment_is_not_white_garment():
    img = _solid_image((58, 62, 60))
    draw = ImageDraw.Draw(img)
    draw.rectangle((170, 68, 210, 92), fill=(225, 60, 45))

    feats = extract_engine_decision_features(img)

    assert feats.is_white_garment is False
    engine, reason = decide_color_fidelity_engine(
        features=feats,
        cutout_passed=True,
        input_anomaly_passed=True,
    )
    assert engine != "skip"
    assert reason != "white_garment"


def test_light_printed_garment_is_not_white_garment():
    img = _solid_image((238, 232, 214))
    draw = ImageDraw.Draw(img)
    for x in range(40, 220, 28):
        draw.line((x, 60, x + 36, 210), fill=(120, 135, 155), width=2)
    draw.ellipse((95, 90, 165, 160), outline=(95, 120, 150), width=3)

    feats = extract_engine_decision_features(img)

    assert feats.pattern_score >= 0.25
    assert feats.is_white_garment is False
    engine, reason = decide_color_fidelity_engine(
        features=feats,
        cutout_passed=True,
        input_anomaly_passed=True,
    )
    assert engine != "skip"
    assert reason != "white_garment"


def test_decide_color_fidelity_engine_hysteresis_guard_band():
    img = _solid_image((180, 180, 180))
    feats = extract_engine_decision_features(img)
    # Force guard-band pattern score and trigger conservative behavior.
    feats.pattern_score = 0.41
    engine, reason = decide_color_fidelity_engine(
        features=feats,
        cutout_passed=True,
        input_anomaly_passed=True,
    )
    assert engine in {"uniform", "skip"}
    assert "guard_band" in reason


def test_decide_color_fidelity_engine_blocked_by_qc_gate():
    img = _solid_image((130, 130, 130))
    feats = extract_engine_decision_features(img)
    engine, reason = decide_color_fidelity_engine(
        features=feats,
        cutout_passed=False,
        input_anomaly_passed=True,
    )
    assert engine == "skip"
    assert reason == "cutout_qc_failed"


def test_strong_patterned_garment_is_not_blocked_by_product_photo_qc_noise():
    feats = EngineDecisionFeatures(
        sat_mean=0.055,
        sat_max=0.25,
        bright_mean=0.69,
        is_white_garment=False,
        has_color=True,
        pattern_score=0.78,
        pattern_confidence=1.0,
    )

    engine, reason = decide_color_fidelity_engine(
        features=feats,
        cutout_passed=False,
        input_anomaly_passed=False,
    )

    assert engine == "spatial"
    assert reason == "pattern_spatial"


def test_score_input_anomaly_detects_mirror_like_artifact():
    w, h = 320, 320
    left = np.zeros((h, w // 2, 3), dtype=np.uint8)
    for y in range(h):
        left[y, :, 0] = y % 255
        left[y, :, 1] = (2 * y) % 255
        left[y, :, 2] = 120
    right = left[:, ::-1, :]
    arr = np.concatenate([left, right], axis=1)
    img = Image.fromarray(arr, mode="RGB")

    score = score_input_anomaly(img).mirror_ghost_score
    assert score >= 0.35


def test_symmetric_patterned_garment_is_not_blocked_by_anomaly_gate():
    """Product-shot T-shirts are naturally symmetric; that is not a ghost artifact."""
    img = _solid_image((248, 248, 248), size=(320, 320))
    draw = ImageDraw.Draw(img)
    draw.rectangle((50, 60, 270, 285), fill=(236, 229, 207))
    draw.polygon([(50, 60), (18, 110), (68, 130)], fill=(236, 229, 207))
    draw.polygon([(270, 60), (302, 110), (252, 130)], fill=(236, 229, 207))
    draw.ellipse((130, 120, 190, 180), fill=(110, 170, 220), outline=(60, 90, 130), width=3)
    draw.rectangle((145, 180, 175, 230), fill=(245, 210, 80), outline=(80, 80, 80), width=2)
    for x, y in [(85, 105), (235, 105), (95, 230), (225, 230)]:
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=(230, 120, 150))

    anomaly = score_input_anomaly(img)
    feats = extract_engine_decision_features(img)
    engine, reason = decide_color_fidelity_engine(
        features=feats,
        cutout_passed=True,
        input_anomaly_passed=anomaly.passed,
    )

    assert anomaly.passed is False
    assert feats.pattern_score > 0.45
    assert engine == "spatial"
    assert reason == "pattern_spatial"


def test_dark_low_average_saturation_logo_garment_uses_spatial_fidelity():
    img = _solid_image((50, 50, 50), size=(320, 320))
    draw = ImageDraw.Draw(img)
    draw.rectangle((52, 58, 268, 286), fill=(48, 48, 48))
    draw.polygon([(52, 58), (18, 112), (70, 132)], fill=(48, 48, 48))
    draw.polygon([(268, 58), (302, 112), (250, 132)], fill=(48, 48, 48))
    for y in range(88, 276, 18):
        draw.line((70, y, 250, y + 12), fill=(86, 86, 86), width=2)
    draw.ellipse((188, 112, 224, 148), fill=(215, 54, 45))
    draw.rectangle((198, 148, 215, 176), fill=(250, 224, 130))

    feats = extract_engine_decision_features(img)
    engine, reason = decide_color_fidelity_engine(
        features=feats,
        cutout_passed=True,
        input_anomaly_passed=True,
    )

    assert feats.sat_mean < 0.10
    assert feats.pattern_score > 0.45
    assert engine == "spatial"
    assert reason == "pattern_spatial"


def test_detect_post_cf_artifacts_flags_blocky_overlay():
    base = _solid_image((180, 180, 180), size=(256, 256))
    bad = base.copy()
    draw = ImageDraw.Draw(bad)
    draw.rectangle((30, 30, 210, 230), fill=(10, 220, 220))

    report = detect_post_cf_artifacts(base, bad)
    assert report.failed is True
    assert report.blockiness_score > 0.30 or report.outlier_ratio > 0.08


def test_detect_post_cf_artifacts_flags_horizontal_hard_edge_overlay():
    base = _solid_image((185, 185, 185), size=(256, 256))
    bad = base.copy()
    draw = ImageDraw.Draw(bad)
    draw.rectangle((48, 118, 208, 214), fill=(82, 108, 146))
    draw.rectangle((48, 118, 208, 126), fill=(128, 160, 205))

    report = detect_post_cf_artifacts(base, bad)

    assert report.failed is True
    assert report.horizontal_hard_edge_score > 0.20


def test_detect_post_cf_artifacts_flags_rectangular_overlay_feel():
    base = _solid_image((192, 192, 192), size=(256, 256))
    bad = base.copy()
    draw = ImageDraw.Draw(bad)
    draw.rectangle((72, 92, 184, 230), fill=(55, 78, 118))

    report = detect_post_cf_artifacts(base, bad)

    assert report.failed is True
    assert report.rectangular_overlay_score > 0.18


def test_evaluate_cutout_alpha_qc_fails_for_full_canvas_alpha():
    rgba = Image.new("RGBA", (256, 256), color=(120, 120, 120, 255))
    qc = evaluate_cutout_alpha_qc(rgba)
    assert qc.passed is False
    assert qc.edge_touch_ratio > 0.12


def test_estimate_pattern_enhance_strength_disables_on_artifacts():
    base = _solid_image((180, 180, 180))
    result = base.copy()
    draw = ImageDraw.Draw(result)
    draw.rectangle((20, 20, 220, 230), fill=(30, 200, 200))
    report = detect_post_cf_artifacts(base, result)

    strength = estimate_pattern_enhance_strength(
        pattern_score=0.65,
        artifact_report=report,
        result_image=result,
    )
    assert strength == 0.0


def test_raw_catvton_quality_passes_when_color_pattern_and_artifacts_are_ok():
    garment = _solid_image((48, 48, 48), size=(320, 320))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((56, 64, 264, 286), fill=(45, 45, 45))
    draw.ellipse((194, 116, 226, 148), fill=(220, 55, 45))
    draw.rectangle((204, 148, 218, 172), fill=(245, 220, 120))

    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((145, 175, 380, 430), fill=(46, 46, 46))
    draw.ellipse((300, 225, 320, 245), fill=(220, 55, 45))
    draw.rectangle((307, 245, 316, 260), fill=(245, 220, 120))

    features = extract_engine_decision_features(garment)
    quality = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        features=features,
    )

    assert quality.color_passed is True
    assert quality.pattern_passed is True
    assert quality.artifact_passed is True
    assert quality.decision in {"raw", "pattern_only"}


def test_raw_catvton_quality_uses_color_only_when_pattern_exists_but_color_is_off():
    garment = _solid_image((190, 128, 140), size=(320, 320))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((56, 64, 264, 286), fill=(190, 128, 140))
    draw.line((100, 90, 220, 210), fill=(60, 40, 45), width=5)

    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((145, 175, 380, 430), fill=(125, 110, 112))
    draw.line((190, 205, 310, 325), fill=(60, 40, 45), width=5)

    features = extract_engine_decision_features(garment)
    quality = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        features=features,
    )

    assert quality.color_passed is False
    assert quality.pattern_passed is True
    assert quality.decision == "color_only"


def test_raw_catvton_quality_uses_pattern_only_when_white_light_pattern_is_missing():
    garment = _solid_image((230, 216, 200), size=(320, 320))
    draw = ImageDraw.Draw(garment)
    for x in range(55, 275, 26):
        draw.line((x, 70, x + 34, 260), fill=(145, 155, 170), width=2)
    for x in range(80, 240, 35):
        draw.ellipse((x, 120, x + 18, 138), fill=(120, 180, 220), outline=(90, 90, 90))

    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((145, 175, 380, 430), fill=(230, 216, 200))

    features = extract_engine_decision_features(garment)
    quality = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        features=features,
    )

    assert quality.color_passed is True
    assert quality.pattern_passed is False
    assert quality.decision == "pattern_only"


def test_raw_catvton_quality_rejects_weak_signal_for_strong_pattern():
    garment = _solid_image((42, 42, 42), size=(320, 320))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((56, 64, 264, 286), fill=(40, 40, 40))
    for y in range(76, 280, 18):
        draw.line((70, y, 250, y), fill=(90, 90, 90), width=3)
    for x in range(82, 250, 24):
        draw.line((x, 70, x, 280), fill=(8, 8, 8), width=2)

    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((145, 310, 380, 690), fill=(43, 43, 43))

    features = extract_engine_decision_features(garment)
    quality = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="bottom",
        features=features,
    )

    assert quality.source_pattern_score >= 0.60
    assert quality.raw_pattern_signal < quality.source_pattern_score * 0.35
    assert quality.pattern_passed is False
    assert quality.decision in ("pattern_only", "strong_spatial")


def test_force_lower_structured_pattern_recovery_for_borderline_raw_pass():
    garment = _solid_image((28, 30, 36), size=(320, 320))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((52, 56, 268, 292), fill=(24, 26, 32))
    for y in range(64, 292, 18):
        draw.line((58, y, 262, y), fill=(90, 96, 108), width=2)
    for x in range(66, 262, 18):
        draw.line((x, 58, x, 292), fill=(72, 78, 90), width=2)

    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((145, 300, 380, 690), fill=(30, 30, 34))
    for y in range(320, 690, 34):
        draw.line((165, y, 360, y), fill=(54, 56, 62), width=1)

    features = extract_engine_decision_features(garment)
    quality = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="lower",
        features=features,
    )

    assert quality.decision in {"raw", "pattern_only"}
    assert quality.source_pattern_score >= 0.75
    assert quality.raw_pattern_signal <= max(0.47, quality.source_pattern_score * 0.49)
    assert (
        should_force_lower_structured_pattern_recovery(
            garment_category="lower",
            raw_quality=quality,
        )
        is True
    )


def test_force_lower_structured_pattern_recovery_not_used_for_non_lower():
    quality = type("Q", (), {})()
    quality.decision = "raw"
    quality.source_pattern_score = 0.95
    quality.raw_pattern_signal = 0.20
    quality.garment_coverage = 0.18

    assert (
        should_force_lower_structured_pattern_recovery(
            garment_category="upper",
            raw_quality=quality,
        )
        is False
    )


def test_force_lower_structured_pattern_recovery_handles_dark_plaid_threshold():
    quality = type("Q", (), {})()
    quality.decision = "raw"
    quality.source_pattern_score = 0.9527
    quality.raw_pattern_signal = 0.4632
    quality.garment_coverage = 0.1454

    assert (
        should_force_lower_structured_pattern_recovery(
            garment_category="lower",
            raw_quality=quality,
        )
        is True
    )


def test_raw_catvton_quality_uses_artifact_only_when_color_and_pattern_pass():
    garment = _solid_image((86, 150, 225), size=(320, 320))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((56, 64, 264, 286), fill=(86, 150, 225))
    for x in range(85, 230, 24):
        draw.line((x, 90, x + 35, 250), fill=(35, 70, 135), width=4)

    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((145, 175, 380, 430), fill=(86, 150, 225))
    for x in range(170, 330, 24):
        draw.line((x, 200, x + 35, 360), fill=(35, 70, 135), width=4)
    draw.rectangle((150, 180, 360, 260), fill=(250, 250, 250))

    features = extract_engine_decision_features(garment)
    quality = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        features=features,
    )

    assert quality.color_passed is True
    assert quality.pattern_passed is True
    assert quality.artifact_passed is False
    assert quality.decision == "artifact_only"


def test_raw_catvton_quality_prefers_supplied_catvton_mask():
    garment = _solid_image((80, 135, 220), size=(320, 320))
    draw = ImageDraw.Draw(garment)
    draw.line((80, 80, 240, 240), fill=(20, 45, 120), width=6)

    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((180, 210, 330, 360), fill=(80, 135, 220))
    draw.line((200, 225, 310, 340), fill=(20, 45, 120), width=6)

    mask = Image.new("L", raw.size, color=0)
    ImageDraw.Draw(mask).rectangle((180, 210, 330, 360), fill=255)

    features = extract_engine_decision_features(garment)
    quality = evaluate_raw_catvton_quality(
        raw_result=raw,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        features=features,
        raw_mask_image=mask,
    )

    assert 0.05 < quality.garment_coverage < 0.07


def test_repair_raw_catvton_artifacts_is_conservative():
    person = _solid_image((245, 245, 245), size=(512, 768))
    raw = person.copy()
    draw = ImageDraw.Draw(raw)
    draw.rectangle((145, 175, 380, 430), fill=(86, 150, 225))
    draw.rectangle((170, 205, 230, 250), fill=(250, 250, 250))

    mask = Image.new("L", raw.size, color=0)
    ImageDraw.Draw(mask).rectangle((145, 175, 380, 430), fill=255)

    repaired, meta = repair_raw_catvton_artifacts(
        raw_result=raw,
        person_image=person,
        garment_category="top",
        raw_mask_image=mask,
    )

    assert repaired.size == raw.size
    assert meta["engine"] == "raw_artifact_repair"
    assert meta["garment_coverage"] > 0
