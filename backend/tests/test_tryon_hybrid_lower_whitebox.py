"""White-box debug coverage for lower-body hybrid try-on."""

from __future__ import annotations

import json

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.services.tryon_v2 import warp_engine


def test_hybrid_lower_saves_whitebox_stages(tmp_path, monkeypatch):
    """Lower-body hybrid mode should save inspectable stage images."""

    from app.core.config import settings

    monkeypatch.setattr(settings, "TRYON_V2_HYBRID_WARP_OVERLAY_ENABLED", True)

    person = Image.new("RGB", (200, 240), (230, 230, 230))
    garment = Image.new("RGB", (80, 140), (20, 30, 45))
    catvton = Image.new("RGB", (100, 120), (210, 210, 210))

    def fake_pants_warp(person_image, garment_image):
        out = person_image.copy()
        draw = ImageDraw.Draw(out)
        draw.rectangle((50, 100, 150, 220), fill=(15, 25, 40))
        meta = warp_engine.WarpMetadata(
            engine="pants_warp_test",
            waistband_box=(50, 94, 150, 110),
            left_leg_box=(50, 110, 100, 220),
            right_leg_box=(100, 110, 150, 220),
            alpha_feather_px=3,
        )
        return out, meta

    def fake_foreground_mask(image):
        h, w = image.size[1], image.size[0]
        mask = np.zeros((h, w), dtype=bool)
        mask[100:220, 50:150] = True
        return mask

    monkeypatch.setattr(warp_engine, "tryon_pants_warp", fake_pants_warp)
    monkeypatch.setattr(warp_engine, "_person_foreground_mask", fake_foreground_mask)

    result, meta = warp_engine.tryon_hybrid_warp_catvton(
        person_image=person,
        garment_image=garment,
        catvton_result=catvton,
        garment_category="bottom",
        drape_alpha=0.65,
        debug_session_dir=str(tmp_path),
    )

    assert result.size == person.size
    assert meta["stage1_engine"] == "pants_warp"
    assert meta["warp_meta"]["engine"] == "pants_warp_test"
    region = meta["blend_meta"]["garment_region"]
    assert 45 <= region["x0"] <= 52
    assert 96 <= region["y0"] <= 102
    assert 148 <= region["x1"] <= 154
    assert 218 <= region["y1"] <= 224

    expected = [
        "hybrid_11_stage1_warp.jpg",
        "hybrid_11b_catvton_raw_input.jpg",
        "hybrid_12_ai_resized_to_warp.jpg",
        "hybrid_13_overlay_foreground_mask.png",
        "hybrid_14_overlay_blend_weight.png",
        "hybrid_15_overlay_result.jpg",
    ]
    for name in expected:
        assert (tmp_path / name).is_file(), name
        assert (tmp_path / name).with_suffix(".json").is_file(), name

    stage1_meta = json.loads((tmp_path / "hybrid_11_stage1_warp.json").read_text("utf-8"))
    assert stage1_meta["stage"] == "hybrid_stage1_warp"
    assert stage1_meta["engine"] == "pants_warp"

    mask_meta = json.loads((tmp_path / "hybrid_13_overlay_foreground_mask.json").read_text("utf-8"))
    assert mask_meta["stage"] == "hybrid_overlay_foreground_mask"
    assert mask_meta["garment_region"] == region
    assert mask_meta["coverage"] < 0.35


def test_hybrid_defaults_to_direct_catvton(tmp_path, monkeypatch):
    """Hybrid should not apply the legacy warp overlay unless explicitly enabled."""

    from app.core.config import settings

    monkeypatch.setattr(settings, "TRYON_V2_HYBRID_WARP_OVERLAY_ENABLED", False)

    person = Image.new("RGB", (200, 240), (230, 230, 230))
    garment = Image.new("RGB", (80, 140), (20, 30, 45))
    catvton = Image.new("RGB", (100, 120), (210, 210, 210))

    result, meta = warp_engine.tryon_hybrid_warp_catvton(
        person_image=person,
        garment_image=garment,
        catvton_result=catvton,
        garment_category="bottom",
        debug_session_dir=str(tmp_path),
    )

    assert result.size == person.size
    assert np.array(result).mean() == 210
    assert meta["engine"] == "catvton"
    assert meta["hybrid_warp_overlay_applied"] is False
    assert (tmp_path / "hybrid_11_direct_catvton.jpg").is_file()


def test_lower_structure_masks_soften_waist_and_protect_shoes():
    person = Image.new("RGB", (180, 240), (214, 214, 214))
    draw = ImageDraw.Draw(person)
    draw.rectangle((56, 202, 84, 236), fill=(248, 248, 248))
    draw.rectangle((96, 202, 124, 236), fill=(28, 28, 28))

    layer_alpha = np.zeros((240, 180), dtype=np.float32)
    layer_alpha[72:220, 40:140] = 1.0

    guides = {
        "waist_y": 82,
        "ankle_y": 206,
        "left_hip": (58, 80),
        "right_hip": (122, 84),
        "left_ankle": (64, 204),
        "right_ankle": (118, 206),
    }

    mask, meta = warp_engine._build_lower_structure_blend_masks(
        person_image=person,
        layer_alpha=layer_alpha,
        guides=guides,
    )

    assert meta["mask_coverage"] > 0.15
    assert mask[68, 90] < 0.15
    assert 0.15 < mask[84, 90] < 0.95
    assert mask[150, 90] > 0.90
    assert mask[224, 70] < 0.05
    assert mask[224, 110] < 0.05


def test_refined_lower_structure_overlay_mask_trims_upper_waist_halo():
    shaded_alpha = np.zeros((240, 180), dtype=np.float32)
    shaded_alpha[56:78, 40:140] = 0.42
    shaded_alpha[78:220, 52:128] = 1.0

    warp_meta = warp_engine.WarpMetadata(
        engine="pants_warp_test",
        waistband_box=(52, 80, 128, 98),
        left_leg_box=(52, 98, 88, 220),
        right_leg_box=(92, 98, 128, 220),
        alpha_feather_px=2,
    )

    refined, meta = warp_engine._refine_lower_structure_overlay_mask(
        shaded_alpha,
        warp_meta=warp_meta,
        structured_pattern_lower=True,
    )

    assert meta["structured_pattern_lower"] is True
    assert meta["top_cut"] >= 70
    assert refined[64, 90] == 0.0
    assert refined[108, 90] == 1.0


def test_trim_lower_waistband_to_body_curve_removes_horizontal_smear():
    layer = np.zeros((240, 180, 4), dtype=np.uint8)
    layer[58:78, 28:164, :3] = (48, 56, 68)
    layer[58:78, 28:164, 3] = 255
    layer[74:214, 54:88, :3] = (28, 34, 46)
    layer[74:214, 54:88, 3] = 255
    layer[74:214, 92:126, :3] = (28, 34, 46)
    layer[74:214, 92:126, 3] = 255

    guides = {
        "waist_y": 84,
        "left_hip": (58, 82),
        "right_hip": (122, 84),
    }

    trimmed, meta = warp_engine._trim_lower_waistband_to_body_curve(
        Image.fromarray(layer, mode="RGBA"),
        waistband_box=(36, 60, 144, 94),
        left_leg_box=(54, 74, 88, 214),
        right_leg_box=(92, 74, 126, 214),
        guides=guides,
    )

    trimmed_np = np.asarray(trimmed)
    assert meta["applied"] is True
    assert trimmed_np[62, 36, 3] == 0
    assert trimmed_np[62, 144, 3] == 0
    assert trimmed_np[84, 72, 3] > 0
    assert trimmed_np[120, 72, 3] > 0


def test_suppress_structured_lower_top_haze_only_fades_top_rows():
    alpha = np.zeros((220, 160), dtype=np.float32)
    alpha[154:210, 40:120] = 0.92
    alpha[150:154, 40:120] = 0.12

    warp_meta = warp_engine.WarpMetadata(
        engine="pants_warp_test",
        waistband_box=(42, 142, 118, 154),
        left_leg_box=(40, 154, 78, 210),
        right_leg_box=(82, 154, 120, 210),
        alpha_feather_px=2,
    )

    out, meta = warp_engine._suppress_structured_lower_top_haze(
        alpha,
        warp_meta=warp_meta,
        structured_pattern_lower=True,
    )

    assert meta["applied"] is True
    assert out[150, 80] < 0.03
    assert out[153, 80] < alpha[153, 80]
    assert out[170, 80] > 0.85


def test_bridge_structured_lower_upper_texture_fills_missing_top_gap():
    shaded = np.zeros((220, 160, 4), dtype=np.uint8)
    for y in range(156, 214):
        shaded[y, 42:118, :3] = (32 + (y % 7), 38 + (y % 5), 48 + (y % 6))
        shaded[y, 42:118, 3] = 255
    shaded_alpha = shaded[:, :, 3].astype(np.float32) / 255.0

    ai_rgb = np.full((220, 160, 3), 238, dtype=np.float32)
    ai_rgb[144:168, 38:122, :] = (58, 62, 72)
    ai_rgb[168:214, 38:122, :] = (34, 38, 46)

    warp_meta = warp_engine.WarpMetadata(
        engine="pants_warp_test",
        waistband_box=(40, 142, 120, 166),
        left_leg_box=(42, 156, 78, 214),
        right_leg_box=(82, 156, 118, 214),
        alpha_feather_px=2,
    )
    guides = {
        "waist_y": 150,
        "left_hip": (46, 148),
        "right_hip": (114, 150),
    }

    out_rgb, out_alpha, meta = warp_engine._bridge_structured_lower_upper_texture(
        shaded,
        shaded_alpha,
        ai_rgb,
        warp_meta=warp_meta,
        guides=guides,
        structured_pattern_lower=True,
    )

    assert meta["applied"] is True
    assert out_alpha[150, 80] > 0.15
    assert out_alpha[154, 80] > 0.30
    assert out_alpha[180, 80] > 0.90
    assert float(out_rgb[150, 80, :].mean()) < 120.0


def test_build_catvton_lower_upper_shape_mask_avoids_full_width_band():
    h, w = 220, 160
    person_rgb = np.full((h, w, 3), 238, dtype=np.float32)
    ai_rgb = person_rgb.copy()
    ai_rgb[144:154, 46:114, :] = (70, 74, 82)
    ai_rgb[154:166, 40:120, :] = (52, 56, 66)
    ai_rgb[166:214, 42:118, :] = (32, 36, 44)
    ai_rgb[148:152, 12:148, :] = (230, 230, 230)

    warp_meta = warp_engine.WarpMetadata(
        engine="pants_warp_test",
        waistband_box=(42, 142, 118, 154),
        left_leg_box=(42, 156, 78, 214),
        right_leg_box=(82, 156, 118, 214),
        alpha_feather_px=2,
    )

    mask, meta = warp_engine._build_catvton_lower_upper_shape_mask(
        person_rgb,
        ai_rgb,
        warp_meta=warp_meta,
        structured_pattern_lower=True,
    )

    assert meta["applied"] is True
    assert mask[150, 80] > 0.10
    assert mask[150, 18] < 0.05
    assert mask[150, 142] < 0.05
    assert mask[160, 80] > 0.02
    assert mask[178, 80] < 0.05


def test_fill_structured_lower_upper_from_shape_mask_respects_shape_bbox():
    h, w = 220, 160
    shaded = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(156, 214):
        shaded[y, 42:118, :3] = (34 + (y % 5), 40 + (y % 4), 48 + (y % 6))
        shaded[y, 42:118, 3] = 255
    shaded_alpha = shaded[:, :, 3].astype(np.float32) / 255.0

    shape_mask = np.zeros((h, w), dtype=np.float32)
    shape_mask[146:166, 48:112] = 1.0
    shape_mask = cv2.GaussianBlur(shape_mask, (7, 7), 0)

    ai_rgb = np.full((h, w, 3), 238, dtype=np.float32)
    ai_rgb[146:166, 48:112, :] = (58, 62, 72)

    warp_meta = warp_engine.WarpMetadata(
        engine="pants_warp_test",
        waistband_box=(42, 142, 118, 154),
        left_leg_box=(42, 156, 78, 214),
        right_leg_box=(82, 156, 118, 214),
        alpha_feather_px=2,
    )

    out_rgb, out_alpha, meta = warp_engine._fill_structured_lower_upper_from_shape_mask(
        shaded,
        shaded_alpha,
        shape_mask,
        ai_rgb,
        warp_meta=warp_meta,
        structured_pattern_lower=True,
    )

    assert meta["applied"] is True
    assert out_alpha[150, 80] > 0.20
    assert out_alpha[150, 24] < 0.05
    assert float(out_rgb[150, 80, :].mean()) < 150.0


def test_lower_structure_shading_uses_ai_luminance_without_destroying_texture():
    layer = np.zeros((160, 120, 4), dtype=np.uint8)
    for y in range(18, 146):
        for x in range(34, 86):
            shade = (y * 3 + x * 2) % 24
            layer[y, x, :3] = (74 + shade, 106 + shade, 148 + shade)
            layer[y, x, 3] = 255

    ai_rgb = np.full((160, 120, 3), 182, dtype=np.float32)
    ai_rgb[18:82, 34:86, :] = 230
    ai_rgb[82:146, 34:86, :] = 118

    blend_mask = np.zeros((160, 120), dtype=np.float32)
    blend_mask[18:146, 34:86] = 1.0

    shaded, meta = warp_engine._apply_lower_luminance_shading(layer, ai_rgb, blend_mask)

    assert meta["mask_coverage"] > 0.20
    top_mean = float(shaded[28:70, 44:76, :3].mean())
    bottom_mean = float(shaded[96:138, 44:76, :3].mean())
    assert top_mean > bottom_mean + 8.0
    assert float(shaded[60, 44:76, 0].std()) > 2.0


def test_denim_lower_structure_qc_accepts_waistband_texture_false_positive():
    qc = {
        "passed": False,
        "reasons": ["waistband_texture_smear"],
        "alpha_coverage": 0.1573,
        "hem_bright_leak_score": 0.0,
        "component_count": 1,
        "largest_component_ratio": 1.0,
    }

    assert warp_engine._accept_lower_structure_qc_for_texture(qc, denim_like=True) is True
    assert warp_engine._accept_lower_structure_qc_for_texture(qc, denim_like=False) is False

    leaking = {**qc, "reasons": ["waistband_texture_smear", "hem_background_leak"]}
    assert warp_engine._accept_lower_structure_qc_for_texture(leaking, denim_like=True) is False


def test_spatial_fidelity_keeps_denim_texture_when_smear_is_accepted(tmp_path, monkeypatch):
    from app.services.tryon_v2 import pose_utils

    person_arr = np.full((240, 180, 3), 236, dtype=np.uint8)
    person_arr[28:58, 72:108] = (236, 198, 170)
    person_arr[58:220, 58:122] = (224, 184, 158)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    catvton_arr[96:224, 54:126] = (30, 30, 32)
    catvton = Image.fromarray(catvton_arr, mode="RGB")

    garment_arr = np.full((240, 180, 3), 255, dtype=np.uint8)
    for y in range(34, 220):
        shade = y % 18
        garment_arr[y, 48:82] = (86 + shade, 114 + shade, 154 + shade * 2)
        garment_arr[y, 98:132] = (86 + shade, 114 + shade, 154 + shade * 2)
    garment_arr[34:64, 42:138] = (92, 118, 156)
    garment_arr[34:220, 88:92] = (48, 68, 96)
    garment = Image.fromarray(garment_arr, mode="RGB")

    mask = Image.new("L", person.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((52, 96, 128, 226), fill=255)
    mask.save(tmp_path / "08_mask_resized.png")

    def fake_pants_layer(**_kwargs):
        layer = np.zeros((240, 180, 4), dtype=np.uint8)
        for y in range(96, 226):
            shade = y % 18
            layer[y, 56:84, :3] = (84 + shade, 112 + shade, 150 + shade * 2)
            layer[y, 56:84, 3] = 255
            layer[y, 96:124, :3] = (84 + shade, 112 + shade, 150 + shade * 2)
            layer[y, 96:124, 3] = 255
        layer[96:114, 52:128, :3] = (90, 116, 152)
        layer[96:114, 52:128, 3] = 255
        meta = warp_engine.WarpMetadata(
            engine="pants_warp_test",
            waistband_box=(52, 96, 128, 114),
            left_leg_box=(56, 114, 84, 226),
            right_leg_box=(96, 114, 124, 226),
            alpha_feather_px=2,
        )
        return Image.fromarray(layer, mode="RGBA"), meta

    def fake_qc(_layer_np, *, lower_warp_meta=None):
        assert lower_warp_meta is not None
        return {
            "passed": False,
            "reasons": ["waistband_texture_smear"],
            "alpha_coverage": 0.1573,
            "hem_bright_leak_score": 0.0,
            "component_count": 1,
            "largest_component_ratio": 1.0,
        }

    monkeypatch.setattr(warp_engine, "detect_pose_keypoints", lambda _image: {})
    monkeypatch.setattr(pose_utils, "detect_pose_keypoints", lambda _image: {})
    monkeypatch.setattr(
        pose_utils,
        "get_body_bounds_from_keypoints",
        lambda _kpts, _w, _h, _category: {},
    )
    monkeypatch.setattr(warp_engine, "_build_pants_warp_layer", fake_pants_layer)
    monkeypatch.setattr(warp_engine, "_assess_lower_warp_layer_qc", fake_qc)

    result, meta = warp_engine.catvton_color_fidelity_spatial(
        catvton_result=catvton,
        original_garment=garment,
        person_image=person,
        garment_category="bottom",
        fidelity_strength=0.75,
        debug_session_dir=str(tmp_path),
    )

    assert result.size == person.size
    assert meta["lower_conservative_color_only"] is True
    assert meta["lower_texture_qc_accepted"] is True

    fidelity_allowed = json.loads((tmp_path / "12b_fidelity_allowed.json").read_text("utf-8"))
    strength = json.loads((tmp_path / "12c_strength.json").read_text("utf-8"))

    assert fidelity_allowed["coverage"] > 0.01
    assert strength["mean"] > 0.0


def test_lower_structure_strong_pattern_uses_stronger_overlay_than_denim(tmp_path, monkeypatch):
    person = Image.new("RGB", (200, 240), (236, 236, 236))
    catvton = person.copy()
    garment_arr = np.full((240, 160, 3), 255, dtype=np.uint8)
    garment_arr[24:214, 38:122] = (28, 34, 46)
    for x in range(38, 122, 7):
        garment_arr[24:214, x : x + 1] = (106, 112, 122)
    for y in range(24, 214, 8):
        garment_arr[y : y + 1, 38:122] = (106, 112, 122)
    garment_arr[24:44, 34:126] = (232, 232, 236)
    garment = Image.fromarray(garment_arr, mode="RGB")

    def fake_pants_layer(**_kwargs):
        layer = np.zeros((240, 200, 4), dtype=np.uint8)
        layer[58:214, 58:94, :3] = (28, 34, 46)
        layer[58:214, 58:94, 3] = 255
        layer[58:214, 106:142, :3] = (28, 34, 46)
        layer[58:214, 106:142, 3] = 255
        for x in range(58, 142, 7):
            layer[58:214, x : x + 1, :3] = (106, 112, 122)
            layer[58:214, x : x + 1, 3] = 255
        for y in range(58, 214, 8):
            layer[y : y + 1, 58:142, :3] = (106, 112, 122)
            layer[y : y + 1, 58:142, 3] = 255
        meta = warp_engine.WarpMetadata(
            engine="pants_warp_test",
            waistband_box=(0, 0, 0, 0),
            left_leg_box=(58, 58, 94, 214),
            right_leg_box=(106, 58, 142, 214),
            alpha_feather_px=2,
        )
        return Image.fromarray(layer, mode="RGBA"), meta

    monkeypatch.setattr(warp_engine, "_build_pants_warp_layer", fake_pants_layer)
    monkeypatch.setattr(
        warp_engine,
        "_assess_lower_warp_layer_qc",
        lambda *_args, **_kwargs: {
            "passed": True,
            "reasons": [],
            "alpha_coverage": 0.16,
            "hem_bright_leak_score": 0.0,
            "component_count": 1,
            "largest_component_ratio": 1.0,
        },
    )

    result, meta = warp_engine.tryon_lower_structure_preserve(
        person_image=person,
        garment_image=garment,
        catvton_result=catvton,
        debug_session_dir=str(tmp_path),
    )

    assert result.size == person.size
    assert meta["lower_denim_like"] is False
    assert meta["strong_pattern_lower"] is True
    assert meta["structured_pattern_lower"] is True
    assert meta["drape_alpha"] > 0.18


def test_lower_structure_accepts_structured_pattern_waistband_smear_override(tmp_path, monkeypatch):
    person = Image.new("RGB", (200, 240), (236, 236, 236))
    catvton = person.copy()
    garment_arr = np.full((240, 160, 3), 255, dtype=np.uint8)
    garment_arr[24:214, 38:122] = (28, 34, 46)
    for x in range(38, 122, 7):
        garment_arr[24:214, x : x + 1] = (106, 112, 122)
    for y in range(24, 214, 8):
        garment_arr[y : y + 1, 38:122] = (106, 112, 122)
    garment_arr[24:44, 34:126] = (232, 232, 236)
    garment = Image.fromarray(garment_arr, mode="RGB")

    def fake_pants_layer(**_kwargs):
        layer = np.zeros((240, 200, 4), dtype=np.uint8)
        layer[54:214, 60:96, :3] = (28, 34, 46)
        layer[54:214, 60:96, 3] = 255
        layer[54:214, 104:140, :3] = (28, 34, 46)
        layer[54:214, 104:140, 3] = 255
        for x in range(60, 140, 7):
            layer[54:214, x : x + 1, :3] = (106, 112, 122)
            layer[54:214, x : x + 1, 3] = 255
        for y in range(54, 214, 8):
            layer[y : y + 1, 60:140, :3] = (106, 112, 122)
            layer[y : y + 1, 60:140, 3] = 255
        meta = warp_engine.WarpMetadata(
            engine="pants_warp_test",
            waistband_box=(0, 0, 0, 0),
            left_leg_box=(60, 54, 96, 214),
            right_leg_box=(104, 54, 140, 214),
            alpha_feather_px=2,
        )
        return Image.fromarray(layer, mode="RGBA"), meta

    monkeypatch.setattr(warp_engine, "_build_pants_warp_layer", fake_pants_layer)
    monkeypatch.setattr(
        warp_engine,
        "_assess_lower_warp_layer_qc",
        lambda *_args, **_kwargs: {
            "passed": False,
            "reasons": ["waistband_texture_smear"],
            "alpha_coverage": 0.16,
            "hem_bright_leak_score": 0.0,
            "component_count": 1,
            "largest_component_ratio": 1.0,
        },
    )

    result, meta = warp_engine.tryon_lower_structure_preserve(
        person_image=person,
        garment_image=garment,
        catvton_result=catvton,
        debug_session_dir=str(tmp_path),
    )

    assert result.size == person.size
    assert meta["lower_warp_qc_accepted"] is True
    assert meta["structured_pattern_qc_override"] is True
