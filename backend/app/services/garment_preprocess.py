"""Garment Image Preprocessing Module.

Removes background, crops to garment bounding box, and centers on a
standard canvas. This gives CatVTON a clean garment representation
without white/gray padding noise polluting the VAE latent space.

Pipeline:
    1. rembg alpha background removal
    2. Bbox crop to garment body
    3. Center on 512x512 white canvas
    4. Output: numpy RGB (H=512, W=512)
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# rembg session cache (reuse to avoid reloading model every call)
_REMBG_SESSION: Optional[object] = None  # rembg remove function, lazily initialized


def _get_rembg_session():
    """Lazily initialize and cache the rembg session."""
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        try:
            from rembg import remove

            _REMBG_SESSION = remove
            logger.info("rembg session initialized")
        except ImportError:
            logger.warning(
                "rembg not installed — garment preprocessing will fall back to color threshold"
            )
            _REMBG_SESSION = None
    return _REMBG_SESSION


def _fill_alpha_holes(alpha: np.ndarray, max_hole_ratio: float = 0.40) -> np.ndarray:
    """
    Fill internal holes in a binary/semi-binary alpha mask.

    This fixes the "transparent floating garment" bug where rembg incorrectly treats
    lace/mesh/pattern gaps as background. Uses flood-fill from border to find
    internal holes (not connected to the image edge), then fills small-to-medium ones.

    Args:
        alpha: uint8 alpha array (0-255).
        max_hole_ratio: Holes larger than this fraction of the garment area
            are NOT filled (likely real transparent regions like mesh panels).

    Returns:
        uint8 alpha with holes filled.
    """
    if alpha.max() == 0:
        return alpha

    h, w = alpha.shape
    fg_mask = (alpha > 20).astype(np.uint8)

    try:
        bg_components = (fg_mask == 0).astype(np.uint8)
        n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bg_components, connectivity=8)
        if n_labels <= 1:
            return alpha

        border_labels = set(labels[0, :].tolist())
        border_labels.update(labels[-1, :].tolist())
        border_labels.update(labels[:, 0].tolist())
        border_labels.update(labels[:, -1].tolist())

        internal_hole = np.zeros_like(fg_mask, dtype=np.uint8)
        for label_idx in range(1, n_labels):
            if label_idx not in border_labels:
                internal_hole[labels == label_idx] = 1

        if internal_hole.sum() == 0:
            return alpha

        # Label hole components
        num_holes, hole_labels, stats, _ = cv2.connectedComponentsWithStats(
            internal_hole, connectivity=8
        )
        if num_holes <= 1:
            return alpha

        # Largest foreground area for ratio threshold
        num_fg, _, fg_stats, _ = cv2.connectedComponentsWithStats(fg_mask, connectivity=8)
        largest_fg_area = (
            int(fg_stats[1:, cv2.CC_STAT_AREA].max()) if num_fg > 1 else int(fg_mask.sum())
        )
        max_hole_area = max(50, int(largest_fg_area * max_hole_ratio))

        fill_mask = np.zeros_like(alpha)
        for i in range(1, num_holes):
            if stats[i, cv2.CC_STAT_AREA] <= max_hole_area:
                fill_mask[hole_labels == i] = 255

        out = alpha.copy()
        out[fill_mask > 0] = 255
        return out.astype(np.uint8)
    except Exception:
        return alpha


def _composite_rgb_on_background(
    rgb: np.ndarray,
    alpha: np.ndarray | None,
    background: tuple[int, int, int] = (255, 255, 255),
) -> np.ndarray:
    """Composite RGBA-style pixels onto a solid background before RGB-only resize."""
    if alpha is None or alpha.size == 0 or alpha.max() == 0:
        return rgb

    rgb_f = rgb.astype(np.float32)
    a = np.clip(alpha.astype(np.float32) / 255.0, 0.0, 1.0)[..., None]
    bg = np.full_like(rgb_f, background, dtype=np.float32)
    return np.clip(rgb_f * a + bg * (1.0 - a), 0, 255).astype(np.uint8)


def _border_connected_background_mask(
    rgb: np.ndarray, alpha: np.ndarray | None = None
) -> np.ndarray:
    """Detect solid product-photo background connected to image borders."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        return np.zeros(rgb.shape[:2], dtype=bool)

    h, w = rgb.shape[:2]
    if h < 16 or w < 16:
        return np.zeros((h, w), dtype=bool)

    border_px = max(3, min(16, min(h, w) // 32))
    border = np.concatenate(
        [
            rgb[:border_px, :, :].reshape(-1, 3),
            rgb[-border_px:, :, :].reshape(-1, 3),
            rgb[:, :border_px, :].reshape(-1, 3),
            rgb[:, -border_px:, :].reshape(-1, 3),
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

    arr = rgb.astype(np.float32)
    dist = np.linalg.norm(arr - bg.reshape(1, 1, 3), axis=2)
    threshold = float(np.clip(np.percentile(border_dist, 92) + 18.0, 24.0, 78.0))
    candidate = dist <= threshold

    channel_max = rgb.max(axis=2)
    channel_min = rgb.min(axis=2)
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

    candidate_u8 = candidate.astype(np.uint8)
    num, labels, _stats, _centroids = cv2.connectedComponentsWithStats(candidate_u8, 8)
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


def _remove_border_background(rgb: np.ndarray, alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Remove uniform black/white product-photo backgrounds that rembg leaves opaque.

    The mask is restricted to pixels connected to the image border, so black labels,
    printed outlines, and inner garment details are preserved.
    """
    if alpha.size == 0 or alpha.max() == 0:
        return rgb, alpha

    bg_mask = _border_connected_background_mask(rgb, alpha=alpha)
    if not bg_mask.any():
        return rgb, alpha

    out_rgb = rgb.copy()
    out_alpha = alpha.copy()
    out_rgb[bg_mask] = 255
    out_alpha[bg_mask] = 0
    logger.info(
        "Removed border-connected product background from garment (coverage=%.3f)",
        float(bg_mask.mean()),
    )
    return out_rgb, out_alpha


def _remove_dark_edge_contamination(
    rgb: np.ndarray,
    alpha: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Trim dark halos left by black-background product photos around light garments."""
    if alpha.size == 0 or alpha.max() == 0:
        return rgb, alpha

    fg = alpha > 20
    if float(fg.mean()) < 0.03:
        return rgb, alpha

    fg_u8 = fg.astype(np.uint8)
    dist = cv2.distanceTransform(fg_u8, cv2.DIST_L2, 3)
    interior = fg & (dist > 10)
    if not interior.any():
        return rgb, alpha

    interior_value = float(rgb[interior].mean())
    if interior_value < 145.0:
        return rgb, alpha

    channel_max = rgb.max(axis=2)
    channel_min = rgb.min(axis=2)
    channel_span = channel_max - channel_min
    dark_edge = fg & (dist <= 7.0) & (channel_max < 105) & (channel_span < 58)
    if float(dark_edge.sum()) / max(float(fg.sum()), 1.0) < 0.002:
        return rgb, alpha

    out_rgb = rgb.copy()
    out_alpha = alpha.copy()
    out_rgb[dark_edge] = 255
    out_alpha[dark_edge] = 0
    logger.info(
        "Removed dark edge contamination from light garment (coverage=%.3f)",
        float(dark_edge.sum()) / max(float(fg.sum()), 1.0),
    )
    return out_rgb, out_alpha


def _inpaint_holes(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """
    Fill color pixels where alpha was holey (rembg saw-through).

    In the holes: rembg set alpha=0, and RGB is garbage (background color).
    We replace those pixels with the surrounding garment color using inpainting.

    Args:
        rgb: RGB image (H, W, 3), uint8.
        alpha: alpha channel (H, W), uint8.

    Returns:
        RGB image with holes filled with plausible garment color.
    """
    hole_mask = (alpha < 10).astype(np.uint8)
    if hole_mask.sum() < 50:
        return rgb

    try:
        # Dilate hole mask slightly before inpainting for cleaner edges
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(hole_mask, kernel, iterations=1)
        # Inpaint with surrounding pixels (TEBALDINI is better for texture)
        result = cv2.inpaint(rgb, dilated, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
        return result
    except Exception:
        # Fallback: just set holes to a neutral gray
        out = rgb.copy()
        out[hole_mask > 0] = [180, 180, 180]
        return out


def _fallback_bg_removal(image: Image.Image) -> np.ndarray:
    """
    Color-threshold background removal when rembg is unavailable.

    Works well for clean product photos where the background is a uniform
    bright color (white, light gray, light blue, etc.).
    """
    arr = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)

    rgb = arr.copy()
    rgb[mask == 0] = 0
    return rgb


def preprocess_garment(image: Image.Image, canvas_size: int = 512) -> tuple[np.ndarray, float]:
    """
    Preprocess a garment product image for CatVTON inference.

    Steps:
        1. Remove background (rembg with alpha, fallback to color threshold)
        2. Crop tightly to garment bounding box (with auto-expand if too small)
        3. Scale to fit within canvas_size with margin
        4. Center on a 512x512 white canvas

    Args:
        image: Input PIL Image (any size, any mode)
        canvas_size: Output canvas size (default 768)

    Returns:
        Tuple of:
        - numpy array: RGB image, shape (canvas_size, canvas_size, 3), dtype uint8
        - float: mask_area_ratio of the cropped bbox relative to original image
    """
    remove_fn = _get_rembg_session()

    if remove_fn is not None:
        try:
            rgb_np, alpha_np = _rembg_remove(image)
            logger.debug("rembg background removal succeeded")
        except Exception as e:
            logger.warning(f"rembg failed ({e}), falling back to color threshold")
            rgb_np = _fallback_bg_removal(image)
            alpha_np = None
    else:
        rgb_np = _fallback_bg_removal(image)
        alpha_np = None

    rgb_np = _composite_rgb_on_background(rgb_np, alpha_np)

    crop_result = _crop_to_bbox_with_ratio(rgb_np, alpha_np, margin=8)
    rgb_np, ratio = crop_result[0], crop_result[1]
    rgb_np = _center_on_canvas(rgb_np, canvas_size)
    return rgb_np, ratio


def _rembg_remove(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Use rembg to remove background and return (RGB, alpha).

    Post-processes the alpha to fix the "floating garment" bug:
      1. Fill internal holes (lace/mesh/pattern gaps rembg incorrectly removed)
      2. Inpaint RGB where alpha was holey so the garment color is continuous
    """
    remove_fn = _get_rembg_session()
    if remove_fn is None:
        raise RuntimeError("rembg not available")

    rgba = remove_fn(image.convert("RGB"))
    if isinstance(rgba, Image.Image):
        rgba_np = np.array(rgba.convert("RGBA"))
    elif isinstance(rgba, (bytes, bytearray, memoryview)):
        rgba_np = np.array(Image.open(rgba if isinstance(rgba, str) else rgba).convert("RGBA"))
    else:
        raise TypeError(f"rembg returned unexpected type: {type(rgba)}")

    if rgba_np.ndim != 3 or rgba_np.shape[2] != 4:
        raise ValueError(f"rembg RGBA shape mismatch: {rgba_np.shape}")

    rgb = rgba_np[:, :, :3]
    alpha = rgba_np[:, :, 3]

    rgb, alpha = _remove_border_background(rgb, alpha)
    rgb, alpha = _remove_dark_edge_contamination(rgb, alpha)

    alpha = _fill_alpha_holes(alpha)

    kernel = np.ones((15, 15), np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=1)
    alpha = cv2.dilate(alpha, kernel, iterations=2)

    rgb = _inpaint_holes(rgb, alpha)

    return rgb, alpha


def _crop_to_bbox_with_ratio(
    rgb: np.ndarray,
    alpha: np.ndarray | None,
    margin: int = 8,
) -> tuple[np.ndarray, float]:
    """
    Crop to the tight bounding box of the garment.

    Args:
        rgb: RGB image
        alpha: alpha channel (if available), used for precise cropping.
               If None, uses luminance threshold fallback.
        margin: pixels of padding around the garment in the crop.

    Returns:
        Tuple of (cropped_rgb, mask_area_ratio).
        mask_area_ratio is the area of the bbox relative to the original image.
    """
    h, w = rgb.shape[:2]

    if alpha is not None and alpha.max() > 0:
        ys, xs = np.where(alpha > 10)
    else:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        _, fg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ys, xs = np.where(fg > 0)

    if len(xs) == 0 or len(ys) == 0:
        logger.warning("No foreground pixels found — returning original")
        return rgb, 0.0

    x1 = max(0, xs.min() - margin)
    y1 = max(0, ys.min() - margin)
    x2 = min(w, xs.max() + margin)
    y2 = min(h, ys.max() + margin)

    mask_area_ratio = (x2 - x1) * (y2 - y1) / (h * w)
    if mask_area_ratio < 0.12:
        pad_x = int((x2 - x1) * 0.12)
        pad_y = int((y2 - y1) * 0.18)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)
        new_ratio = (x2 - x1) * (y2 - y1) / (h * w)
        logger.warning(
            f"Mask too small: auto expanded from {mask_area_ratio:.3f} to {new_ratio:.3f}"
        )
        mask_area_ratio = new_ratio

    crop = rgb[y1:y2, x1:x2]
    return crop, mask_area_ratio


def _center_on_canvas(rgb: np.ndarray, canvas_size: int = 512) -> np.ndarray:
    """
    Scale garment to fit canvas with margin, then center on white canvas.

    Args:
        rgb: Cropped garment RGB image
        canvas_size: Target canvas size (default 512)
    """
    h, w = rgb.shape[:2]

    # Scale so the garment fills ~80% of the canvas
    max_dim = max(h, w)
    target_fill = canvas_size * 0.80
    scale = target_fill / max_dim
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    resized = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    canvas = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    x_offset = (canvas_size - new_w) // 2
    y_offset = (canvas_size - new_h) // 2
    canvas[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

    return canvas
