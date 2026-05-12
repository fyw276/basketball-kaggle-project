"""Verify tight crop is working correctly.

Compares before/after bbox sizes and logs results for validation.
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# Find a real garment test image
DEBUG_DIR = Path("d:/Users/omen/OneDrive/桌面/clothing-assistant/debug_output")
IMG_DIR = DEBUG_DIR / "tryon_20260510_093303_233_8538db"
GARMENT_IMG = IMG_DIR / "02_input_garment.jpg"


def verify_tight_crop():
    from PIL import Image

    from app.services.tryon_v2.garment_struct import cutout_garment_rgba
    from app.services.tryon_v2.preprocess import (
        _standardize_white_background,
        generate_preview_white,
        preprocess_garment_image,
    )

    if not GARMENT_IMG.exists():
        print(f"[SKIP] Test image not found: {GARMENT_IMG}")
        print("Looking for existing garment images...")
        for d in sorted(DEBUG_DIR.glob("*/"))[-3:]:
            g = d / "02_input_garment.jpg"
            if g.exists():
                GARMENT_IMG = g
                break
        if not GARMENT_IMG.exists():
            print("[SKIP] No test garment images found")
            return

    garment = Image.open(GARMENT_IMG).convert("RGB")
    orig_w, orig_h = garment.size
    print(f"\n{'='*60}")
    print(f"TEST: Tight Crop Verification")
    print(f"Input garment: {GARMENT_IMG.name}")
    print(f"Original size: {orig_w}x{orig_h}")
    print(f"{'='*60}\n")

    # ── Step 1: cutout_garment_rgba bbox ─────────────────────────────────
    cutout = cutout_garment_rgba(garment, cloth_type="upper")
    rgba = cutout.rgba
    cropped = cutout.cropped
    alpha = rgba.split()[-1]
    bbox = alpha.getbbox()
    print(f"[1] cutout_garment_rgba results:")
    print(f"    rgba.size          = {rgba.size}  (full size)")
    print(f"    cutout.cropped.size= {cropped.size}  (cropped via _alpha_bbox)")
    print(f"    alpha.getbbox()    = {bbox}")

    # ── Step 2: _standardize_white_background (uses cropped image) ────────
    print(f"\n[2] _standardize_white_background(cutout.cropped):")
    standardized = _standardize_white_background(cropped)
    print(f"    standardized.size  = {standardized.size}  (should be 768x768)")

    # ── Step 3: generate_preview_white (uses full rgba + tight crop) ────
    print(f"\n[3] generate_preview_white(garment):")
    preview = generate_preview_white(garment, cloth_type="upper")
    if preview:
        print(f"    preview.size       = {preview.size}")
    else:
        print(f"    preview            = None (failed)")

    # ── Step 4: full preprocess_garment_image ─────────────────────────────
    print(f"\n[4] preprocess_garment_image(garment):")
    result = preprocess_garment_image(garment, cloth_type_hint="upper")
    print(f"    result.image.size  = {result.image.size}")
    print(
        f"    result.preview_white.size = {result.preview_white.size if result.preview_white else 'None'}"
    )
    print(f"    result.tryon_category    = {result.tryon_category}")
    print(f"    result.confidence        = {result.confidence:.3f}")
    print(f"    result.raw_category      = {result.raw_category}")
    print(f"    result.metadata:")
    for k, v in result.metadata.items():
        print(f"      {k:30s} = {v}")

    # ── Validation ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("VALIDATION RESULTS")
    print(f"{'='*60}")

    # Check 1: cutout bbox should be smaller than original
    if bbox:
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        crop_smaller = bw < orig_w or bh < orig_h
        print(f"\n[CHECK 1] bbox crop:")
        print(f"  Original : {orig_w}x{orig_h}")
        print(f"  bbox     : ({bbox[0]},{bbox[1]}) → ({bbox[2]},{bbox[3]})  = {bw}x{bh}")
        print(f"  bbox < orig: {'PASS ✓' if crop_smaller else 'FAIL ✗ (bbox == orig size)'}")
    else:
        print(f"\n[CHECK 1] bbox crop: FAIL ✗ (bbox is None)")

    # Check 2: standardized should be 768x768
    is_768 = standardized.size == (768, 768)
    print(f"\n[CHECK 2] standardized size:")
    print(f"  Size: {standardized.size}")
    print(f"  Is 768x768: {'PASS ✓' if is_768 else 'FAIL ✗'}")

    # Check 3: preview should be 768x768 letterbox
    if preview:
        is_preview_768 = preview.size == (768, 768)
        print(f"\n[CHECK 3] preview_white size:")
        print(f"  Size: {preview.size}")
        print(f"  Is 768x768: {'PASS ✓' if is_preview_768 else 'FAIL ✗'}")

    # Check 4: bbox < cropped size should NOT happen (already cropped)
    # This is expected to show as "bbox == cropped size"
    if bbox:
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        cropped_smaller = cropped.size[0] < orig_w or cropped.size[1] < orig_h
        print(f"\n[CHECK 4] cutout.cropped vs original:")
        print(f"  cropped.size = {cropped.size}")
        print(f"  cropped < orig: {'PASS ✓' if cropped_smaller else 'FAIL ✗'}")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Before crop (original): {orig_w}x{orig_h}")
    print(f"  After  crop (cutout.cropped): {cropped.size}")
    print(f"  standardized output: {standardized.size}")
    print(f"  preview_white output: {preview.size if preview else 'None'}")
    print(f"  confidence: {result.confidence:.3f}")
    print(f"  tryon_category: {result.tryon_category}")


if __name__ == "__main__":
    verify_tight_crop()
