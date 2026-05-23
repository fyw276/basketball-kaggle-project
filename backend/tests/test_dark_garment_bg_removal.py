"""
Tests for dark garment background removal.

Verifies that `_border_connected_background_mask` does NOT erase dark garments
when rembg alpha is available (the real-world scenario).

Bug: The `dark_border` broad-sweep (`channel_max < 70 & channel_span < 42`)
marks all dark pixels — including the garment — as background candidates.
Fix: When alpha from rembg indicates the garment is already segmented
(border alpha is transparent), skip the dark_border sweep.
"""

import numpy as np
import pytest
from PIL import Image

from app.services.garment_preprocess import _border_connected_background_mask as gp_border_mask_nd
from app.services.tryon_v2.garment_struct import _border_connected_background_mask as gs_border_mask


def _gp_border_mask(img: Image.Image, alpha: np.ndarray | None = None) -> np.ndarray:
    """Wrapper: garment_preprocess version expects np.ndarray, not PIL Image."""
    return gp_border_mask_nd(np.asarray(img.convert("RGB"), dtype=np.uint8), alpha=alpha)


def _make_garment_with_alpha(
    img_size: int = 256,
    garment_rect: tuple = (64, 64, 192, 192),
    garment_color: tuple = (15, 15, 15),
    bg_color: tuple = (30, 30, 30),
) -> tuple[Image.Image, np.ndarray]:
    """Simulate rembg output: garment with alpha mask.

    Returns (RGB image, alpha array) where:
    - alpha=0 for background (rembg segmented as non-garment)
    - alpha=255 for garment (rembg segmented as garment)
    """
    arr = np.full((img_size, img_size, 3), bg_color, dtype=np.uint8)
    alpha = np.zeros((img_size, img_size), dtype=np.uint8)
    x0, y0, x1, y1 = garment_rect
    arr[y0:y1, x0:x1] = garment_color
    alpha[y0:y1, x0:x1] = 255
    return Image.fromarray(arr), alpha


class TestDarkGarmentWithAlpha:
    """Dark garment on dark background — must be protected when alpha is available."""

    @pytest.mark.parametrize(
        "mask_fn, module",
        [
            (gs_border_mask, "garment_struct"),
            (_gp_border_mask, "garment_preprocess"),
        ],
    )
    def test_dark_garment_on_dark_bg_with_alpha_preserved(self, mask_fn, module):
        """Black garment on dark background with rembg alpha must not be erased.

        Before fix: coverage ≈ 1.0 (garment + bg both removed).
        After fix:  alpha guard skips dark_border sweep, garment preserved.
        """
        img, alpha = _make_garment_with_alpha(garment_color=(15, 15, 15), bg_color=(30, 30, 30))
        mask = mask_fn(img, alpha=alpha)
        coverage = float(mask.mean())
        assert (
            coverage < 0.50
        ), f"[{module}] coverage={coverage:.3f} — dark garment erased despite alpha guard"

    @pytest.mark.parametrize(
        "mask_fn, module",
        [
            (gs_border_mask, "garment_struct"),
            (_gp_border_mask, "garment_preprocess"),
        ],
    )
    def test_dark_garment_center_preserved_with_alpha(self, mask_fn, module):
        """Garment center must NOT be marked as background when alpha is present."""
        img, alpha = _make_garment_with_alpha(garment_color=(15, 15, 15), bg_color=(30, 30, 30))
        mask = mask_fn(img, alpha=alpha)
        assert not mask[128, 128], f"[{module}] garment center (128,128) marked as background"

    @pytest.mark.parametrize(
        "mask_fn, module",
        [
            (gs_border_mask, "garment_struct"),
            (_gp_border_mask, "garment_preprocess"),
        ],
    )
    def test_dark_garment_texture_preserved_with_alpha(self, mask_fn, module):
        """Dark garment with texture on dark bg must preserve interior with alpha."""
        np.random.seed(42)
        rgb = np.full((256, 256, 3), (35, 35, 35), dtype=np.uint8)
        garment = np.random.randint(10, 30, (128, 128, 3), dtype=np.uint8)
        rgb[64:192, 64:192] = garment
        alpha = np.zeros((256, 256), dtype=np.uint8)
        alpha[64:192, 64:192] = 255
        img = Image.fromarray(rgb)

        mask = mask_fn(img, alpha=alpha)
        interior = mask[80:176, 80:176]
        assert (
            float(interior.mean()) < 0.30
        ), f"[{module}] garment interior coverage={float(interior.mean()):.3f}"


class TestWhiteBackgroundBlackGarment:
    """Black garment on white background — light_border path must not erase garment."""

    @pytest.mark.parametrize(
        "mask_fn, module",
        [
            (gs_border_mask, "garment_struct"),
            (_gp_border_mask, "garment_preprocess"),
        ],
    )
    def test_white_bg_black_garment_works_correctly(self, mask_fn, module):
        """Black garment on white bg: background removed, garment preserved."""
        arr = np.full((256, 256, 3), 245, dtype=np.uint8)
        arr[64:192, 64:192] = (10, 10, 10)
        img = Image.fromarray(arr)
        mask = mask_fn(img)
        coverage = float(mask.mean())
        assert (
            coverage > 0.30
        ), f"[{module}] white background not detected (coverage={coverage:.3f})"
        assert not mask[128, 128], f"[{module}] garment center erased on white background"

    def test_gs_black_on_white_with_alpha(self):
        """garment_struct: black garment on white bg with alpha preserves garment."""
        img, alpha = _make_garment_with_alpha(garment_color=(15, 15, 15), bg_color=(245, 245, 245))
        mask = gs_border_mask(img, alpha=alpha)
        assert not mask[128, 128], "garment center marked as background"
        interior = mask[60:196, 60:196]
        assert (
            float(interior.mean()) < 0.15
        ), f"garment interior coverage={float(interior.mean()):.3f}"

    def test_gp_black_on_white_with_alpha(self):
        """garment_preprocess: black garment on white bg with alpha preserves garment."""
        img, alpha = _make_garment_with_alpha(garment_color=(15, 15, 15), bg_color=(245, 245, 245))
        rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
        mask = gp_border_mask_nd(rgb, alpha=alpha)
        assert not mask[128, 128], "garment center marked as background"
        interior = mask[60:196, 60:196]
        assert (
            float(interior.mean()) < 0.15
        ), f"garment interior coverage={float(interior.mean()):.3f}"


class TestDarkBackgroundCleanup:
    """Without alpha, dark_border sweep must still clean actual dark backgrounds."""

    def test_white_garment_on_dark_bg_cleaned_without_alpha(self):
        """White garment on dark bg: dark_border sweep should clean the background."""
        arr = np.full((256, 256, 3), (30, 30, 30), dtype=np.uint8)
        arr[64:192, 64:192] = (220, 220, 220)
        img = Image.fromarray(arr)
        mask = gs_border_mask(img)
        coverage = float(mask.mean())
        assert coverage > 0.50, f"coverage={coverage:.3f} — dark background not cleaned"
        assert not mask[128, 128], "light garment center erased"


class TestAlphaGuardDetails:
    """Detailed alpha guard behavior tests."""

    def test_alpha_guard_skips_dark_border_sweep(self):
        """With alpha, dark_border sweep is skipped; without alpha, it runs."""
        rgb = np.full((256, 256, 3), (35, 35, 35), dtype=np.uint8)
        rgb[64:192, 64:192] = (15, 15, 15)
        alpha = np.zeros((256, 256), dtype=np.uint8)
        alpha[64:192, 64:192] = 255
        img = Image.fromarray(rgb)

        mask_with = gs_border_mask(img, alpha=alpha)
        mask_without = gs_border_mask(img)

        # Without alpha: garment gets erased
        assert (
            float(mask_without.mean()) > 0.80
        ), "sanity check: without alpha guard, coverage should be high"
        # With alpha: garment protected
        assert (
            float(mask_with.mean()) < 0.50
        ), f"with alpha guard, coverage={float(mask_with.mean()):.3f}"
