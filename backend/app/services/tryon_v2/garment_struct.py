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
    """Same idea as v1 fallback: bright + low saturation treated as background."""
    img_array = np.asarray(rgb.convert("RGB"), dtype=np.uint8)
    h, w = img_array.shape[:2]
    gray = img_array.mean(axis=2).astype(np.float32)
    sat = (img_array.max(axis=2) - img_array.min(axis=2)).astype(np.float32)
    bg_mask = (gray > 230.0) & (sat < 18.0)
    mask = np.ones((h, w), dtype=np.uint8) * 255
    mask[bg_mask] = 0

    pil_mask = Image.fromarray(mask, mode="L")
    # Slightly inflate foreground.
    for _ in range(2):
        pil_mask = pil_mask.filter(ImageFilter.MaxFilter(3))
    # Small blur to help feather later.
    pil_mask = pil_mask.filter(ImageFilter.GaussianBlur(radius=0.6))
    return pil_mask


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
        mask = _generate_garment_mask(rgb)
        rgba = rgb.convert("RGBA")
        rgba.putalpha(mask)

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
