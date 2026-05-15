from __future__ import annotations

from typing import Mapping

import cv2
import numpy as np
from PIL import Image, ImageFilter


def _foreground_mask(arr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    white_bg = (val > 246) & (sat < 18)
    black_bg = val < 18
    mask = ~(white_bg | black_bg)
    return mask


def detect_pattern_strength(img: Image.Image) -> float:
    """Detect printed or woven pattern strength, including low-saturation pastel prints."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    if h < 16 or w < 16:
        return 0.0

    fg = _foreground_mask(arr)
    if int(fg.sum()) < max(64, int(h * w * 0.02)):
        fg = np.ones((h, w), dtype=bool)

    gray = arr.mean(axis=2)
    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx**2 + gy**2)
    fg_grad = grad[fg]
    if fg_grad.size == 0 or float(fg_grad.max()) <= 0:
        return 0.0

    strong_edge_threshold = max(8.0, float(np.percentile(fg_grad, 88)))
    edge_density = float(((grad > strong_edge_threshold) & fg).sum() / max(1, fg.sum()))
    edge_score = min(1.0, edge_density * 10.0)

    local_mean = np.asarray(
        Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.BoxBlur(radius=4)),
        dtype=np.float32,
    )
    local_var = (gray - local_mean) ** 2
    fg_local_var = local_var[fg]
    var_score = min(1.0, float(np.percentile(fg_local_var, 97)) / 900.0)

    fg_rgb = arr[fg]
    channel_range = (fg_rgb.max(axis=0) - fg_rgb.min(axis=0)) / 255.0
    color_range_score = min(1.0, float(channel_range.mean()) * 1.7)

    hsv = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1] / 255.0
    fg_sat = sat[fg]
    sat_score = min(1.0, float(np.percentile(fg_sat, 95)) * 1.8)

    combined = 0.35 * edge_score + 0.25 * var_score + 0.25 * color_range_score + 0.15 * sat_score
    return float(np.clip(combined, 0.0, 1.0))


def estimate_catvton_garment_region_from_change(
    *,
    catvton_result: Image.Image,
    person_image: Image.Image,
    pose_region: Mapping[str, int],
    garment_category: str,
) -> tuple[int, int, int, int] | None:
    """Estimate the full generated garment area from CatVTON-vs-person changes."""
    result = np.asarray(catvton_result.convert("RGB"), dtype=np.float32)
    person = np.asarray(person_image.convert("RGB").resize(catvton_result.size), dtype=np.float32)
    h, w = result.shape[:2]

    diff = np.abs(result - person).mean(axis=2)
    cat = (garment_category or "").lower()

    neck_y = int(pose_region.get("neck_y", int(h * 0.2)))
    waist_y = int(pose_region.get("waist_y", int(h * 0.52)))
    x0_pose = int(pose_region.get("x0", int(w * 0.35)))
    x1_pose = int(pose_region.get("x1", int(w * 0.65)))

    if any(k in cat for k in ("bottom", "pants", "lower")):
        y0_hint = waist_y
        y1_hint = int(h * 0.95)
    elif any(k in cat for k in ("skirt", "dress")):
        y0_hint = max(0, neck_y)
        y1_hint = int(h * 0.95)
    else:
        pose_h = max(1, waist_y - neck_y)
        y0_hint = max(0, neck_y - int(pose_h * 0.12))
        y1_hint = min(h, waist_y + int(pose_h * 0.18))

    roi = diff[y0_hint:y1_hint, :]
    if roi.size == 0:
        return None

    threshold = max(12.0, float(np.percentile(roi, 70)))
    change = roi >= threshold
    if int(change.sum()) < 40:
        return None

    kernel = np.ones((5, 5), dtype=np.uint8)
    change_u8 = cv2.morphologyEx(change.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(change_u8, connectivity=8)
    if num_labels <= 1:
        return None

    pose_cx = (x0_pose + x1_pose) / 2.0
    best_label = None
    best_score = -1.0
    for label in range(1, num_labels):
        x, y, comp_w, comp_h, area = stats[label]
        if area < 40:
            continue
        comp_x0 = int(x)
        comp_x1 = int(x + comp_w)
        overlap = max(0, min(comp_x1, x1_pose) - max(comp_x0, x0_pose))
        center_penalty = abs(((comp_x0 + comp_x1) / 2.0) - pose_cx) / max(1.0, w)
        score = float(area) + overlap * 20.0 - center_penalty * 500.0
        if score > best_score:
            best_label = label
            best_score = score

    if best_label is None:
        return None

    change_u8 = (labels == best_label).astype(np.uint8)
    rows = np.any(change_u8 > 0, axis=1)
    cols = np.any(change_u8 > 0, axis=0)
    if not rows.any() or not cols.any():
        return None

    y0 = y0_hint + int(np.where(rows)[0][0])
    y1 = y0_hint + int(np.where(rows)[0][-1]) + 1
    x0 = int(np.where(cols)[0][0])
    x1 = int(np.where(cols)[0][-1]) + 1

    x0 = min(x0, x0_pose)
    x1 = max(x1, x1_pose)
    y0 = min(y0, neck_y)
    y1 = max(y1, waist_y)

    pad_x = max(3, int((x1 - x0) * 0.04))
    pad_y = max(3, int((y1 - y0) * 0.03))
    return (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(w, x1 + pad_x),
        min(h, y1 + pad_y),
    )
