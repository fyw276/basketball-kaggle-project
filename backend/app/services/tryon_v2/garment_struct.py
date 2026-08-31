"""Garment structuring helpers for Try-on v2 pipeline A (bottom garments).

This module intentionally uses light, deterministic heuristics (no heavy ML),
so that the v2 MVP stays explainable and testable on CPU-only environments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


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


def _border_connected_background_mask(
    rgb: Image.Image, alpha: np.ndarray | None = None
) -> np.ndarray:
    """Detect solid product-photo background connected to image borders."""
    arr = np.asarray(rgb.convert("RGB"), dtype=np.uint8)
    h, w = arr.shape[:2]
    if h < 16 or w < 16:
        return np.zeros((h, w), dtype=bool)

    border_px = max(3, min(16, min(h, w) // 32))
    border = np.concatenate(
        [
            arr[:border_px, :, :].reshape(-1, 3),
            arr[-border_px:, :, :].reshape(-1, 3),
            arr[:, :border_px, :].reshape(-1, 3),
            arr[:, -border_px:, :].reshape(-1, 3),
        ],
        axis=0,
    ).astype(np.float32)
    if border.size == 0:
        return np.zeros((h, w), dtype=bool)

    bg = np.median(border, axis=0)
    border_dist = np.linalg.norm(border - bg, axis=1)
    border_uniform = float(np.percentile(border_dist, 75)) < 38.0
    dark_border = float(bg.mean()) < 70.0
    light_border = float(bg.mean()) > 220.0 and float(border_dist.mean()) < 45.0
    if not (border_uniform or dark_border or light_border):
        return np.zeros((h, w), dtype=bool)

    arr_f = arr.astype(np.float32)
    dist = np.linalg.norm(arr_f - bg.reshape(1, 1, 3), axis=2)
    threshold = float(np.clip(np.percentile(border_dist, 92) + 18.0, 24.0, 78.0))
    candidate = dist <= threshold

    channel_max = arr.max(axis=2)
    channel_min = arr.min(axis=2)
    channel_span = channel_max - channel_min
    if dark_border:
        if alpha is not None and alpha.size > 0:
            a_h, a_w = alpha.shape[:2]
            bp = max(3, min(16, min(a_h, a_w) // 32))
            border_alpha = np.concatenate(
                [
                    alpha[:bp, :].ravel(),
                    alpha[-bp:, :].ravel(),
                    alpha[:, :bp].ravel(),
                    alpha[:, -bp:].ravel(),
                ]
            )
            if float(np.mean(border_alpha < 30)) > 0.70:
                pass
            else:
                candidate |= (channel_max < 70) & (channel_span < 42)
        else:
            candidate |= (channel_max < 70) & (channel_span < 42)
    if light_border:
        candidate |= (channel_min > 232) & (channel_span < 34)

    num, labels, _stats, _centroids = cv2.connectedComponentsWithStats(
        candidate.astype(np.uint8), 8
    )
    if num <= 1:
        return np.zeros((h, w), dtype=bool)

    border_labels = set(labels[0, :].tolist())
    border_labels.update(labels[-1, :].tolist())
    border_labels.update(labels[:, 0].tolist())
    border_labels.update(labels[:, -1].tolist())

    bg_mask = np.zeros((h, w), dtype=bool)
    for label_idx in border_labels:
        if label_idx != 0:
            bg_mask |= labels == label_idx

    coverage = float(bg_mask.mean())
    if coverage < 0.02:
        return np.zeros((h, w), dtype=bool)
    if dark_border and coverage > 0.70 and alpha is not None and alpha.size > 0:
        return np.zeros((h, w), dtype=bool)
    return bg_mask


def _remove_border_background_from_rgba(rgba: Image.Image, rgb: Image.Image) -> Image.Image:
    """
    Clear black/white product-photo backgrounds that segmentation leaves opaque.

    Only border-connected pixels are removed, so internal black labels and prints stay.
    """
    im = rgba.convert("RGBA")
    alpha_arr = np.asarray(im, dtype=np.uint8)[:, :, 3]
    bg_mask = _border_connected_background_mask(rgb, alpha=alpha_arr)
    if not bg_mask.any():
        return im

    arr = np.asarray(im, dtype=np.uint8).copy()
    arr[bg_mask, :3] = 255
    arr[bg_mask, 3] = 0
    logger.info(
        "[GARMENT-STRUCT] removed border-connected product background (coverage=%.3f)",
        float(bg_mask.mean()),
    )
    return Image.fromarray(arr, mode="RGBA")


def _remove_dark_edge_contamination_from_rgba(rgba: Image.Image) -> Image.Image:
    """Trim black-background halos around light garments without touching inner prints."""
    im = rgba.convert("RGBA")
    arr = np.asarray(im, dtype=np.uint8).copy()
    alpha = arr[:, :, 3]
    fg = alpha > 20
    if float(fg.mean()) < 0.03:
        return im

    dist = cv2.distanceTransform(fg.astype(np.uint8), cv2.DIST_L2, 3)
    interior = fg & (dist > 10)
    if not interior.any():
        return im

    interior_value = float(arr[:, :, :3][interior].mean())
    if interior_value < 145.0:
        return im

    channel_max = arr[:, :, :3].max(axis=2)
    channel_min = arr[:, :, :3].min(axis=2)
    channel_span = channel_max - channel_min
    dark_edge = fg & (dist <= 7.0) & (channel_max < 105) & (channel_span < 58)
    dark_ratio = float(dark_edge.sum()) / max(float(fg.sum()), 1.0)
    if dark_ratio < 0.002:
        return im

    arr[dark_edge, :3] = 255
    arr[dark_edge, 3] = 0
    logger.info(
        "[GARMENT-STRUCT] removed dark edge contamination from light garment " "(coverage=%.3f)",
        dark_ratio,
    )
    return Image.fromarray(arr, mode="RGBA")


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


def _fill_alpha_holes(rgba: Image.Image, max_hole_area_ratio: float = 0.40) -> Image.Image:
    """Fill internal holes in the alpha mask that rembg incorrectly treats as background.

    This is the KEY fix for the "transparent floating garment" bug. When rembg
    sees through lace, mesh, or pattern gaps, the alpha mask has holes that let
    the person image bleed through. We fill any hole that is:
      1. Completely surrounded by foreground pixels
      2. Smaller than max_hole_area_ratio of the largest foreground component

    Args:
        rgba: RGBA PIL image with alpha mask.
        max_hole_area_ratio: Holes larger than this ratio of the main garment
            are NOT filled (they're likely real transparent regions like mesh).
    """
    im = rgba.convert("RGBA")
    a = np.asarray(im.split()[3], dtype=np.uint8)
    if a.max() == 0:
        return im

    try:
        # Binarize alpha
        fg_mask = (a > 20).astype(np.uint8)

        # Flood-fill the background from the image border to mark external background
        h, w = a.shape
        bg_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        cv2.floodFill(bg_mask, seedPoint=(0, 0), newVal=1)
        cv2.floodFill(bg_mask, seedPoint=(w + 1, 0), newVal=1)
        cv2.floodFill(bg_mask, seedPoint=(0, h + 1), newVal=1)
        cv2.floodFill(bg_mask, seedPoint=(w + 1, h + 1), newVal=1)
        bg_mask = bg_mask[1:-1, 1:-1]  # Remove padding

        # Everything NOT background AND NOT foreground = internal hole
        internal_hole = ((bg_mask == 0) & (fg_mask == 0)).astype(np.uint8)

        if internal_hole.sum() == 0:
            return im

        # Label connected hole components
        num_holes, hole_labels, stats, _ = cv2.connectedComponentsWithStats(
            internal_hole, connectivity=8
        )
        if num_holes <= 1:
            return im

        # Find largest foreground component area for ratio comparison
        num_fg, fg_labels, fg_stats, _ = cv2.connectedComponentsWithStats(fg_mask, connectivity=8)
        largest_fg_area = 0
        if num_fg > 1:
            largest_fg_area = int(fg_stats[1:, cv2.CC_STAT_AREA].max())

        # Fill only small-to-medium holes (not large transparent regions like mesh panels)
        fill_mask = np.zeros_like(a)
        max_hole_area = int(largest_fg_area * max_hole_area_ratio) if largest_fg_area > 0 else 1000

        for i in range(1, num_holes):
            hole_area = int(stats[i, cv2.CC_STAT_AREA])
            if hole_area <= max_hole_area:
                fill_mask[hole_labels == i] = 255

        # Apply fill
        a_filled = np.minimum(a, fill_mask).astype(np.uint8)
        out = im.copy()
        out.putalpha(Image.fromarray(a_filled, mode="L"))
        return out
    except Exception:
        return im


def _check_rembg_quality(rgba: Image.Image) -> bool:
    """Return True if rembg alpha looks suspicious (many internal holes = bad quality).

    Suspicious patterns that indicate rembg failure:
      - Very high solidity (lots of holes inside garment)
      - Alpha coverage is too sparse for a garment image
    """
    try:
        a = np.asarray(rgba.split()[3], dtype=np.uint8)
        fg_mask = (a > 20).astype(np.uint8)

        # Find contours on the alpha
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False

        # Largest contour area
        largest_area = max(cv2.contourArea(c) for c in contours)
        if largest_area < 100:
            return False

        # Ratio of foreground pixels to bounding box of largest contour
        ys, xs = np.where(fg_mask > 0)
        if xs.size == 0:
            return False
        x0, y0 = xs.min(), ys.min()
        x1, y1 = xs.max() + 1, ys.max() + 1
        bbox_area = float((x1 - x0) * (y1 - y0))
        solidity = float(fg_mask.sum()) / max(bbox_area, 1.0)

        # If fill ratio < 0.55, rembg likely missed a lot of the garment (many holes)
        if solidity < 0.55:
            return True

        # Check for suspicious internal holes (large un-filled area within bbox)
        holes_area = bbox_area - float(fg_mask.sum())
        hole_ratio = holes_area / max(bbox_area, 1.0)
        if hole_ratio > 0.30:
            return True

        return False
    except Exception:
        return False


def cutout_garment_rgba(
    garment_image: Image.Image,
    cloth_type: str = "upper",
) -> GarmentCutout:
    """Extract garment from product image as RGBA with alpha mask.

    Strategy (in priority order):
      1. MobileSAM + cloth_type hints → best quality for complex garments
      2. rembg → fast for white-background product photos
      3. Color threshold fallback → last resort

    For SAM: cloth_type hints guide the segmentation (upper/bottom/dress).
    For rembg: alpha holes (lace/mesh gaps) are filled with flood-fill.

    Args:
        garment_image: PIL RGB image of the garment.
        cloth_type: "upper" | "lower" | "dress" | "skirt" — hints for SAM.
    """
    rgb = garment_image.convert("RGB")
    rgba: Image.Image | None = None
    used_sam = False

    # ── Strategy 1: MobileSAM with cloth-type hints ─────────────────────────
    # SAM provides much better segmentation than rembg for:
    # - Complex garments (ruffles, puffy sleeves, skirts)
    # - Semi-transparent fabrics
    # - Garments with cutouts / holes
    # Using cloth_type hints produces more accurate masks.
    try:
        from app.services.sam_mask import sam_segment_with_hints

        sam_mask = sam_segment_with_hints(rgb, cloth_type=cloth_type)
        if sam_mask is not None:
            sam_np = np.asarray(sam_mask, dtype=np.uint8)
            if sam_np.sum() > 100:
                rgba = rgb.convert("RGBA")
                rgba.putalpha(sam_mask)
                used_sam = True
                logger.debug(
                    f"[GARMENT-STRUCT] MobileSAM segmentation succeeded "
                    f"(type={cloth_type}, area={sam_np.sum()})"
                )
    except Exception:
        pass

    # ── Strategy 2: rembg (fast, white-background product photos) ───────────
    # rembg handles white/clean backgrounds very well.
    # Alpha holes (lace/mesh gaps) are fixed by _fill_alpha_holes below.
    if rgba is None:
        try:
            from io import BytesIO

            from rembg import remove

            out = remove(rgb)
            if isinstance(out, Image.Image):
                candidate = out.convert("RGBA")
            elif isinstance(out, (bytes, bytearray)):
                candidate = Image.open(BytesIO(out)).convert("RGBA")
            else:
                candidate = None
            # Validate rembg mask quality: require at least 5% non-transparent pixels
            if candidate is not None:
                a_arr = np.asarray(candidate.split()[3], dtype=np.uint8)
                cover = float((a_arr > 20).mean())
                if cover >= 0.05:
                    rgba = candidate
                else:
                    logger.debug(
                        "[GARMENT-STRUCT] rembg mask too sparse (%.1f%% cover), "
                        "falling back to color threshold",
                        cover * 100,
                    )
        except Exception:
            pass

    # ── Strategy 3: Color threshold fallback ─────────────────────────────────
    if rgba is None:
        if _looks_like_white_bg_product(rgb):
            mask = _generate_white_bg_mask(rgb)
        else:
            mask = _generate_garment_mask(rgb)
        rgba = rgb.convert("RGBA")
        rgba.putalpha(mask)

    rgba = _remove_border_background_from_rgba(rgba, rgb)
    rgba = _remove_dark_edge_contamination_from_rgba(rgba)

    # ── Post-processing: fill alpha holes + smooth boundary ──────────────────
    # For non-SAM paths: rembg and color-threshold can produce holes (lace/mesh gaps).
    # These holes cause the "floating garment" bug where the person bleeds through.
    # For SAM: even though SAM generates clean masks, some garment-edge holes may
    # still exist and should be filled for best quality.
    if not used_sam:
        if not _looks_like_white_bg_product(rgb):
            rgba = _keep_largest_alpha_component(rgba)

        rgba = _fill_alpha_holes(rgba)
        rgba = _smooth_alpha_boundary(rgba)

        a = np.asarray(rgba.split()[3], dtype=np.uint8)
        cover = float((a > 20).mean())
        if cover > 0.85:
            refined = _grabcut_refine_rgba(rgb)
            if refined is not None:
                refined = _keep_largest_alpha_component(refined)
                # Validate GrabCut: keep original if GrabCut destroys the mask
                ref_a = np.asarray(refined.split()[3], dtype=np.uint8)
                ref_cover = float((ref_a > 20).mean())
                if ref_cover >= 0.10:
                    rgba = refined
                else:
                    logger.debug(
                        "[GARMENT-STRUCT] GrabCut produced sparse mask (%.1f%% cover), "
                        "keeping original (%.1f%%)",
                        ref_cover * 100,
                        cover * 100,
                    )
    else:
        # SAM masks can also have small internal holes (thin garment parts).
        # Apply gentle hole-filling to ensure full garment coverage.
        rgba = _fill_alpha_holes(rgba, max_hole_area_ratio=0.15)

    bbox = _alpha_bbox(rgba)
    cropped = rgba.crop(bbox) if bbox else rgba
    return GarmentCutout(rgba=rgba, cropped=cropped)


def _strip_inner_leg_white_edge(leg: Image.Image, *, inseam: str) -> Image.Image:
    """Clear near-white product-bg pixels stuck to a leg crop's inseam side.

    White-bg pants photos leave a bright fringe between the legs. After L/R split
    that fringe sits on the inseam edge and warps into a vertical white split.

    Args:
        leg: RGBA leg crop.
        inseam: ``"right"`` for the left leg (inseam on its right), ``"left"``
            for the right leg.
    """
    im = leg.convert("RGBA")
    arr = np.asarray(im, dtype=np.uint8).copy()
    h, w = arr.shape[:2]
    if w < 8 or h < 8:
        return im

    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3]
    gray = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    fg = alpha > 20
    if not fg.any():
        return im

    edge_band = np.zeros((h, w), dtype=bool)
    band_w = max(3, int(w * 0.20))
    if inseam == "right":
        edge_band[:, w - band_w :] = True
    else:
        edge_band[:, :band_w] = True

    eroded = cv2.erode(fg.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2)
    near_boundary = fg & (eroded == 0)
    interior = eroded > 0
    interior_gray = float(np.median(gray[interior])) if interior.any() else 255.0
    whiteish = (gray > 175.0) & (sat < 28.0) & fg

    # Dark pants: white product-bg between legs is often fully opaque and glued to
    # the fabric, so do not require an alpha boundary — clear the whole inseam fringe.
    # Light pants: only clear true background fringe near the silhouette edge.
    if interior_gray < 140.0:
        kill = whiteish & edge_band
        bright_edge = (
            edge_band & near_boundary & fg & (gray > interior_gray + 45.0) & (gray > 110.0)
        )
        kill |= bright_edge
    else:
        kill = whiteish & edge_band & near_boundary

    if not kill.any():
        return im

    arr[kill, :3] = 255
    arr[kill, 3] = 0
    logger.debug(
        "[GARMENT-STRUCT] stripped inner-leg white edge inseam=%s px=%d",
        inseam,
        int(kill.sum()),
    )
    return Image.fromarray(arr, mode="RGBA")


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

    # Split row for waistband: keep only the visible waistband/crotch transition.
    # A tall product-photo waistband becomes an obvious pasted horizontal block
    # when stretched onto the person, especially for plaid pants.
    y_band = _clamp_int(int(h * 0.12), 6, h - 6)
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

    left_leg = _strip_inner_leg_white_edge(
        lower.crop((0, 0, x_mid, lower.size[1])),
        inseam="right",
    )
    right_leg = _strip_inner_leg_white_edge(
        lower.crop((x_mid, 0, w, lower.size[1])),
        inseam="left",
    )

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
