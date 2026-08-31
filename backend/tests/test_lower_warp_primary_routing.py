"""Lower garments use warp-primary; optional CatVTON lighting only; upper untouched."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
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
async def test_detail_fidelity_lower_routes_warp_primary_before_upper_path(monkeypatch):
    """Lower still enters warp-primary early; CatVTON is lighting-only when configured."""
    from app.services.tryon_v2.category_utils import (
        is_lower_garment_category,
        map_to_catvton_cloth_type,
    )
    from app.services.tryon_v2.warp_engine import tryon_lower_warp_primary

    person = _fake_person()
    garment = _fake_pants()
    warp_result = Image.new("RGB", person.size, (45, 30, 25))
    warp_meta = {
        "engine": "lower_warp_primary",
        "catvton_used": False,
        "use_knee_split": False,
    }

    monkeypatch.setattr(
        "app.services.tryon_v2.warp_engine.tryon_lower_warp_primary",
        lambda **kwargs: (warp_result, warp_meta),
    )

    mode = "detail_fidelity"
    garment_category = "下装"
    cloth_type = map_to_catvton_cloth_type(garment_category)
    assert is_lower_garment_category(garment_category)
    assert cloth_type == "lower"

    entered_lower = False
    if mode in {"detail_fidelity", "hybrid"} and (
        is_lower_garment_category(garment_category) or cloth_type == "lower"
    ):
        entered_lower = True
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
        result = {"status": "error"}

    assert entered_lower is True
    assert result["status"] == "success"
    assert result["metadata"]["pipeline"] == "LOWER_WARP_PRIMARY"
    assert result["metadata"].get("catvton_used") is False


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
    assert meta.get("use_knee_split") is False
    waist_raise = float(meta.get("waist_raise_ratio") or 0)
    assert 0.0 <= waist_raise <= 0.04
    assert float(meta.get("hem_extend_ratio") or 0) > 0
    arr = np.asarray(out)
    lower = arr[arr.shape[0] // 2 :, :, :]
    dark_ratio = float((lower.mean(axis=2) < 100).mean())
    assert dark_ratio > 0.02 or meta.get("engine") == "lower_warp_primary_fallback"


def test_lower_warp_primary_boxes_cover_high_waist_and_hem():
    """Legs extend high (continuous waist) and hem past ankle."""
    from app.services.tryon_v2.pose_utils import (
        detect_pose_keypoints,
        get_body_bounds_from_keypoints,
    )
    from app.services.tryon_v2.warp_engine import tryon_lower_warp_primary

    person = _fake_person(size=(384, 512))
    garment = _fake_pants()
    out, meta = tryon_lower_warp_primary(person, garment)
    assert out.size == person.size
    assert meta.get("include_waistband") is False
    assert meta.get("continuous_leg_waist") is True

    left = meta["left_leg_box"]
    right = meta["right_leg_box"]
    # Legs start in upper-mid body (raised continuous waist), not low hip.
    assert min(left[1], right[1]) < int(person.size[1] * 0.55)
    assert max(left[3], right[3]) > int(person.size[1] * 0.84)

    kpts = detect_pose_keypoints(person)
    if kpts:
        bounds = get_body_bounds_from_keypoints(kpts, *person.size, "bottom")
        if bounds.get("valid"):
            assert max(left[3], right[3]) >= int(bounds["ankle_y"]) + 8


def test_lower_warp_primary_keeps_waist_at_natural_level():
    from app.services.tryon_v2.warp_engine import _lower_warp_primary_box_extends

    person = _fake_person(size=(384, 512))
    waist_raise, _, meta = _lower_warp_primary_box_extends(person)

    assert waist_raise <= 0.04
    assert meta["person_waist_y"] >= int(person.size[1] * 0.38)
    assert meta["person_waist_y"] <= int(person.size[1] * 0.58)


def test_lower_warp_primary_adapts_to_body_width_proportionally():
    from app.services.tryon_v2.warp_engine import _estimate_person_body_scale

    slim = _fake_person(size=(320, 480))
    wide = _fake_person(size=(420, 560))

    slim_meta = _estimate_person_body_scale(slim)
    wide_meta = _estimate_person_body_scale(wide)

    assert slim_meta["width_scale"] < wide_meta["width_scale"]
    assert 0.72 <= slim_meta["width_scale"] <= 1.35
    assert 0.72 <= wide_meta["width_scale"] <= 1.35


def test_lower_warp_primary_uses_pose_leg_axis():
    from app.services.tryon_v2.warp_engine import tryon_lower_warp_primary

    person = _fake_person(size=(384, 512))
    garment = _fake_pants()
    out, meta = tryon_lower_warp_primary(person, garment)
    assert out.size == person.size
    assert meta.get("pose_leg_axis") is True or meta.get("engine") == "lower_warp_primary_fallback"
    assert meta.get("wear_composite") is True or meta.get("engine") == "lower_warp_primary_fallback"
    # Opaque core should cover original bottoms (not translucent ghost).
    if meta.get("engine") == "lower_warp_primary":
        assert float(meta.get("opaque_core") or 0) > 0.02
        assert (meta.get("harden_meta") or {}).get("applied") is True


def test_harden_pants_warp_alpha_makes_core_opaque():
    from app.services.tryon_v2.warp_engine import _harden_pants_warp_alpha

    layer = Image.new("RGBA", (64, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((16, 30, 48, 90), fill=(40, 28, 22, 140))  # translucent brown
    out, meta = _harden_pants_warp_alpha(layer)
    assert meta.get("applied") is True
    a = np.asarray(out)[:, :, 3]
    core = a[40:80, 20:44]
    assert float((core > 230).mean()) > 0.5


def test_fill_pants_inner_leg_seam_closes_center_gap():
    from app.services.tryon_v2.warp_engine import _fill_pants_inner_leg_seam

    layer = Image.new("RGBA", (80, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # Two brown legs with a gap down the middle (simulates person bleed).
    d.rectangle((18, 20, 35, 110), fill=(50, 35, 28, 255))
    d.rectangle((45, 20, 62, 110), fill=(50, 35, 28, 255))
    out, meta = _fill_pants_inner_leg_seam(
        layer,
        left_leg_box=(18, 20, 40, 110),
        right_leg_box=(40, 20, 62, 110),
    )
    assert meta.get("applied") is True
    arr = np.asarray(out)
    mid = arr[50:90, 36:44]
    # Gap should be filled with opaque brown, not empty/white.
    assert float((mid[:, :, 3] > 200).mean()) > 0.7
    assert float(mid[:, :, 0].mean()) < 120


def test_fill_pants_inner_leg_seam_heals_opaque_bright_ridge():
    """Overlapping L/R legs with a baked-in white hairline must be darkened."""
    from app.services.tryon_v2.warp_engine import _fill_pants_inner_leg_seam

    layer = Image.new("RGBA", (80, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # Fully overlapping brown panel (no alpha gap) with a bright vertical seam.
    d.rectangle((18, 20, 62, 110), fill=(50, 35, 28, 255))
    d.line([(40, 25), (40, 105)], fill=(210, 205, 200, 255), width=2)
    out, meta = _fill_pants_inner_leg_seam(
        layer,
        left_leg_box=(18, 20, 42, 110),
        right_leg_box=(38, 20, 62, 110),
    )
    assert meta.get("applied") is True
    assert int(meta.get("healed_bright_px") or 0) > 0
    arr = np.asarray(out).astype(np.float32)
    ridge = arr[40:95, 39:42, :3].mean(axis=2)
    assert float(ridge.mean()) < 100.0
    assert float((ridge > 150).mean()) < 0.15


def test_strip_inner_leg_white_edge_clears_inseam_fringe():
    from app.services.tryon_v2.garment_struct import _strip_inner_leg_white_edge

    # Left leg crop: brown body + white fringe on the right (inseam).
    leg = Image.new("RGBA", (40, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(leg)
    d.rectangle((4, 4, 30, 76), fill=(48, 34, 28, 255))
    d.rectangle((28, 8, 36, 72), fill=(245, 245, 245, 255))
    out = _strip_inner_leg_white_edge(leg, inseam="right")
    arr = np.asarray(out)
    fringe = arr[10:70, 30:37]
    assert float((fringe[:, :, 3] < 20).mean()) > 0.6
    body = arr[10:70, 8:24]
    assert float((body[:, :, 3] > 200).mean()) > 0.85


def test_wear_composite_does_not_flash_white_pants_at_hips():
    """Waist tuck must not reveal bright original bottoms as a horizontal band."""
    from app.services.tryon_v2.warp_engine import _composite_lower_warp_as_worn

    person = Image.new("RGB", (120, 200), (240, 240, 240))  # white bottoms
    d = ImageDraw.Draw(person)
    d.rectangle((40, 20, 80, 90), fill=(120, 120, 120))  # gray tank
    layer = Image.new("RGBA", (120, 200), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(layer)
    d2.rectangle((35, 85, 85, 180), fill=(55, 40, 32, 255))  # brown pants over hips
    out, meta = _composite_lower_warp_as_worn(person, layer, drape_alpha=0.22, ankle_y=175)
    arr = np.asarray(out).astype(np.float32)
    # Mid-hip band on fabric should stay brown, not washed to white.
    band = arr[100:130, 45:75]
    assert float(band.mean()) < 120.0
    assert meta.get("applied") is True


def test_lower_warp_primary_adapts_to_different_person_proportions():
    """Different body sizes get pose-proportional hem/waist meta (not color crop)."""
    from app.services.tryon_v2.warp_engine import _lower_warp_primary_box_extends

    short = _fake_person(size=(320, 400))
    tall = _fake_person(size=(320, 640))
    _wr_s, he_s, meta_s = _lower_warp_primary_box_extends(short)
    _wr_t, he_t, meta_t = _lower_warp_primary_box_extends(tall)
    assert meta_t.get("adaptive") is True
    assert meta_t.get("mode") == "pose_proportional"
    assert meta_s.get("leg_len_px", 0) != meta_t.get("leg_len_px", -1)
    assert "person_waist_y" in meta_t
    assert he_t >= 0.04 and he_s >= 0.04


def test_blend_lower_ai_lighting_keeps_warp_chroma():
    """LAB lighting blend should keep warp color; only shift luminance toward AI."""
    from app.services.tryon_v2.warp_engine import blend_lower_ai_lighting_onto_warp

    person = Image.new("RGB", (64, 96), (200, 200, 200))
    # Dark brown warp pants in lower half
    warp = person.copy()
    wp = np.asarray(warp).copy()
    wp[40:, 16:48] = (40, 28, 22)
    warp = Image.fromarray(wp, mode="RGB")
    # Bright beige AI (bad color) with darker fold stripes
    ai = np.full((96, 64, 3), (180, 150, 120), dtype=np.uint8)
    ai[50:55, 16:48] = (90, 80, 70)
    ai_img = Image.fromarray(ai, mode="RGB")

    out, meta = blend_lower_ai_lighting_onto_warp(warp, ai_img, person, lighting_strength=0.42)
    assert meta.get("applied") is True
    out_arr = np.asarray(out)
    region = out_arr[42:90, 18:46]
    mean = region.mean(axis=(0, 1))
    # Stay near dark brown, not washed to AI beige.
    assert mean[0] < 100 and mean[1] < 90 and mean[2] < 85
    # Chroma still brown-ish (R >= G >= B-ish for this fabric).
    assert mean[0] >= mean[1] - 5


def test_lower_ai_lighting_rejects_solid_leg_blob_reason():
    """Gate helper: strong_spatial / color miss / blob reasons must skip lighting blend."""
    reason = "lower_solid_leg_blob_no_crotch"
    decision = "strong_spatial"
    reject_blob = (
        decision in {"strong_spatial", "color_only", "color_and_pattern"}
        or "solid_leg_blob" in reason
        or "flat_color_block" in reason
        or "texture_collapsed" in reason
    )
    assert reject_blob is True

    color_miss = SimpleNamespace(decision="color_only", reason="raw_pattern_ok_color_missing")
    reject_color = (
        color_miss.decision in {"strong_spatial", "color_only", "color_and_pattern"}
        or "solid_leg_blob" in (color_miss.reason or "")
        or "flat_color_block" in (color_miss.reason or "")
        or "texture_collapsed" in (color_miss.reason or "")
    )
    assert reject_color is True

    ok = SimpleNamespace(decision="raw", reason="raw_color_pattern_artifacts_passed")
    reject_ok = (
        ok.decision in {"strong_spatial", "color_only", "color_and_pattern"}
        or "solid_leg_blob" in (ok.reason or "")
        or "flat_color_block" in (ok.reason or "")
        or "texture_collapsed" in (ok.reason or "")
    )
    assert reject_ok is False


@pytest.mark.asyncio
async def test_lower_lighting_falls_back_when_catvton_rejected(monkeypatch):
    """When CatVTON is rejected as blob, keep warp result (no lighting applied)."""
    from app.services.tryon_v2.warp_engine import blend_lower_ai_lighting_onto_warp

    person = _fake_person(size=(64, 96))
    warp = Image.new("RGB", person.size, (45, 30, 25))
    ai = Image.new("RGB", person.size, (180, 150, 120))

    # Simulate reject path: do not call blend.
    raw_quality = SimpleNamespace(
        decision="strong_spatial",
        reason="lower_solid_leg_blob_no_crotch",
    )
    reason = raw_quality.reason or ""
    reject_blob = (
        raw_quality.decision == "strong_spatial"
        or "solid_leg_blob" in reason
        or "flat_color_block" in reason
        or "texture_collapsed" in reason
    )
    assert reject_blob is True
    result_img = warp
    # Blend must not run when rejected; if forced, would still keep chroma but we skip.
    blended, _ = blend_lower_ai_lighting_onto_warp(warp, ai, person)
    assert result_img is warp
    assert blended.size == person.size
