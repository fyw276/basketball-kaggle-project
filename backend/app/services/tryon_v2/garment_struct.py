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
    # Knee-aware split (populated when knee_garment_ratio is provided to split_pants_parts)
    left_upper: Image.Image | None = None  # RGBA, hip→knee portion
    left_lower: Image.Image | None = None  # RGBA, knee→ankle portion
    right_upper: Image.Image | None = None  # RGBA, hip→knee portion
    right_lower: Image.Image | None = None  # RGBA, knee→ankle portion


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
    """Remove small disconnected noise in alpha while preserving garment details.

    Preserves the largest connected component AND any other components that are:
    1. Within 20% of the largest component's area
    2. Spatially separated from the main body (likely sleeves/collar/details)

    This prevents aggressive filtering that was removing garment details
    for colored garments with disconnected parts.
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
        areas = stats[1:, cv2.CC_STAT_AREA]
        if areas.size == 0:
            return im

        sorted_indices = np.argsort(areas)[::-1]  # 降序排列
        keep_mask = np.zeros_like(mask)

        # 永远保留最大连通区域
        largest_idx = sorted_indices[0] + 1
        keep_mask[labels == largest_idx] = 1

        # 保留所有面积 >= 最大面积 20% 的连通区域（捕获袖子、领口等细节）
        largest_area = areas[sorted_indices[0]]
        area_threshold = largest_area * 0.20
        for idx in sorted_indices[1:]:
            if areas[idx] >= area_threshold:
                keep_idx = idx + 1
                keep_mask[labels == keep_idx] = 1
            else:
                break  # 后续都是更小的，不用再检查

        # 也保留那些与主区域有明显空间分离的连通区域
        # 计算主区域的中心
        largest_component_mask = (labels == largest_idx).astype(np.uint8)
        M = cv2.moments(largest_component_mask)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            main_area = largest_area

            for idx in sorted_indices[1:]:
                if areas[idx] < largest_area * 0.05:  # 太小直接跳过
                    continue
                comp_mask = (labels == (idx + 1)).astype(np.uint8)
                M2 = cv2.moments(comp_mask)
                if M2["m00"] > 0:
                    cx2 = int(M2["m10"] / M2["m00"])
                    cy2 = int(M2["m01"] / M2["m00"])
                    # 计算到主区域中心的距离
                    dist = np.sqrt((cx2 - cx) ** 2 + (cy2 - cy) ** 2)
                    # 如果距离 > 主区域宽度的 30%，可能是袖子等分离部件，保留
                    main_width = np.sqrt(main_area / np.pi)  # 近似半径
                    if dist > main_width * 0.30:
                        keep_mask[labels == (idx + 1)] = 1

        a2 = (keep_mask * 255).astype(np.uint8)
        out = im.copy()
        out.putalpha(Image.fromarray(a2, mode="L"))
        return out
    except Exception:
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


def split_pants_parts(
    cropped_rgba: Image.Image,
    *,
    knee_garment_ratio: float | None = None,
) -> PantsParts:
    """Split pants into waistband / left leg / right leg using alpha heuristics.

    Args:
        cropped_rgba: Cropped RGBA pants image.
        knee_garment_ratio: Optional vertical ratio [0,1] for knee position within the leg portion.
            If provided, also populates upper_leg and lower_leg for each leg.
            For example, knee_garment_ratio=0.45 means the knee is at 45% of leg height from top.
    """
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

    parts = PantsParts(waistband=waistband, left_leg=left_leg, right_leg=right_leg)

    # ── Knee-aware leg splitting ──────────────────────────────────────────
    # If knee_garment_ratio is provided, split each leg into upper (hip→knee)
    # and lower (knee→ankle) for two-stage warp with better pattern preservation.
    if knee_garment_ratio is not None and 0.25 <= knee_garment_ratio <= 0.75:
        leg_h = lower.size[1]
        knee_y = _clamp_int(int(leg_h * knee_garment_ratio), int(leg_h * 0.25), int(leg_h * 0.75))
        parts.left_upper = left_leg.crop((0, 0, left_leg.size[0], knee_y))
        parts.left_lower = left_leg.crop((0, knee_y, left_leg.size[0], left_leg.size[1]))
        parts.right_upper = right_leg.crop((0, 0, right_leg.size[0], knee_y))
        parts.right_lower = right_leg.crop((0, knee_y, right_leg.size[0], right_leg.size[1]))

    return parts
