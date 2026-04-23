"""Garment structuring helpers for Try-on v2 pipeline A (bottom garments).

This module intentionally uses light, deterministic heuristics (no heavy ML),
so that the v2 MVP stays explainable and testable on CPU-only environments.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter


@dataclass
class GarmentCutout:
    rgba: Image.Image  # original size RGBA with alpha
    cropped: Image.Image  # cropped to alpha bbox, RGBA


@dataclass
class PantsParts:
    waistband: Image.Image  # RGBA
    left_leg: Image.Image  # RGBA
    right_leg: Image.Image  # RGBA


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _alpha_bbox(im: Image.Image) -> tuple[int, int, int, int] | None:
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    bbox = im.split()[3].getbbox()
    return bbox


def _generate_garment_mask(rgb: Image.Image) -> Image.Image:
    """Generate garment foreground mask using color/saturation thresholding."""
    img_array = np.asarray(rgb.convert("RGB"), dtype=np.uint8)
    h, w = img_array.shape[:2]
    gray = img_array.mean(axis=2).astype(np.float32)
    sat = (img_array.max(axis=2) - img_array.min(axis=2)).astype(np.float32)
    # Background: very bright + low saturation
    bg_mask = (gray > 230.0) & (sat < 18.0)
    mask = np.ones((h, w), dtype=np.uint8) * 255
    mask[bg_mask] = 0

    pil_mask = Image.fromarray(mask, mode="L")
    # Inflate foreground to preserve thin edges (sleeves, collar, etc.)
    for _ in range(3):
        pil_mask = pil_mask.filter(ImageFilter.MaxFilter(5))
    # Light blur to smooth the mask edges
    pil_mask = pil_mask.filter(ImageFilter.GaussianBlur(radius=0.8))
    return pil_mask


def _looks_like_white_bg_product(rgb: Image.Image) -> bool:
    """Detect standardized white-background product photos.

    For those, a simpler threshold-based segmentation is often more stable than
    rembg/GrabCut and avoids cutting the garment into tiny components.
    """
    arr = np.asarray(rgb.convert("RGB"), dtype=np.uint8)
    if arr.size == 0:
        return False
    gray = arr.mean(axis=2).astype(np.float32)
    sat = (arr.max(axis=2) - arr.min(axis=2)).astype(np.float32)
    bg = (gray > 242.0) & (sat < 14.0)
    # Standardized white-bg images should have large clean background area.
    return float(bg.mean()) >= 0.45


def _generate_white_bg_mask(rgb: Image.Image) -> Image.Image:
    """More permissive foreground mask tuned for white-background product photos."""
    arr = np.asarray(rgb.convert("RGB"), dtype=np.uint8)
    h, w = arr.shape[:2]
    gray = arr.mean(axis=2).astype(np.float32)
    sat = (arr.max(axis=2) - arr.min(axis=2)).astype(np.float32)

    # Background: very bright and low saturation.
    bg = (gray > 244.0) & (sat < 16.0)
    mask = np.ones((h, w), dtype=np.uint8) * 255
    mask[bg] = 0

    pil = Image.fromarray(mask, mode="L")
    # Inflate foreground slightly to keep thin sleeves/edges.
    for _ in range(3):
        pil = pil.filter(ImageFilter.MaxFilter(3))
    pil = pil.filter(ImageFilter.GaussianBlur(radius=0.8))
    return pil


def _keep_largest_alpha_component(rgba: Image.Image, min_alpha: int = 20) -> Image.Image:
    """Remove small disconnected components in alpha (keep only largest blob).

    Uses OpenCV if available, otherwise falls back to a simple bbox-only cleanup.
    """
    im = rgba.convert("RGBA")
    a = np.asarray(im.split()[3], dtype=np.uint8)
    mask = (a > int(min_alpha)).astype(np.uint8)
    if mask.sum() < 64:
        return im

    try:
        import cv2  # type: ignore

        num, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num <= 1:
            return im
        # stats: [label, x, y, w, h, area], label 0 is background
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = int(1 + np.argmax(areas))
        keep_mask = (labels == keep).astype(np.uint8)
        a2 = (keep_mask * 255).astype(np.uint8)
        out = im.copy()
        out.putalpha(Image.fromarray(a2, mode="L"))
        return out
    except Exception:
        # Fallback: do nothing (still better than crashing).
        return im


def _grabcut_refine_rgba(rgb: Image.Image) -> Image.Image | None:
    """Best-effort foreground extraction for poster/screenshot-like inputs.

    Requires OpenCV. Returns an RGBA image with alpha mask, or None if unavailable/fails.
    """
    try:
        import cv2  # type: ignore

        arr = np.asarray(rgb.convert("RGB"))
        h, w = arr.shape[:2]
        if h < 64 or w < 64:
            return None

        # Initialize with a loose rectangle (exclude borders).
        rect = (int(w * 0.06), int(h * 0.06), int(w * 0.88), int(h * 0.88))
        mask = np.zeros((h, w), np.uint8)
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)
        cv2.grabCut(arr, mask, rect, bgdModel, fgdModel, 3, cv2.GC_INIT_WITH_RECT)
        # Foreground: GC_FGD or GC_PR_FGD
        fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        pil_a = Image.fromarray(fg, mode="L").filter(ImageFilter.GaussianBlur(radius=1.0))
        out = Image.fromarray(arr, mode="RGB").convert("RGBA")
        out.putalpha(pil_a)
        return out
    except Exception:
        return None


def _smooth_alpha_boundary(rgba: Image.Image) -> Image.Image:
    """Reduce halo/feather artifacts at the alpha boundary using alpha morphology."""
    im = rgba.convert("RGBA")
    a = np.asarray(im.split()[3], dtype=np.uint8)
    if a.max() == 0:
        return im

    boundary = (a > 10) & (a < 245)
    if boundary.sum() < 100:
        return im

    try:
        import cv2

        kernel = np.ones((3, 3), np.uint8)
        a_thin = cv2.erode(a, kernel, iterations=1)
        a_thick = cv2.dilate(a_thin, kernel, iterations=1)
        mask = boundary.astype(np.float32) / 255.0
        a_clean = (a * (1 - mask * 0.5) + a_thick * mask * 0.5).astype(np.uint8)
        out = im.copy()
        out.putalpha(Image.fromarray(a_clean, mode="L"))
        return out
    except Exception:
        return im


def cutout_garment_rgba(garment_image: Image.Image) -> GarmentCutout:
    rgb = garment_image.convert("RGB")
    rgba: Image.Image | None = None

    # Optional: use rembg if available (kept best-effort).
    try:
        from io import BytesIO

        from rembg import remove

        out = remove(rgb)
        if isinstance(out, Image.Image):
            rgba = out.convert("RGBA")
        elif isinstance(out, (bytes, bytearray)):
            rgba = Image.open(BytesIO(out)).convert("RGBA")
    except Exception:
        rgba = None

    if rgba is None:
        # If this is a white-bg product photo, use a more stable mask.
        if _looks_like_white_bg_product(rgb):
            mask = _generate_white_bg_mask(rgb)
        else:
            mask = _generate_garment_mask(rgb)
        rgba = rgb.convert("RGBA")
        rgba.putalpha(mask)

    # Keep only the main connected component to avoid pasting "product list panels"/watermarks.
    # For white-bg product photos, avoid over-aggressive component filtering.
    if not _looks_like_white_bg_product(rgb):
        rgba = _keep_largest_alpha_component(rgba)

    # Edge-preserving refinement: use bilateral-ish smoothing on alpha near boundary
    # to reduce halo artifacts where garment meets background.
    rgba = _smooth_alpha_boundary(rgba)

    # Poster/screenshot often yields near-full alpha. Instead of failing, try GrabCut refinement.
    a = np.asarray(rgba.split()[3], dtype=np.uint8)
    cover = float((a > 20).mean())
    if cover > 0.85:
        refined = _grabcut_refine_rgba(rgb)
        if refined is not None:
            refined = _keep_largest_alpha_component(refined)
            rgba = refined

    bbox = _alpha_bbox(rgba)
    cropped = rgba.crop(bbox) if bbox else rgba
    return GarmentCutout(rgba=rgba, cropped=cropped)


def split_pants_parts(cropped_rgba: Image.Image) -> PantsParts:
    """Split pants into waistband / left leg / right leg using alpha heuristics."""
    im = cropped_rgba.convert("RGBA")
    w, h = im.size
    if w < 16 or h < 16:
        raise ValueError("garment too small for structuring")

    # Split row for waistband: keep top ~22% as waistband.
    y_band = _clamp_int(int(h * 0.22), 6, h - 6)
    waistband = im.crop((0, 0, w, y_band))

    # Remaining region: split legs by alpha median x in lower region.
    lower = im.crop((0, y_band, w, h))
    a = np.asarray(lower.split()[3], dtype=np.uint8)
    ys, xs = np.where(a > 20)
    if xs.size < 50:
        # If segmentation is poor, fall back to equal split.
        x_mid = w // 2
    else:
        x_mid = int(np.median(xs))
        x_mid = _clamp_int(x_mid, int(w * 0.35), int(w * 0.65))

    left_leg = lower.crop((0, 0, x_mid, lower.size[1]))
    right_leg = lower.crop((x_mid, 0, w, lower.size[1]))

    return PantsParts(waistband=waistband, left_leg=left_leg, right_leg=right_leg)
