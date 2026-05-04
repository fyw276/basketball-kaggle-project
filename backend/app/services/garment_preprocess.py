"""Garment Image Preprocessing Module.

Removes background, crops to garment bounding box, and centers on a
standard canvas. This gives CatVTON a clean garment representation
without white/gray padding noise polluting the VAE latent space.

Pipeline:
    1. rembg alpha background removal
    2. Bbox crop to garment body
    3. Center on 512x512 black canvas
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


def preprocess_garment(image: Image.Image, canvas_size: int = 512) -> np.ndarray:
    """
    Preprocess a garment product image for CatVTON inference.

    Steps:
        1. Remove background (rembg with alpha, fallback to color threshold)
        2. Crop tightly to garment bounding box
        3. Scale to fit within canvas_size with margin
        4. Center on a 512x512 black canvas

    Args:
        image: Input PIL Image (any size, any mode)
        canvas_size: Output canvas size (default 512)

    Returns:
        numpy array: RGB image, shape (canvas_size, canvas_size, 3), dtype uint8
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

    rgb_np = _crop_to_bbox(rgb_np, alpha_np, margin=8)
    rgb_np = _center_on_canvas(rgb_np, canvas_size)
    return rgb_np


def _rembg_remove(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Use rembg to remove background and return (RGB, alpha)."""
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
    return rgb, alpha


def _crop_to_bbox(
    rgb: np.ndarray,
    alpha: np.ndarray | None,
    margin: int = 8,
) -> np.ndarray:
    """
    Crop to the tight bounding box of the garment.

    Args:
        rgb: RGB image
        alpha: alpha channel (if available), used for precise cropping.
               If None, uses luminance threshold fallback.
        margin: pixels of padding around the garment in the crop.
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
        return rgb

    x1 = max(0, xs.min() - margin)
    y1 = max(0, ys.min() - margin)
    x2 = min(w, xs.max() + margin)
    y2 = min(h, ys.max() + margin)

    crop = rgb[y1:y2, x1:x2]
    return crop


def _center_on_canvas(rgb: np.ndarray, canvas_size: int = 512) -> np.ndarray:
    """
    Scale garment to fit canvas with margin, then center on black canvas.

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

    canvas = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)
    x_offset = (canvas_size - new_w) // 2
    y_offset = (canvas_size - new_h) // 2
    canvas[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

    return canvas
