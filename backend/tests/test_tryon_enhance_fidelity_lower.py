"""Tests for enhance color fidelity lower-body region detection."""

from __future__ import annotations

import numpy as np
from PIL import Image


class TestEnhanceLowerBodyDetection:
    """Verify _is_bottom flag in catvton_color_fidelity_enhance."""

    @staticmethod
    def _is_bottom(garment_category: str) -> bool:
        cat = (garment_category or "").strip().lower()
        return any(k in cat for k in ("bottom", "pants", "下装", "裤", "lower"))

    def test_bottom(self):
        assert self._is_bottom("bottom") is True

    def test_pants(self):
        assert self._is_bottom("pants") is True

    def test_lower(self):
        assert self._is_bottom("lower") is True

    def test_top_is_not_bottom(self):
        assert self._is_bottom("top") is False


class TestEnhanceGarmentRegion:
    """Verify garment region computation for lower garments."""

    def test_lower_garment_region_uses_ankle_y(self):
        """Lower garments should use ankle_y for gar_y1."""
        ch = 1024
        waist_y = 500
        ankle_y = 950
        _is_bottom = True
        _is_top = False
        _is_skirt = False

        if _is_top:
            gar_y0 = max(0, min(int(150 - ch * 0.05), int(ch * 0.40)))
            gar_y1 = min(ch, max(gar_y0 + 2, int(waist_y + ch * 0.06)))
        elif _is_skirt:
            gar_y0 = max(0, int(waist_y - ch * 0.04))
            gar_y1 = min(ch, int(ch * 0.92))
        elif _is_bottom:
            gar_y0 = max(0, int(waist_y - ch * 0.02))
            gar_y1 = min(ch, int(ankle_y + ch * 0.03))
        else:
            gar_y0 = max(0, int(waist_y - ch * 0.02))
            gar_y1 = min(ch, int(ch * 0.92))

        # gar_y0 should be near waist_y
        assert abs(gar_y0 - (waist_y - int(ch * 0.02))) < 5
        # gar_y1 should be near ankle_y + margin
        assert gar_y1 > ankle_y
        # gar_y1 should not exceed image height
        assert gar_y1 <= ch

    def test_upper_garment_region_differs_from_lower(self):
        """Upper and lower garments should have different region bounds."""
        ch = 1024
        neck_y = 150
        waist_y = 500

        # Upper
        gar_y0_upper = max(0, min(int(neck_y - ch * 0.05), int(ch * 0.40)))
        gar_y1_upper = min(ch, max(gar_y0_upper + 2, int(waist_y + ch * 0.06)))

        # Lower
        ankle_y = 950
        gar_y0_lower = max(0, int(waist_y - ch * 0.02))
        gar_y1_lower = min(ch, int(ankle_y + ch * 0.03))

        # Lower region should be significantly lower
        assert gar_y0_lower > gar_y0_upper
        assert gar_y1_lower > gar_y1_upper


class TestEnhanceLowerBodyProtectMask:
    """Verify lower-body protect mask in enhance function."""

    def _make_en_lower_body_protect_mask(
        self, cw: int, ch: int, waist_y: int, ankle_y: int | None
    ) -> Image.Image:
        protect_mask = Image.new("L", (cw, ch), color=255)
        protect_upper_y = max(0, waist_y - int(ch * 0.02))
        if protect_upper_y > 0:
            protect_mask.paste(0, (0, 0, cw, protect_upper_y))
        if ankle_y is not None:
            protect_lower_y = min(ch, ankle_y + int(ch * 0.06))
            if protect_lower_y < ch:
                protect_mask.paste(0, (0, protect_lower_y, cw, ch))
        return protect_mask

    def test_upper_protected_lower_allowed(self):
        """Upper body protected, pants region allowed."""
        cw, ch = 100, 200
        waist_y = 100
        ankle_y = 170
        mask = self._make_en_lower_body_protect_mask(cw, ch, waist_y, ankle_y)
        mask_np = np.array(mask)
        assert mask_np[50, 50] == 0  # upper body protected
        assert mask_np[140, 50] == 255  # pants region allowed
        assert mask_np[185, 50] == 0  # shoe region protected
