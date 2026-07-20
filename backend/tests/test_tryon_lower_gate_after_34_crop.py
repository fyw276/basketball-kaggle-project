"""Lower input gate must not reject valid full-body photos after 3:4 crop."""

from __future__ import annotations

from PIL import Image, ImageDraw

from app.services.tryon_v2.input_gate import (
    _score_full_body,
    _score_full_body_aspect,
    evaluate_input_gate,
)


def _make_34_person() -> Image.Image:
    """Synthetic standing person on the CatVTON 3:4 canvas (768x1024)."""
    img = Image.new("RGB", (768, 1024), color=(230, 225, 220))
    draw = ImageDraw.Draw(img)
    # Head / torso / legs roughly matching a standing figure.
    draw.ellipse((334, 60, 434, 160), fill=(200, 170, 150))
    draw.rectangle((300, 160, 468, 480), fill=(90, 120, 180))
    draw.rectangle((310, 480, 380, 900), fill=(40, 40, 90))
    draw.rectangle((388, 480, 458, 900), fill=(40, 40, 90))
    draw.rectangle((300, 900, 380, 960), fill=(30, 30, 30))
    draw.rectangle((388, 900, 468, 960), fill=(30, 30, 30))
    return img


def _make_white_pants() -> Image.Image:
    img = Image.new("RGB", (768, 768), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Simple pants silhouette with crotch gap.
    draw.rectangle((260, 120, 508, 280), fill=(50, 70, 140))
    draw.rectangle((260, 280, 360, 640), fill=(50, 70, 140))
    draw.rectangle((408, 280, 508, 640), fill=(50, 70, 140))
    return img


def test_aspect_score_on_34_canvas_is_below_lower_threshold():
    person = _make_34_person()
    aspect = _score_full_body_aspect(person)
    assert aspect < 0.65


def test_full_body_score_recovers_via_pose_or_is_not_aspect_limited(monkeypatch):
    """After 3:4 crop, full_body must not be stuck at ~0.56 when body is standing."""
    import app.services.tryon_v2.input_gate as gate

    # Avoid real MediaPipe in unit tests (can AV on Windows).
    monkeypatch.setattr(gate, "_score_full_body_pose_span", lambda _img: 0.90)
    person = _make_34_person()
    aspect = _score_full_body_aspect(person)
    assert aspect < 0.65
    assert _score_full_body(person) >= 0.65


def test_lower_gate_passes_when_pose_confirms_legs_despite_weak_std(monkeypatch):
    """User failure: leg_visibility std≈0.36 but lower_pose=1.0 must still pass."""
    import app.services.tryon_v2.input_gate as gate

    monkeypatch.setattr(gate, "_score_full_body_pose_span", lambda _img: 1.0)
    monkeypatch.setattr(gate, "_score_lower_pose_keypoints", lambda _img: 1.0)
    monkeypatch.setattr(gate, "_score_leg_visibility_std", lambda _img: 0.36)
    monkeypatch.setattr(gate, "_score_front_pose", lambda _img: 0.88)
    monkeypatch.setattr(gate, "_score_garment_front", lambda _img: 0.66)
    monkeypatch.setattr(gate, "_score_garment_background_cleanliness", lambda _img: 1.0)

    class _Cutout:
        cropped = _make_white_pants().convert("RGBA")

    monkeypatch.setattr(
        "app.services.tryon_v2.garment_struct.cutout_garment_rgba",
        lambda *_a, **_k: _Cutout(),
    )
    monkeypatch.setattr(
        "app.services.tryon_v2.preprocess.evaluate_lower_garment_qc",
        lambda _rgba: {"passed": True, "score": 0.8, "message": None},
    )

    result = evaluate_input_gate(
        person_image=_make_34_person(),
        garment_image=_make_white_pants(),
        garment_category="下装",
        strict=False,
        thresholds={
            "full_body": 0.45,
            "leg_visibility": 0.35,
            "front_pose": 0.25,
            "garment_front": 0.35,
        },
    )
    assert result.passed, (result.error_code, result.message, result.scores)
    assert result.scores["leg_visibility_score"] >= 1.0
    assert result.scores["leg_visibility_min"] == 0.45


def test_lower_gate_does_not_fail_solely_on_34_aspect(monkeypatch):
    """Force pose-based recovery so gate passes on a 3:4 standing person."""
    import app.services.tryon_v2.input_gate as gate

    monkeypatch.setattr(gate, "_score_full_body_pose_span", lambda _img: 0.90)
    monkeypatch.setattr(gate, "_score_lower_pose_keypoints", lambda _img: 1.0)
    monkeypatch.setattr(gate, "_score_leg_visibility_std", lambda _img: 0.80)
    monkeypatch.setattr(gate, "_score_front_pose", lambda _img: 0.90)
    # Clean white-bg pants: skip weak FG-ratio via pants QC path.
    monkeypatch.setattr(gate, "_score_garment_front", lambda _img: 0.30)
    monkeypatch.setattr(gate, "_score_garment_background_cleanliness", lambda _img: 1.0)

    class _Cutout:
        cropped = _make_white_pants().convert("RGBA")

    monkeypatch.setattr(
        "app.services.tryon_v2.garment_struct.cutout_garment_rgba",
        lambda *_a, **_k: _Cutout(),
    )
    monkeypatch.setattr(
        "app.services.tryon_v2.preprocess.evaluate_lower_garment_qc",
        lambda _rgba: {"passed": True, "score": 0.8, "message": None},
    )

    result = evaluate_input_gate(
        person_image=_make_34_person(),
        garment_image=_make_white_pants(),
        garment_category="bottom",
        strict=True,
        thresholds={
            "full_body": 0.55,
            "leg_visibility": 0.45,
            "front_pose": 0.35,
            "garment_front": 0.45,
        },
    )
    assert result.passed, (result.error_code, result.message, result.scores)
    assert result.scores["full_body_score"] >= 0.65
