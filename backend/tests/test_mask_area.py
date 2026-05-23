"""
Tests for mask_area_ratio threshold in garment preprocessing.

Verifies that after morphological operations (CLOSE + dilate) and auto bbox expansion,
the mask occupies at least 12% of the original image area.
"""

import numpy as np
from PIL import Image

from app.services.garment_preprocess import preprocess_garment


class TestMaskAreaRatio:
    """Verify mask_area_ratio meets minimum threshold after preprocessing."""

    def test_solid_garment_maintains_high_ratio(self):
        """A solid-color garment on white background should have mask_area_ratio > 0.12."""
        img = Image.new("RGB", (800, 900), color=(200, 50, 50))
        _, ratio = preprocess_garment(img, canvas_size=512)
        assert ratio > 0.12, f"Expected mask_area_ratio > 0.12, got {ratio:.3f}"

    def test_rectangular_garment_small_padding(self):
        """A tightly-cropped rectangular garment should still reach ratio > 0.12 after expansion."""
        arr = np.full((600, 700, 3), (50, 100, 200), dtype=np.uint8)
        arr[50:550, 50:650] = (150, 60, 220)
        img = Image.fromarray(arr)
        _, ratio = preprocess_garment(img, canvas_size=512)
        assert ratio > 0.12, f"Expected mask_area_ratio > 0.12, got {ratio:.3f}"

    def test_return_type_is_tuple(self):
        """preprocess_garment must return a (rgb, ratio) tuple."""
        img = Image.new("RGB", (512, 512), color=(100, 100, 100))
        result = preprocess_garment(img, canvas_size=512)
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 2, f"Expected 2-tuple, got {len(result)}"
        rgb, ratio = result
        assert isinstance(rgb, np.ndarray), f"Expected ndarray, got {type(rgb)}"
        assert rgb.shape == (512, 512, 3), f"Expected shape (512, 512, 3), got {rgb.shape}"
        assert isinstance(ratio, float), f"Expected float ratio, got {type(ratio)}"

    def test_ratio_with_black_background_garment_centered(self):
        """A centered solid garment on black background passes threshold."""
        arr = np.zeros((800, 800, 3), dtype=np.uint8)
        arr[150:650, 200:600] = (80, 120, 200)
        img = Image.fromarray(arr)
        _, ratio = preprocess_garment(img, canvas_size=512)
        assert ratio > 0.12, f"Expected mask_area_ratio > 0.12, got {ratio:.3f}"

    def test_ratio_with_white_background_garment(self):
        """A solid garment on pure white background passes threshold."""
        arr = np.full((700, 700, 3), 255, dtype=np.uint8)
        arr[100:600, 100:600] = (60, 80, 200)
        img = Image.fromarray(arr)
        _, ratio = preprocess_garment(img, canvas_size=512)
        assert ratio > 0.12, f"Expected mask_area_ratio > 0.12, got {ratio:.3f}"

    def test_transparent_rembg_pixels_are_composited_to_white(self, monkeypatch):
        """rembg often leaves transparent background RGB as black; CatVTON must see white."""
        import app.services.garment_preprocess as garment_preprocess

        rgb = np.zeros((256, 256, 3), dtype=np.uint8)
        rgb[48:208, 64:192] = (238, 236, 222)
        alpha = np.zeros((256, 256), dtype=np.uint8)
        alpha[48:208, 64:192] = 255

        monkeypatch.setattr(garment_preprocess, "_get_rembg_session", lambda: object())
        monkeypatch.setattr(
            garment_preprocess,
            "_rembg_remove",
            lambda _image: (rgb.copy(), alpha.copy()),
        )

        out, ratio = garment_preprocess.preprocess_garment(
            Image.new("RGB", (256, 256), "white"), canvas_size=128
        )

        assert ratio > 0.12
        assert float((out.mean(axis=2) < 20).mean()) < 0.01
        assert out[0, 0].mean() > 245
