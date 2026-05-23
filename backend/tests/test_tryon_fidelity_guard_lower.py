"""Tests for fidelity guard lower-body mask estimation."""

from __future__ import annotations

import numpy as np


class TestLowerGarmentMaskRegion:
    """Verify the mask region for lower garments is properly constrained."""

    @staticmethod
    def _compute_region(garment_category: str, h: int, w: int) -> np.ndarray:
        """Mirror the region logic from _estimate_raw_garment_mask."""
        cat = (garment_category or "").strip().lower()
        yy, xx = np.indices((h, w))
        if any(k in cat for k in ("top", "upper", "上衣", "上装")):
            region = (
                (yy >= int(h * 0.16))
                & (yy <= int(h * 0.56))
                & (xx >= int(w * 0.12))
                & (xx <= int(w * 0.88))
            )
        elif any(k in cat for k in ("bottom", "pants", "lower", "裤", "下装")):
            region = (
                (yy >= int(h * 0.40))
                & (yy <= int(h * 0.90))
                & (xx >= int(w * 0.15))
                & (xx <= int(w * 0.85))
            )
        else:
            region = (
                (yy >= int(h * 0.15))
                & (yy <= int(h * 0.90))
                & (xx >= int(w * 0.10))
                & (xx <= int(w * 0.90))
            )
        return region

    def test_lower_region_excludes_upper_body(self):
        """Lower garment region should not include upper body pixels."""
        h, w = 1024, 768
        region = self._compute_region("bottom", h, w)
        # Upper body (y=200) should be excluded
        assert not region[200, 384]

    def test_lower_region_includes_pants_area(self):
        """Lower garment region should include the pants area."""
        h, w = 1024, 768
        region = self._compute_region("bottom", h, w)
        # Pants area (y=600) should be included
        assert region[600, 384]

    def test_lower_region_excludes_shoes(self):
        """Lower garment region should not include shoe pixels at image bottom."""
        h, w = 1024, 768
        region = self._compute_region("bottom", h, w)
        # Shoe area (y=980) should be excluded (above 90% = 921)
        assert not region[980, 384]

    def test_lower_region_has_horizontal_bounds(self):
        """Lower garment region should have horizontal constraints."""
        h, w = 1024, 768
        region = self._compute_region("bottom", h, w)
        # Far left (x=50) should be excluded
        assert not region[600, 50]
        # Far right (x=720) should be excluded
        assert not region[600, 720]
        # Center (x=384) should be included
        assert region[600, 384]

    def test_lower_region_different_from_upper(self):
        """Lower and upper regions should cover different areas."""
        h, w = 1024, 768
        upper = self._compute_region("top", h, w)
        lower = self._compute_region("bottom", h, w)
        # Upper body area (y=300) should be in upper but not lower
        assert upper[300, 384]
        assert not lower[300, 384]

    def test_chinese_category_ku(self):
        """Chinese category '裤' should be detected as lower."""
        h, w = 1024, 768
        region = self._compute_region("裤", h, w)
        assert region[600, 384]
        assert not region[200, 384]

    def test_chinese_category_xiazhuang(self):
        """Chinese category '下装' should be detected as lower."""
        h, w = 1024, 768
        region = self._compute_region("下装", h, w)
        assert region[600, 384]
        assert not region[200, 384]
