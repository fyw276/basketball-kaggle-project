"""Lightweight tight crop verification without running full ML pipeline."""

import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def make_test_rgba(size=(1000, 1200)):
    """Create a test RGBA image with garment in center."""
    from PIL import ImageDraw

    img = Image.new("RGBA", size, (0, 0, 0, 0))  # fully transparent
    # Draw a solid garment rectangle in center (60% of image)
    w, h = size
    gx0, gy0 = int(w * 0.2), int(h * 0.2)
    gx1, gy1 = int(w * 0.8), int(h * 0.8)
    draw = ImageDraw.Draw(img)
    draw.rectangle([gx0, gy0, gx1, gy1], fill=(255, 0, 0, 255))  # red garment
    return img


def make_white_bg_garment(size=(1000, 1200)):
    """Create a white-background test image with garment centered."""
    from PIL import ImageDraw

    img = Image.new("RGB", size, (255, 255, 255))  # white background
    w, h = size
    gx0, gy0 = int(w * 0.2), int(h * 0.2)
    gx1, gy1 = int(w * 0.8), int(h * 0.8)
    draw = ImageDraw.Draw(img)
    draw.rectangle([gx0, gy0, gx1, gy1], fill=(200, 50, 50))  # red garment
    return img


def test_alpha_bbox_crop():
    print("\n" + "=" * 60)
    print("TEST 1: alpha.getbbox() returns correct tight crop")
    print("=" * 60)

    # Case A: Transparent background + solid garment (RGBA with alpha)
    rgba = make_test_rgba(size=(1000, 1200))
    alpha = rgba.split()[-1]
    bbox = alpha.getbbox()

    orig_w, orig_h = rgba.size
    print(f"\n  [RGBA test image]")
    print(f"  Original size : {orig_w}x{orig_h}")
    print(f"  bbox          : {bbox}")

    if bbox:
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        crop_smaller = bw < orig_w or bh < orig_h
        print(f"  Cropped size  : {bw}x{bh}")
        print(f"  bbox < orig  : {'PASS' if crop_smaller else 'FAIL'}")
    else:
        print(f"  bbox is None : FAIL")

    # Case B: White background + solid garment (like real product photo)
    white_bg = make_white_bg_garment(size=(1000, 1200))
    orig_w, orig_h = white_bg.size
    print(f"\n  [White BG test image]")
    print(f"  Original size : {orig_w}x{orig_h}")
    print(f"  (This is what cutout_garment_rgba receives)")
    print(f"  Note: white BG garment would need rembg/color-threshold to extract mask")


def test_generate_preview_white_tight_crop():
    print("\n" + "=" * 60)
    print("TEST 2: generate_preview_white tight crop logic (isolated)")
    print("=" * 60)

    from app.services.tryon_v2.preprocess import letterbox_resize

    # Simulate what generate_preview_white now does:
    # 1. Get RGBA from cutout
    rgba = make_test_rgba(size=(1000, 1200))
    orig_size = rgba.size

    # 2. Apply tight crop (this is the new code)
    rgba_w, rgba_h = rgba.size
    alpha = rgba.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
        print(f"\n  [Tight crop applied]")
        print(f"  Before: {rgba_w}x{rgba_h}")
        print(f"  After : {rgba.size[0]}x{rgba.size[1]}")
        print(f"  bbox  : {bbox}")
    else:
        print(f"\n  [NO CROP] bbox is None")

    # 3. Letterbox resize
    rgb = rgba.convert("RGB")
    preview = letterbox_resize(rgb, canvas_size=768, background_color=(255, 255, 255))

    print(f"\n  [Letterbox resize]")
    print(f"  Input       : {rgb.size}")
    print(f"  Output      : {preview.size}")
    print(f"  Is 768x768  : {'PASS' if preview.size == (768, 768) else 'FAIL'}")

    # Save preview for visual check
    out_path = Path(
        "d:/Users/omen/OneDrive/桌面/clothing-assistant/debug_output/tight_crop_preview.png"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(out_path)
    print(f"\n  [Saved preview to] {out_path}")


def test_standardize_white_background_tight_crop():
    print("\n" + "=" * 60)
    print("TEST 3: _standardize_white_background tight crop (isolated)")
    print("=" * 60)

    from app.services.tryon_v2.preprocess import _standardize_white_background

    # Simulate: _standardize_white_background receives the cropped RGBA
    rgba = make_test_rgba(size=(1000, 1200))
    orig_size = rgba.size

    # The function computes bbox on the cropped image
    alpha = rgba.split()[-1]
    bbox = alpha.getbbox()

    if bbox:
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        crop_smaller = bw < orig_size[0] or bh < orig_size[1]
        print(f"\n  [Input to _standardize_white_background]")
        print(f"  Input size  : {orig_size}")
        print(f"  bbox        : {bbox}")
        print(f"  Cropped size: {bw}x{bh}")
        print(f"  bbox < orig : {'PASS' if crop_smaller else 'FAIL'}")

        # Apply crop (what the function does)
        cropped_rgba = rgba.crop(bbox)
        standardized = _standardize_white_background(cropped_rgba)
        print(f"\n  [Output]")
        print(f"  standardized.size: {standardized.size}")
        print(f"  Is 768x768      : {'PASS' if standardized.size == (768, 768) else 'FAIL'}")
    else:
        print(f"\n  bbox is None - FAIL")


def test_mask_precision():
    print("\n" + "=" * 60)
    print("TEST 4: Mask edge precision with real image")
    print("=" * 60)

    # Find a real garment debug image
    debug_dir = Path("d:/Users/omen/OneDrive/桌面/clothing-assistant/debug_output")
    garment_path = None
    for d in sorted(debug_dir.glob("tryon_*/"))[-1:]:
        g = d / "02_input_garment.jpg"
        if g.exists():
            garment_path = g
            break

    if garment_path is None:
        print("  [SKIP] No real garment images found")
        return

    garment = Image.open(garment_path).convert("RGB")
    orig_w, orig_h = garment.size
    print(f"\n  Real garment image: {garment_path.name}")
    print(f"  Original size: {orig_w}x{orig_h}")

    # Apply color-threshold mask (simple version of cutout)
    import numpy as np
    from PIL import ImageFilter

    arr = np.asarray(garment, dtype=np.uint8)
    gray = arr.mean(axis=2).astype(np.float32)
    sat = (arr.max(axis=2) - arr.min(axis=2)).astype(np.float32)
    bg = (gray > 230.0) & (sat < 18.0)
    mask = np.ones(arr.shape[:2], dtype=np.uint8) * 255
    mask[bg] = 0
    pil_mask = Image.fromarray(mask, mode="L")
    for _ in range(3):
        pil_mask = pil_mask.filter(ImageFilter.MaxFilter(5))
    pil_mask = pil_mask.filter(ImageFilter.GaussianBlur(radius=0.8))

    alpha_img = pil_mask.convert("RGBA")
    alpha = alpha_img.split()[-1]
    bbox = alpha.getbbox()

    if bbox:
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        crop_smaller = bw < orig_w or bh < orig_h
        print(f"  Mask bbox    : {bbox}")
        print(f"  Cropped size : {bw}x{bh}")
        print(f"  bbox < orig  : {'PASS' if crop_smaller else 'FAIL'}")
        print(f"  Crop ratio   : {bw/orig_w:.1%} x {bh/orig_h:.1%} of original")

        # Apply crop
        cropped = garment.crop(bbox)
        out_path = garment_path.parent / "tight_crop_test.png"
        cropped.save(out_path)
        print(f"  Saved cropped: {out_path}")
    else:
        print(f"  bbox is None - might need rembg for this image")


def main():
    print("=" * 60)
    print("TIGHT CROP VERIFICATION - Lightweight Tests")
    print("=" * 60)

    test_alpha_bbox_crop()
    test_generate_preview_white_tight_crop()
    test_standardize_white_background_tight_crop()
    test_mask_precision()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
    print(
        """
VERIFICATION CHECKLIST:
  [1] alpha.getbbox() returns bbox < original size  --> PASS if garment != full image
  [2] generate_preview_white applies crop before resize --> Check logs for [CROP]
  [3] _standardize_white_background applies crop --> Check logs for [CROP]
  [4] Mask edge precision improved --> Compare mask_overlay.png vs cropped image

EXPECTED LOG OUTPUT (after running full pipeline):
  [CROP] generate_preview_white tight bbox: 1000x1200 -> 600x720 (bbox=(200,240,800,960))
  [CROP] _standardize_white_background tight bbox: 600x720 -> 600x720 (bbox=(0,0,600,720))

If you see bbox == original size in logs, the cutout pipeline (rembg/SAM)
is NOT producing a tight mask. Check garment_struct.py for the issue.
"""
    )


if __name__ == "__main__":
    main()
