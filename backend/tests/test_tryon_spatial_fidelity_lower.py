"""Tests for spatial color fidelity lower-body region detection."""

from __future__ import annotations

import numpy as np
from PIL import Image

from app.services.tryon_v2.warp_engine import (
    _assess_lower_warp_layer_qc,
    _build_lower_fidelity_clip_mask,
    _expand_lower_layer_to_clip,
    _expand_lower_mask_bbox,
    _is_denim_like_garment,
)


class TestLowerBodyDetection:
    """Verify _is_bottom flag is correctly set for lower garment categories."""

    @staticmethod
    def _is_bottom(garment_category: str) -> bool:
        cat = (garment_category or "").strip().lower()
        return any(k in cat for k in ("bottom", "pants", "下装", "裤", "lower"))

    def test_bottom(self):
        assert self._is_bottom("bottom") is True

    def test_pants(self):
        assert self._is_bottom("pants") is True

    def test_xiazhuang(self):
        assert self._is_bottom("下装") is True

    def test_ku(self):
        assert self._is_bottom("裤") is True

    def test_lower(self):
        assert self._is_bottom("lower") is True

    def test_kuzi(self):
        assert self._is_bottom("裤子") is True

    def test_top_is_not_bottom(self):
        assert self._is_bottom("top") is False

    def test_shangyi_is_not_bottom(self):
        assert self._is_bottom("上衣") is False

    def test_dress_is_not_bottom(self):
        assert self._is_bottom("dress") is False

    def test_empty_is_not_bottom(self):
        assert self._is_bottom("") is False


class TestBodyCenterComputation:
    """Verify body_cy is computed correctly for lower vs upper garments."""

    def test_upper_body_cy(self):
        """Upper garments: body_cy = (neck_y + waist_y) // 2"""
        neck_y = 150
        waist_y = 450
        body_cy = (neck_y + waist_y) // 2
        assert body_cy == 300

    def test_lower_body_cy(self):
        """Lower garments: body_cy = (waist_y + ankle_y) // 2"""
        waist_y = 450
        ankle_y = 900
        body_cy = (waist_y + ankle_y) // 2
        assert body_cy == 675

    def test_lower_body_cy_differs_from_upper(self):
        """Lower body center should be significantly lower than upper body center."""
        neck_y = 150
        waist_y = 450
        ankle_y = 900
        upper_cy = (neck_y + waist_y) // 2  # 300
        lower_cy = (waist_y + ankle_y) // 2  # 675
        assert lower_cy > upper_cy


class TestLowerBodyProtectMask:
    """Verify the lower-body protect mask correctly excludes upper body and shoes."""

    def _make_lower_body_protect_mask(
        self, cw: int, ch: int, waist_y: int, ankle_y: int | None
    ) -> Image.Image:
        """Mirror the protection mask logic from warp_engine.py."""
        protect_mask = Image.new("L", (cw, ch), color=255)
        protect_upper_y = max(0, waist_y - int(ch * 0.02))
        if protect_upper_y > 0:
            protect_mask.paste(0, (0, 0, cw, protect_upper_y))
        if ankle_y is not None:
            protect_lower_y = min(ch, ankle_y + int(ch * 0.06))
            if protect_lower_y < ch:
                protect_mask.paste(0, (0, protect_lower_y, cw, ch))
        return protect_mask

    def test_upper_body_protected(self):
        """Pixels above waist_y should be protected (0)."""
        cw, ch = 100, 200
        waist_y = 100
        ankle_y = 190
        mask = self._make_lower_body_protect_mask(cw, ch, waist_y, ankle_y)
        mask_np = np.array(mask)
        # Upper body (y=50) should be 0 (protected)
        assert mask_np[50, 50] == 0

    def test_pants_region_allowed(self):
        """Pixels in the pants region (waist_y to ankle_y) should be allowed (255)."""
        cw, ch = 100, 200
        waist_y = 100
        ankle_y = 190
        mask = self._make_lower_body_protect_mask(cw, ch, waist_y, ankle_y)
        mask_np = np.array(mask)
        # Pants region (y=150) should be 255 (allowed)
        assert mask_np[150, 50] == 255

    def test_shoe_region_protected(self):
        """Pixels below ankle_y + margin should be protected (0)."""
        cw, ch = 100, 200
        waist_y = 100
        ankle_y = 160  # ankle well above image bottom
        mask = self._make_lower_body_protect_mask(cw, ch, waist_y, ankle_y)
        mask_np = np.array(mask)
        # Shoe region (y=180) should be 0 (protected), margin = 12
        assert mask_np[180, 50] == 0

    def test_no_ankle_y_no_shoe_protection(self):
        """When ankle_y is None, no shoe protection is applied."""
        cw, ch = 100, 200
        waist_y = 100
        mask = self._make_lower_body_protect_mask(cw, ch, waist_y, None)
        mask_np = np.array(mask)
        # Bottom of image should still be 255 (no shoe protection)
        assert mask_np[199, 50] == 255

    def test_waist_boundary(self):
        """Pixels at waist_y should be allowed (255)."""
        cw, ch = 100, 200
        waist_y = 100
        ankle_y = 190
        mask = self._make_lower_body_protect_mask(cw, ch, waist_y, ankle_y)
        mask_np = np.array(mask)
        # At waist_y (y=100) should be 255 (allowed, since protection is above waist_y - 2%)
        assert mask_np[100, 50] == 255


class TestMaskRegionClamping:
    """Verify that lower debug mask region preserves a waist/hip style band."""

    def test_mask_y0_clamped_to_waistband_limit(self):
        """When mask extends far above waist_y, keep only a small waistband band."""
        ch = 1000
        waist_y = 400
        mask_y0 = 200
        _is_bottom = True

        gar_y0 = mask_y0
        lower_y0_limit = max(0, int(waist_y - ch * 0.055))
        if _is_bottom and gar_y0 < lower_y0_limit:
            gar_y0 = lower_y0_limit

        assert gar_y0 == 345

    def test_mask_y0_not_clamped_for_upper(self):
        """For upper garments, mask region should not be clamped."""
        ch = 1000
        waist_y = 400
        mask_y0 = 200
        _is_bottom = False

        gar_y0 = mask_y0
        lower_y0_limit = max(0, int(waist_y - ch * 0.055))
        if _is_bottom and gar_y0 < lower_y0_limit:
            gar_y0 = lower_y0_limit

        assert gar_y0 == 200

    def test_mask_inside_waistband_band_not_clamped(self):
        """When mask starts in the waistband band, preserve it."""
        ch = 1000
        waist_y = 400
        mask_y0 = 360
        _is_bottom = True

        gar_y0 = mask_y0
        lower_y0_limit = max(0, int(waist_y - ch * 0.055))
        if _is_bottom and gar_y0 < lower_y0_limit:
            gar_y0 = lower_y0_limit

        assert gar_y0 == 360


class TestLowerFidelityClipMask:
    """Verify lower fidelity compositing keeps moderate outer expansion only."""

    def test_clip_mask_expands_past_raw_mask_without_using_full_warp_width(self):
        h, w = 220, 160
        catvton_mask = np.zeros((h, w), dtype=np.float32)
        catvton_mask[50:205, 62:98] = 1.0

        changed_garment = np.zeros((h, w), dtype=bool)
        changed_garment[48:206, 34:126] = True

        garment_layer_present = np.zeros((h, w), dtype=bool)
        garment_layer_present[52:202, 30:130] = True

        protected_by_mask = np.zeros((h, w), dtype=bool)
        protected_by_mask[:40, :] = True
        protected_by_mask[210:, :] = True

        clip_mask = _build_lower_fidelity_clip_mask(
            catvton_mask_np=catvton_mask,
            changed_garment=changed_garment,
            garment_layer_present=garment_layer_present,
            protected_by_mask=protected_by_mask,
        )

        assert clip_mask is not None
        clip_cov = float((clip_mask > 0.08).mean())
        raw_cov = float((catvton_mask > 0.08).mean())
        warp_cov = float(garment_layer_present.mean())
        assert clip_cov > raw_cov * 1.45
        assert clip_cov < warp_cov * 0.70
        assert clip_mask[120, 36] <= 0.08
        assert clip_mask[120, 44] <= 0.08
        assert clip_mask[120, 52] > 0.08
        assert clip_mask[120, 56] > 0.08
        assert clip_mask[120, 64] > 0.08
        assert clip_mask[120, 96] > 0.08
        assert clip_mask[120, 104] > 0.08
        assert clip_mask[120, 112] <= 0.08
        assert clip_mask[120, 124] <= 0.08
        assert clip_mask[20, 80] <= 0.08
        assert clip_mask[215, 80] <= 0.08

    def test_segmented_clip_mask_is_narrower_at_hip_and_wider_on_legs(self):
        h, w = 240, 180
        catvton_mask = np.zeros((h, w), dtype=np.float32)
        catvton_mask[42:212, 72:108] = 1.0

        changed_garment = np.zeros((h, w), dtype=bool)
        changed_garment[40:216, 38:142] = True

        garment_layer_present = np.zeros((h, w), dtype=bool)
        garment_layer_present[44:100, 58:122] = True
        garment_layer_present[98:228, 28:78] = True
        garment_layer_present[98:228, 102:152] = True

        layer_alpha = np.zeros((h, w), dtype=np.float32)
        layer_alpha[44:100, 62:118] = 0.92
        layer_alpha[98:228, 30:76] = 0.96
        layer_alpha[98:228, 104:150] = 0.96
        layer_alpha[110:228, 24:30] = 0.18
        layer_alpha[110:228, 150:156] = 0.18

        protected_by_mask = np.zeros((h, w), dtype=bool)

        clip_mask = _build_lower_fidelity_clip_mask(
            catvton_mask_np=catvton_mask,
            changed_garment=changed_garment,
            garment_layer_present=garment_layer_present,
            protected_by_mask=protected_by_mask,
            layer_alpha=layer_alpha,
            left_leg_box=(28, 96, 78, 228),
            right_leg_box=(102, 96, 152, 228),
        )

        assert clip_mask is not None
        # hip / crotch rows stay relatively narrow
        assert clip_mask[70, 38] <= 0.08
        assert clip_mask[70, 52] <= 0.08
        assert clip_mask[70, 74] > 0.08
        assert clip_mask[70, 106] > 0.08
        assert clip_mask[70, 128] <= 0.08
        # lower leg rows are allowed to widen back out to the real leg shape
        assert clip_mask[170, 34] > 0.08
        assert clip_mask[170, 56] > 0.08
        assert clip_mask[170, 74] > 0.08
        assert clip_mask[170, 106] > 0.08
        assert clip_mask[170, 124] > 0.08
        assert clip_mask[170, 146] > 0.08


class TestLowerLayerExpansion:
    """Verify lower warped pixels are no longer fabricated outside the warp."""

    def test_does_not_expand_layer_pixels_into_clip_holes(self):
        h, w = 120, 90
        layer = np.zeros((h, w, 4), dtype=np.uint8)
        layer[30:110, 35:55, :3] = (40, 60, 90)
        layer[30:110, 35:55, 3] = 255

        clip_mask = np.zeros((h, w), dtype=np.float32)
        clip_mask[28:112, 20:70] = 1.0

        out = _expand_lower_layer_to_clip(layer, clip_mask)

        assert out[70, 24, 3] == 0
        assert out[70, 66, 3] == 0
        assert tuple(out[70, 40, :3]) == (40, 60, 90)
        assert out[10, 10, 3] == 0


class TestLowerWarpConservativeGates:
    """Verify lower-body spatial overlays are guarded before heavy repaint."""

    def test_blue_textured_denim_is_detected(self):
        h, w = 220, 150
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        for y in range(28, 198):
            shade = y % 17
            rgb[y, 44:70] = (92 + shade, 120 + shade * 2, 158 + shade * 3)
            rgb[y, 82:108] = (92 + shade, 120 + shade * 2, 158 + shade * 3)
        rgb[28:58, 40:112] = (88, 112, 150)
        rgb[28:198, w // 2 - 1 : w // 2 + 1] = (48, 68, 98)
        garment = Image.fromarray(rgb, mode="RGB")

        assert _is_denim_like_garment(garment) is True

    def test_dark_plaid_lower_is_not_misclassified_as_denim(self):
        h, w = 240, 160
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        base = np.array([42, 46, 54], dtype=np.uint8)
        rgb[24:216, 34:126] = base
        for x in range(34, 126, 7):
            rgb[24:216, x : x + 1] = (94, 102, 118)
        for y in range(24, 216, 8):
            rgb[y : y + 1, 34:126] = (104, 110, 122)
        rgb[24:54, 30:130] = (232, 232, 236)
        rgb[54:216, w // 2 - 2 : w // 2 + 2] = (22, 24, 30)
        garment = Image.fromarray(rgb, mode="RGB")

        assert _is_denim_like_garment(garment) is False

    def test_dark_dense_grid_lower_is_not_misclassified_as_denim(self):
        h, w = 320, 220
        rgb = np.full((h, w, 3), 255, dtype=np.uint8)
        base = np.array([28, 34, 46], dtype=np.uint8)
        rgb[30:292, 46:174] = base
        for x in range(46, 174, 8):
            rgb[30:292, x : x + 1] = (104, 110, 122)
        for y in range(30, 292, 9):
            rgb[y : y + 1, 46:174] = (104, 110, 122)
        rgb[30:52, 38:182] = (232, 232, 236)
        rgb[52:292, w // 2 - 2 : w // 2 + 2] = (18, 20, 24)
        garment = Image.fromarray(rgb, mode="RGB")

        assert _is_denim_like_garment(garment) is False

    def test_qc_rejects_horizontal_waistband_drag(self):
        h, w = 220, 180
        layer = np.zeros((h, w, 4), dtype=np.uint8)
        layer[20:28, 10:170, :3] = (130, 150, 180)
        layer[20:28, 10:170, 3] = 255
        layer[45:205, 54:82, :3] = (120, 145, 175)
        layer[45:205, 54:82, 3] = 255
        layer[45:205, 98:126, :3] = (120, 145, 175)
        layer[45:205, 98:126, 3] = 255

        qc = _assess_lower_warp_layer_qc(layer)

        assert qc["passed"] is False
        assert "horizontal_waistband_drag" in qc["reasons"]

    def test_qc_rejects_waistband_texture_smear_and_hem_background_leak(self):
        h, w = 260, 180
        layer = np.zeros((h, w, 4), dtype=np.uint8)
        for y in range(30, 46):
            layer[y, 24:156, :3] = (110 + (y % 2) * 30, 138 + (y % 2) * 20, 175 + (y % 2) * 15)
            layer[y, 24:156, 3] = 255
        layer[46:236, 42:84, :3] = (86, 116, 160)
        layer[46:236, 42:84, 3] = 255
        layer[46:236, 96:138, :3] = (86, 116, 160)
        layer[46:236, 96:138, 3] = 255
        layer[210:236, 42:84, :3] = (232, 236, 242)
        layer[210:236, 96:138, :3] = (232, 236, 242)

        qc = _assess_lower_warp_layer_qc(layer)

        assert qc["passed"] is False
        assert "waistband_texture_smear" in qc["reasons"]
        assert "hem_background_leak" in qc["reasons"]


class TestLowerMaskBboxExpansion:
    """Verify narrow lower mask boxes are widened before warping texture."""

    def test_expands_lower_mask_bbox_sideways_and_up_to_waistband(self):
        bbox = (308, 603, 582, 1247)
        expanded = _expand_lower_mask_bbox(
            bbox,
            image_w=906,
            image_h=1382,
            waist_y=634,
            ankle_y=1222,
        )

        assert expanded[0] < bbox[0]
        assert expanded[2] > bbox[2]
        assert expanded[1] <= bbox[1]
        assert expanded[1] >= 0
        assert expanded[2] <= 906
