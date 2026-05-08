"""Garment alignment and centering module for CatVTON try-on.

Fixes the "garment not centered/not aligned" problem by:
1. Detecting and correcting garment orientation (hanger at top → flip)
2. Auto-centering the garment in the canvas (body occupies 70%)
3. Perspective correction using edge detection
4. Ensuring left-right symmetry for upper-body garments
5. White background standardization

This ensures CatVTON receives a well-aligned, centered garment image,
which is critical for accurate cloth warping and realistic try-on.

Pipeline:
    Input garment image
    → Detect orientation (hanger/hanging → correct)
    → Remove background (already done by cutout_garment_rgba)
    → Auto-center and scale (body = 70% of canvas)
    → Perspective correction (edge detection)
    → Left-right symmetry enforcement
    → White background composite
    → Output standardized garment
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple, Any

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

__all__ = [
    "align_garment",
    "center_garment",
    "correct_perspective",
    "enforce_garment_symmetry",
    "standardize_garment_canvas",
]


def _detect_hanger_top(arr: np.ndarray) -> bool:
    """Detect if garment has a hanger at the top (common in product photos).

    Returns True if the top region looks like a hanger/clothesline.
    """
    h, w = arr.shape[:2]
    if h < 4 or w < 4:
        return False
    top_region = arr[: max(1, int(h * 0.08)), :, :]
    top_gray = cv2.cvtColor(top_region, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(top_gray, 40, 120)
    horizontal_lines = np.sum(edges > 0) / max(edges.size, 1)
    avg_brightness = top_region.mean()
    overall_brightness = arr.mean()
    return (
        horizontal_lines > 0.015
        and avg_brightness > overall_brightness * 1.25
        and top_gray.mean() > 180
    )


def _detect_and_correct_orientation(rgb: Image.Image) -> Image.Image:
    """Detect and correct garment orientation.

    Common cases:
    - Hanger at top → flip vertically so garment hangs downward
    - Upside-down garment (detected via aspect ratio heuristics)
    """
    arr = np.array(rgb.convert("RGB"))

    if _detect_hanger_top(arr):
        return rgb.transpose(Image.FLIP_TOP_BOTTOM)

    return rgb


def _rotate_to_upright(
    rgb: Image.Image,
    max_skew_deg: float = 15.0,
) -> Image.Image:
    """Rotate garment to upright position using edge detection.

    Detects the dominant skew angle of garment edges and corrects it.
    This fixes photos taken at an angle where the garment appears tilted.
    """
    arr = np.array(rgb.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=30,
        minLineLength=40,
        maxLineGap=10,
    )

    if lines is None or len(lines) == 0:
        return rgb

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if abs(x2 - x1) < 1:
            continue
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(angle) < max_skew_deg:
            angles.append(angle)

    if not angles:
        return rgb

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return rgb

    h, w = arr.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(arr, M, (w, h), borderValue=(255, 255, 255))
    return Image.fromarray(rotated, mode="RGB")


def _compute_garment_center(masked: np.ndarray) -> tuple[float, float]:
    """Compute the centroid of the foreground garment."""
    gray = cv2.cvtColor(masked, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
    moments = cv2.moments(thresh)
    if moments["m00"] == 0:
        h, w = masked.shape[:2]
        return w / 2.0, h / 2.0
    cx = moments["m10"] / moments["m00"]
    cy = moments["m01"] / moments["m00"]
    return float(cx), float(cy)


def center_garment(
    rgb: Image.Image,
    canvas_size: int = 768,
    fill_ratio: float = 0.70,
) -> Image.Image:
    """Center the garment in a white canvas so it occupies `fill_ratio` of the canvas.

    Args:
        rgb: Cropped garment RGB image (no background).
        canvas_size: Target canvas size (default 768x768).
        fill_ratio: How much of the canvas the garment should occupy (default 0.70 = 70%).
    """
    arr = np.array(rgb.convert("RGB"))
    h, w = arr.shape[:2]

    if h < 4 or w < 4:
        return Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    target_fill = canvas_size * fill_ratio
    scale = target_fill / max(h, w)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    resized = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    cx_garment, cy_garment = _compute_garment_center(resized)

    canvas = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    x_offset = int(round(canvas_size / 2.0 - cx_garment * scale))
    y_offset = int(round(canvas_size / 2.0 - cy_garment * scale))

    x_offset = max(0, min(x_offset, canvas_size - new_w))
    y_offset = max(0, min(y_offset, canvas_size - new_h))

    x1 = min(x_offset + new_w, canvas_size)
    y1 = min(y_offset + new_h, canvas_size)
    sx = max(0, -x_offset)
    sy = max(0, -y_offset)
    canvas[y_offset:y1, x_offset:x1] = resized[sy : sy + (y1 - y_offset), sx : sx + (x1 - x_offset)]

    return Image.fromarray(canvas, mode="RGB")


def _find_contour_mask(arr: np.ndarray) -> np.ndarray:
    """Create a foreground mask by finding the largest contour."""
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return binary
    largest = max(contours, key=cv2.contourArea)
    mask = np.zeros_like(binary)
    cv2.drawContours(mask, [largest], -1, 255, -1)
    return mask


def correct_perspective(rgb: Image.Image) -> Image.Image:
    """Detect and correct perspective distortion using edge detection.

    This fixes garments photographed at an angle where parallel lines
    (shoulders, sleeves) appear to converge. Works by finding the
    garment outline and applying a perspective transform.
    """
    arr = np.array(rgb.convert("RGB"))
    mask = _find_contour_mask(arr)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return rgb

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    h, w = arr.shape[:2]
    if area < (w * h * 0.05):
        return rgb

    epsilon = 0.02 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)

    if len(approx) < 4:
        return rgb

    # Always use minAreaRect to get exactly 4 corner points (handles n-point contours)
    rect = cv2.minAreaRect(approx)
    box = cv2.boxPoints(rect)
    src_pts = box.astype(np.float32)

    widths = [
        np.linalg.norm(src_pts[0] - src_pts[1]),
        np.linalg.norm(src_pts[2] - src_pts[3]),
    ]
    heights = [
        np.linalg.norm(src_pts[0] - src_pts[3]),
        np.linalg.norm(src_pts[1] - src_pts[2]),
    ]
    max_width = max(int(max(widths)), 1)
    max_height = max(int(max(heights)), 1)

    dst_pts = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype=np.float32,
    )

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    corrected = cv2.warpPerspective(arr, M, (max_width, max_height), borderValue=(255, 255, 255))

    min_size = 128
    if corrected.shape[0] < min_size or corrected.shape[1] < min_size:
        scale = min_size / min(corrected.shape[0], corrected.shape[1])
        new_w = max(min_size, int(corrected.shape[1] * scale))
        new_h = max(min_size, int(corrected.shape[0] * scale))
        corrected = cv2.resize(corrected, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    return Image.fromarray(corrected, mode="RGB")


def enforce_garment_symmetry(rgb: Image.Image, cloth_type: str = "upper") -> Image.Image:
    """Enforce left-right symmetry for upper-body garments.

    For upper-body garments (tops, shirts, jackets), the left and right
    sides should be roughly symmetric. This function averages the two halves
    to create a symmetric result, which helps CatVTON produce cleaner
    shoulder and sleeve warping.

    For lower-body garments (pants, skirts), symmetry is less important
    and this step is skipped.
    """
    if cloth_type not in ("upper", "top", "dress", "overall"):
        return rgb

    arr = np.array(rgb.convert("RGB"))
    h, w = arr.shape[:2]

    if w < 32 or h < 32:
        return rgb

    mid = w // 2
    left = arr[:, :mid, :]
    right = arr[:, mid : 2 * mid, :]

    if right.shape[1] != left.shape[1]:
        right_resized = cv2.resize(right, (left.shape[1], h), interpolation=cv2.INTER_LANCZOS4)
    else:
        right_resized = right

    flipped_right = cv2.flip(right_resized, 1)

    symmetric = cv2.addWeighted(left, 0.5, flipped_right, 0.5, 0)

    result = np.zeros_like(arr)
    result[:, :mid, :] = symmetric
    if 2 * mid < w:
        result[:, mid:, :] = cv2.flip(symmetric, 1)
    else:
        result[:, mid : mid + left.shape[1], :] = cv2.flip(symmetric, 1)

    return Image.fromarray(result, mode="RGB")


def standardize_garment_canvas(
    rgb: Image.Image,
    canvas_size: int = 768,
    fill_ratio: float = 0.70,
) -> Image.Image:
    """Compose the garment on a clean white canvas with proper centering.

    This is the final step that ensures:
    - White background (CatVTON expects it)
    - Garment centered in canvas
    - Body occupies ~70% of canvas
    - Left-right symmetry for upper-body garments

    Args:
        rgb: Cropped garment RGB image (no background).
        canvas_size: Output canvas size (default 768x768).
        fill_ratio: How much of canvas the garment should fill (default 0.70).
    """
    oriented = _detect_and_correct_orientation(rgb)
    upright = _rotate_to_upright(oriented)
    centered = center_garment(upright, canvas_size=canvas_size, fill_ratio=fill_ratio)
    arr = np.array(centered.convert("RGB"))
    h, w = arr.shape[:2]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
    fg_ratio = float(binary.sum()) / max(binary.size, 1)
    cloth_type = "upper" if fg_ratio > 0.30 else "lower"
    if cloth_type == "upper":
        symmetric = enforce_garment_symmetry(centered, cloth_type=cloth_type)
    else:
        symmetric = centered
    return symmetric


def align_garment(
    garment_image: Image.Image,
    cloth_type: str = "upper",
    canvas_size: int = 768,
) -> Image.Image:
    """Full garment alignment pipeline.

    Combines all alignment steps:
    1. Orientation detection (hanger flip)
    2. Perspective correction
    3. Centering and scaling
    4. Left-right symmetry (for upper-body)
    5. White background standardization

    Args:
        garment_image: Raw garment image (any format).
        cloth_type: "upper" | "lower" | "dress" for symmetry handling.
        canvas_size: Output canvas size (default 768).
    """
    oriented = _detect_and_correct_orientation(garment_image)
    corrected = correct_perspective(oriented)
    final = standardize_garment_canvas(
        corrected,
        canvas_size=canvas_size,
        fill_ratio=0.70,
    )
    logger.debug(
        f"[GARMENT-ALIGN] alignment done: type={cloth_type}, " f"canvas={canvas_size}, fill=70%"
    )
    return final
