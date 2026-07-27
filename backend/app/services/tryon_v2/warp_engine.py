"""Deterministic 2D warp + CatVTON hybrid engine for Try-on v2.

Goal: keep identity/background, only replace garment area using geometric
warps or Warp+CatVTON hybrid blending. Not a physics simulation; it's a
stable, explainable heuristic.

v2 modes:
- `strict`/`balanced`: warp-based geometric fitting with QC gate
- `replace`: AI generation (catvton → bailian → remote → warp → diffusion)
- `realistic`: CatVTON deep learning
- `professional`: CatVTON + postprocessing + quality scoring
- `hybrid`: Warp pixel-perfect + CatVTON realism overlay with saturation-aware
  drape_alpha (warp handles color/pattern, CatVTON adds shadow/lighting)

Warp engine uses MediaPipe Pose keypoints (shoulders/hips/ankles/knees) for
accurate garment placement; falls back to gradient energy estimation if
MediaPipe is unavailable. The two-stage knee-aware pants warp preserves
pattern symmetry at knee-bend vs single-taper warp.

Usage:
  from app.services.tryon_v2.warp_engine import tryon_top_warp_preserve
  result, meta = tryon_top_warp_preserve(person_image, garment_image)

  # hybrid mode:
  from app.services.tryon_v2.warp_engine import tryon_hybrid_warp_catvton
  result, meta = tryon_hybrid_warp_catvton(
      person_image, garment_image, catvton_result, garment_category)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter

from app.services.tryon_pattern_utils import (
    detect_pattern_strength,
    estimate_catvton_garment_region_from_change,
)
from app.services.tryon_v2.garment_struct import cutout_garment_rgba, split_pants_parts
from app.services.tryon_v2.pose_utils import detect_pose_keypoints, get_body_bounds_from_keypoints

logger = logging.getLogger(__name__)


@dataclass
class WarpMetadata:
    engine: str
    waistband_box: tuple[int, int, int, int]
    left_leg_box: tuple[int, int, int, int]
    right_leg_box: tuple[int, int, int, int]
    alpha_feather_px: int


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _alpha_band_width(alpha: np.ndarray, y_center: int, *, threshold: int = 20) -> int:
    """Measure visible alpha width around a row band."""
    h, w = alpha.shape[:2]
    if h < 2 or w < 2:
        return 0
    y0 = max(0, int(y_center) - 2)
    y1 = min(h, int(y_center) + 3)
    band = alpha[y0:y1, :] > threshold
    if not band.any():
        return 0
    xs = np.where(band.max(axis=0))[0]
    if xs.size == 0:
        return 0
    return int(xs[-1] - xs[0] + 1)


def _is_denim_like_garment(garment_image: Image.Image) -> bool:
    """Detect blue denim-like lower garments for conservative postprocessing."""
    try:
        cutout = cutout_garment_rgba(garment_image).cropped.convert("RGBA")
        arr = np.asarray(cutout, dtype=np.uint8)
        alpha = arr[:, :, 3] > 128
        if int(alpha.sum()) < 128:
            return False

        rgb = arr[:, :, :3][alpha]
        hsv = cv2.cvtColor(rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2HSV).reshape(-1, 3)
        hue = hsv[:, 0].astype(np.float32)
        sat = hsv[:, 1].astype(np.float32)
        val = hsv[:, 2].astype(np.float32)
        blue = (hue >= 86.0) & (hue <= 128.0) & (sat >= 18.0) & (val >= 35.0)
        blue_ratio = float(blue.mean())
        sat_median = float(np.median(sat))
        val_median = float(np.median(val))
        value_std = float(np.std(val))
        pattern_strength = _detect_pattern_strength(garment_image)
        gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
        gy, gx = np.gradient(gray)
        texture_signal = float(np.mean(np.sqrt(gx * gx + gy * gy)[alpha]))
        if pattern_strength >= 0.82 and val_median < 105.0 and sat_median < 78.0:
            logger.info(
                "catvton_color_fidelity_spatial: skipping denim-like lower handling "
                "for dark structured pattern "
                "(pattern_strength=%.3f, val_median=%.1f, sat_median=%.1f)",
                pattern_strength,
                val_median,
                sat_median,
            )
            return False
        if pattern_strength >= 0.78 and blue_ratio < 0.94:
            logger.info(
                "catvton_color_fidelity_spatial: skipping denim-like lower handling "
                "for strong repeating pattern (pattern_strength=%.3f, blue_ratio=%.3f)",
                pattern_strength,
                blue_ratio,
            )
            return False
        return (
            blue_ratio >= 0.28
            and sat_median >= 22.0
            and (value_std >= 18.0 or texture_signal >= 5.0)
        )
    except Exception:
        return False


def _assess_lower_warp_layer_qc(
    layer_np: np.ndarray,
    *,
    lower_warp_meta: WarpMetadata | None = None,
) -> dict:
    """Reject lower warped layers that look like stretched product-photo patches."""
    alpha = layer_np[:, :, 3] if layer_np.ndim == 3 and layer_np.shape[2] >= 4 else None
    if alpha is None:
        return {"passed": False, "reasons": ["missing_alpha"]}

    mask = alpha > 20
    if int(mask.sum()) < 128:
        return {"passed": False, "reasons": ["empty_alpha"]}

    ys, xs = np.where(mask)
    x0, x1 = int(xs.min()), int(xs.max() + 1)
    y0, y1 = int(ys.min()), int(ys.max() + 1)
    h, w = mask.shape
    bbox_w = max(1, x1 - x0)
    bbox_h = max(1, y1 - y0)
    coverage = float(mask.mean())

    row_widths: list[int] = []
    rel_rows: list[float] = []
    for y in range(y0, y1):
        row_x = np.where(mask[y, :])[0]
        if row_x.size:
            row_widths.append(int(row_x[-1] - row_x[0] + 1))
            rel_rows.append((y - y0) / float(bbox_h))

    widths = np.asarray(row_widths, dtype=np.float32)
    rel = np.asarray(rel_rows, dtype=np.float32)
    reasons: list[str] = []
    horizontal_drag_score = 0.0
    top_band_coverage = 0.0
    waistband_smear_score = 0.0
    hem_bright_leak_score = 0.0
    if widths.size:
        top_widths = widths[rel <= 0.16]
        leg_widths = widths[(rel >= 0.28) & (rel <= 0.92)]
        if top_widths.size and leg_widths.size:
            top_p95 = float(np.percentile(top_widths, 95))
            leg_med = float(max(1.0, np.median(leg_widths)))
            horizontal_drag_score = top_p95 / leg_med
            top_band_coverage = float(top_widths.size) / float(max(1, bbox_h))
            if horizontal_drag_score > 1.38 and top_band_coverage < 0.18:
                reasons.append("horizontal_waistband_drag")

    rgb = layer_np[:, :, :3].astype(np.float32)
    gray = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(
        np.float32
    )
    hsv = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    if bbox_h >= 24 and bbox_w >= 24:
        top_y1 = min(y1, y0 + max(10, int(bbox_h * 0.14)))
        top_mask = mask[y0:top_y1, x0:x1]
        if np.any(top_mask):
            top_gray = gray[y0:top_y1, x0:x1]
            gy, gx = np.gradient(top_gray)
            gx_mean = float(np.mean(np.abs(gx)[top_mask])) if np.any(top_mask) else 0.0
            gy_mean = float(np.mean(np.abs(gy)[top_mask])) if np.any(top_mask) else 0.0
            waistband_smear_score = min(4.0, gy_mean / max(gx_mean, 1.0))
            if waistband_smear_score > 1.9 and top_band_coverage < 0.20:
                reasons.append("waistband_texture_smear")

        bottom_y0 = max(y0, y1 - max(12, int(bbox_h * 0.12)))
        mid_y0 = y0 + max(12, int(bbox_h * 0.30))
        mid_y1 = min(y1, y0 + max(24, int(bbox_h * 0.72)))
        bottom_mask = mask[bottom_y0:y1, x0:x1]
        mid_mask = mask[mid_y0:mid_y1, x0:x1]
        if np.any(bottom_mask) and np.any(mid_mask):
            bottom_v = float(hsv[bottom_y0:y1, x0:x1, 2][bottom_mask].mean())
            mid_v = float(hsv[mid_y0:mid_y1, x0:x1, 2][mid_mask].mean())
            bottom_s = float(hsv[bottom_y0:y1, x0:x1, 1][bottom_mask].mean())
            mid_s = float(hsv[mid_y0:mid_y1, x0:x1, 1][mid_mask].mean())
            hem_bright_leak_score = max(0.0, (bottom_v - mid_v) / 28.0) + max(
                0.0, (mid_s - bottom_s) / 38.0
            )
            if hem_bright_leak_score > 1.15:
                reasons.append("hem_background_leak")

    labels_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8),
        8,
    )
    component_count = max(0, labels_count - 1)
    largest_component_ratio = 1.0
    if component_count > 0:
        areas = stats[1:, cv2.CC_STAT_AREA].astype(np.float32)
        largest_component_ratio = float(areas.max() / max(1.0, areas.sum()))
        if component_count > 4 and largest_component_ratio < 0.78:
            reasons.append("fragmented_warp_layer")

    if lower_warp_meta is not None:
        wx0, wy0, wx1, wy1 = lower_warp_meta.waistband_box
        lx0, _ly0, lx1, _ly1 = lower_warp_meta.left_leg_box
        rx0, _ry0, rx1, _ry1 = lower_warp_meta.right_leg_box
        waist_w = max(0, wx1 - wx0)
        legs_w = max(1, max(lx1, rx1) - min(lx0, rx0))
        waist_h = max(0, wy1 - wy0)
        if waist_w > legs_w * 1.32 and waist_h < bbox_h * 0.16:
            reasons.append("waistband_wider_than_leg_structure")

    if coverage > 0.24:
        reasons.append("excessive_lower_layer_coverage")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "alpha_coverage": round(coverage, 4),
        "bbox": [x0, y0, x1, y1],
        "bbox_aspect": round(float(bbox_w / max(1, bbox_h)), 4),
        "horizontal_drag_score": round(float(horizontal_drag_score), 4),
        "top_band_coverage": round(float(top_band_coverage), 4),
        "waistband_smear_score": round(float(waistband_smear_score), 4),
        "hem_bright_leak_score": round(float(hem_bright_leak_score), 4),
        "component_count": int(component_count),
        "largest_component_ratio": round(float(largest_component_ratio), 4),
    }


def _accept_lower_structure_qc_for_texture(qc: dict, *, denim_like: bool) -> bool:
    """Allow denim texture transfer through one conservative false-positive gate."""
    if qc.get("passed", False):
        return True
    if not denim_like:
        return False

    reasons = set(qc.get("reasons") or [])
    nonfatal_denim_reasons = {"waistband_texture_smear"}
    if not reasons or not reasons.issubset(nonfatal_denim_reasons):
        return False

    alpha_coverage = float(qc.get("alpha_coverage", 1.0) or 1.0)
    hem_leak = float(qc.get("hem_bright_leak_score", 1.0) or 0.0)
    component_count = int(qc.get("component_count", 99) or 0)
    largest_component_ratio = float(qc.get("largest_component_ratio", 0.0) or 0.0)
    return (
        alpha_coverage <= 0.20
        and hem_leak < 0.35
        and component_count <= 2
        and largest_component_ratio >= 0.92
    )


def _estimate_lower_structure_guides(person_image: Image.Image) -> dict:
    """Estimate lower-body guide points for waistband and shoe-safe compositing."""
    pw, ph = person_image.size
    kpts = detect_pose_keypoints(person_image) or {}
    bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "bottom") if kpts else {}
    valid = bool(bounds.get("valid"))

    waist_y = int(bounds.get("waist_y", int(ph * 0.48))) if valid else int(ph * 0.48)
    ankle_y = int(bounds.get("ankle_y", int(ph * 0.92))) if valid else int(ph * 0.92)

    def _px_point(name: str) -> tuple[int, int] | None:
        pt = kpts.get(name)
        if not pt:
            return None
        return (
            _clamp_int(int(round(pt[0] * pw)), 0, pw - 1),
            _clamp_int(int(round(pt[1] * ph)), 0, ph - 1),
        )

    left_hip = _px_point("left_hip")
    right_hip = _px_point("right_hip")
    left_ankle = _px_point("left_ankle")
    right_ankle = _px_point("right_ankle")

    return {
        "waist_y": _clamp_int(waist_y, int(ph * 0.30), int(ph * 0.60)),
        "ankle_y": _clamp_int(ankle_y, int(ph * 0.72), ph - 1),
        "left_hip": left_hip,
        "right_hip": right_hip,
        "left_ankle": left_ankle,
        "right_ankle": right_ankle,
        "pose_valid": valid,
    }


def _interpolate_body_curve(
    width: int,
    points: list[tuple[int, int]],
    *,
    default_y: int,
) -> np.ndarray:
    """Build a smooth per-column guide curve from sparse pose points."""
    if width <= 0:
        return np.zeros((0,), dtype=np.float32)
    if not points:
        return np.full((width,), float(default_y), dtype=np.float32)

    xs: list[int] = []
    ys: list[int] = []
    for x, y in sorted(points, key=lambda item: item[0]):
        if xs and x == xs[-1]:
            ys[-1] = int(round((ys[-1] + y) * 0.5))
        else:
            xs.append(int(x))
            ys.append(int(y))

    if len(xs) == 1:
        return np.full((width,), float(ys[0]), dtype=np.float32)

    curve = np.interp(np.arange(width, dtype=np.float32), np.asarray(xs), np.asarray(ys))
    kernel = max(5, min(width // 8 * 2 + 1, 61))
    if kernel % 2 == 0:
        kernel += 1
    curve = cv2.GaussianBlur(curve.reshape(1, width).astype(np.float32), (kernel, 1), 0).reshape(
        width
    )
    return curve.astype(np.float32)


def _build_lower_structure_blend_masks(
    person_image: Image.Image,
    layer_alpha: np.ndarray,
    *,
    guides: dict | None = None,
    prefer_layer_extent: bool = False,
) -> tuple[np.ndarray, dict]:
    """Build soft waistband and shoe-aware masks for lower fidelity compositing."""
    h, w = layer_alpha.shape[:2]
    if h <= 0 or w <= 0:
        return np.zeros((h, w), dtype=np.float32), {"reason": "empty"}

    guides = guides or _estimate_lower_structure_guides(person_image)
    waist_y = int(guides.get("waist_y", int(h * 0.48)))
    ankle_y = int(guides.get("ankle_y", int(h * 0.92)))
    left_hip = guides.get("left_hip")
    right_hip = guides.get("right_hip")
    left_ankle = guides.get("left_ankle")
    right_ankle = guides.get("right_ankle")

    waist_pts: list[tuple[int, int]] = []
    if left_hip is not None:
        waist_pts.append((left_hip[0], left_hip[1]))
    if right_hip is not None:
        waist_pts.append((right_hip[0], right_hip[1]))
    if left_hip is not None and right_hip is not None:
        waist_pts.append(
            (
                ((left_hip[0] + right_hip[0]) // 2),
                int((left_hip[1] + right_hip[1]) * 0.5 + h * 0.012),
            )
        )
    waist_curve = _interpolate_body_curve(w, waist_pts, default_y=waist_y)

    ankle_pts: list[tuple[int, int]] = []
    if left_ankle is not None:
        ankle_pts.append((left_ankle[0], left_ankle[1]))
    if right_ankle is not None:
        ankle_pts.append((right_ankle[0], right_ankle[1]))
    if left_ankle is not None and right_ankle is not None:
        ankle_pts.append(
            (((left_ankle[0] + right_ankle[0]) // 2), max(left_ankle[1], right_ankle[1]))
        )
    ankle_curve = _interpolate_body_curve(w, ankle_pts, default_y=ankle_y)

    yy = np.arange(h, dtype=np.float32)[:, None]
    top_soft = max(10.0, h * 0.030)
    top_mask = np.clip((yy - (waist_curve[None, :] - top_soft)) / (top_soft * 2.2), 0.0, 1.0)
    layer_top_y = None
    if prefer_layer_extent and (layer_alpha > 0.02).any():
        alpha_rows = np.where((layer_alpha > 0.02).any(axis=1))[0]
        if alpha_rows.size:
            layer_top_y = int(alpha_rows[0])
            layer_top_soft = max(10.0, h * 0.014)
            layer_top_mask = np.clip(
                (yy - layer_top_y) / max(1.0, layer_top_soft),
                0.0,
                1.0,
            )
            top_mask = np.maximum(top_mask, layer_top_mask)

    bottom_start = ankle_curve[None, :] - max(8.0, h * 0.015)
    bottom_end = ankle_curve[None, :] + max(14.0, h * 0.045)
    bottom_mask = 1.0 - np.clip(
        (yy - bottom_start) / np.maximum(1.0, bottom_end - bottom_start), 0.0, 1.0
    )

    person_rgb = np.asarray(
        person_image.convert("RGB").resize((w, h), Image.Resampling.BILINEAR),
        dtype=np.uint8,
    )
    hsv = cv2.cvtColor(person_rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    bright = person_rgb.mean(axis=2) > 188.0
    low_sat = hsv[:, :, 1] < 42.0
    dark_shoe = (person_rgb.mean(axis=2) < 46.0) & (hsv[:, :, 1] < 95.0)
    lower_zone = yy[:, 0] >= max(0, int(np.min(ankle_curve) + h * 0.035))
    shoe_region = lower_zone[:, None] & (bright & low_sat | dark_shoe)
    if shoe_region.any():
        shoe_region = (
            cv2.dilate(shoe_region.astype(np.uint8) * 255, np.ones((5, 5), np.uint8), iterations=1)
            > 0
        )
        bottom_mask = np.where(shoe_region, 0.0, bottom_mask)

    alpha_gate = np.clip(layer_alpha / max(1e-6, float(layer_alpha.max())), 0.0, 1.0)
    blend_mask = np.clip(top_mask * bottom_mask, 0.0, 1.0) * (alpha_gate > 0.02).astype(np.float32)
    if blend_mask.any():
        blur_px = max(5, int(min(w, h) * 0.012))
        kernel = blur_px * 2 + 1
        blend_mask = cv2.GaussianBlur(blend_mask.astype(np.float32), (kernel, kernel), 0)
        blend_mask = np.clip(blend_mask * (alpha_gate > 0.02).astype(np.float32), 0.0, 1.0)

    meta = {
        "waist_y": waist_y,
        "ankle_y": ankle_y,
        "top_soft_px": round(float(top_soft), 2),
        "prefer_layer_extent": bool(prefer_layer_extent),
        "layer_top_y": layer_top_y,
        "shoe_region_coverage": round(float(shoe_region.mean()) if shoe_region.any() else 0.0, 4),
        "mask_coverage": round(float((blend_mask > 0.08).mean()), 4),
    }
    return blend_mask.astype(np.float32), meta


def _refine_lower_structure_overlay_mask(
    shaded_alpha: np.ndarray,
    *,
    warp_meta: WarpMetadata | None = None,
    structured_pattern_lower: bool = False,
) -> tuple[np.ndarray, dict]:
    """Trim structured-pattern overlay halos before CatVTON drape blending."""
    mask = np.clip(shaded_alpha.astype(np.float32), 0.0, 1.0)
    if mask.size == 0:
        return mask, {"reason": "empty"}

    raw_coverage = float((mask > 0.08).mean())
    if not structured_pattern_lower:
        return mask, {
            "structured_pattern_lower": False,
            "raw_coverage": round(raw_coverage, 4),
            "refined_coverage": round(raw_coverage, 4),
        }

    refined = (mask > 0.10).astype(np.uint8) * 255
    h, _w = refined.shape
    top_cut = 0
    if warp_meta is not None and warp_meta.waistband_box != (0, 0, 0, 0):
        _wx0, wy0, _wx1, _wy1 = warp_meta.waistband_box
        top_cut = max(0, wy0 - max(2, int(h * 0.006)))
        if top_cut > 0:
            refined[:top_cut, :] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    refined = cv2.morphologyEx(refined, cv2.MORPH_OPEN, kernel, iterations=1)
    refined_mask = (refined > 0).astype(np.float32)
    return refined_mask, {
        "structured_pattern_lower": True,
        "raw_coverage": round(raw_coverage, 4),
        "refined_coverage": round(float(refined_mask.mean()), 4),
        "top_cut": int(top_cut),
    }


def _restore_structured_lower_waistband_color(
    result_rgb: Image.Image,
    *,
    source_layer_rgba: Image.Image,
    warp_meta: WarpMetadata | None = None,
    raw_mask_image: Image.Image | None = None,
) -> tuple[Image.Image, dict]:
    """Lock waistband color/details back after AI drape blend without changing silhouette."""
    if warp_meta is None or warp_meta.waistband_box == (0, 0, 0, 0):
        return result_rgb, {"applied": False, "reason": "no_waistband_box"}

    wx0, wy0, wx1, wy1 = warp_meta.waistband_box
    if wx1 <= wx0 or wy1 <= wy0:
        return result_rgb, {"applied": False, "reason": "invalid_waistband_box"}

    base = np.asarray(result_rgb.convert("RGB"), dtype=np.float32)
    source_rgba = np.asarray(
        source_layer_rgba.convert("RGBA").resize(result_rgb.size, Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    source_rgb = source_rgba[:, :, :3]
    source_alpha = source_rgba[:, :, 3] / 255.0
    h, w = source_alpha.shape

    y_pad = max(4, int(h * 0.007))
    x_pad = max(10, int(w * 0.018))
    sx0 = _clamp_int(wx0 - x_pad, 0, w - 1)
    sx1 = _clamp_int(wx1 + x_pad, sx0 + 1, w)
    sy0 = _clamp_int(wy0 - y_pad, 0, h - 1)
    sy1 = _clamp_int(wy1 + y_pad, sy0 + 1, h)

    band_mask = np.zeros((h, w), dtype=np.float32)
    band_mask[sy0:sy1, sx0:sx1] = 1.0

    vertical = np.zeros((h, w), dtype=np.float32)
    band_h = max(1, sy1 - sy0)
    yy = np.arange(sy0, sy1, dtype=np.float32)
    center = sy0 + band_h * 0.48
    sigma = max(3.0, band_h * 0.32)
    weights = np.exp(-0.5 * ((yy - center) / sigma) ** 2).astype(np.float32)
    weights = np.clip(weights / max(1e-6, float(weights.max())), 0.0, 1.0)
    vertical[sy0:sy1, sx0:sx1] = weights[:, None]

    restore_mask = np.clip(source_alpha * band_mask * vertical, 0.0, 1.0)
    restore_mask = np.clip((restore_mask - 0.04) / 0.28, 0.0, 1.0)
    if float(restore_mask.max()) <= 0.01:
        return result_rgb, {"applied": False, "reason": "empty_restore_mask"}

    restore_strength = 0.98
    blend = restore_mask[:, :, None] * restore_strength
    restored = base * (1.0 - blend) + source_rgb * blend
    out = Image.fromarray(np.clip(restored, 0, 255).astype(np.uint8), mode="RGB")
    return out, {
        "applied": True,
        "restore_strength": restore_strength,
        "source": "pre_shading_warp_layer",
        "region": [int(sx0), int(sy0), int(sx1), int(sy1)],
        "mask_max": round(float(restore_mask.max()), 4),
        "mask_mean": round(float(restore_mask.mean()), 4),
    }


def _detect_light_structured_lower_waistband(
    layer_np: np.ndarray,
    *,
    warp_meta: WarpMetadata | None = None,
) -> tuple[np.ndarray | None, dict]:
    """Find light, low-saturation waistband pixels that should not inherit leg texture."""
    if warp_meta is None or warp_meta.waistband_box == (0, 0, 0, 0):
        return None, {"applied": False, "reason": "no_waistband_box"}
    if layer_np.ndim != 3 or layer_np.shape[2] < 4:
        return None, {"applied": False, "reason": "invalid_layer"}

    h, w = layer_np.shape[:2]
    wx0, wy0, wx1, wy1 = warp_meta.waistband_box
    if wx1 <= wx0 or wy1 <= wy0:
        return None, {"applied": False, "reason": "invalid_waistband_box"}

    y_pad = max(4, int(h * 0.006))
    x_pad = max(8, int(w * 0.012))
    sx0 = _clamp_int(wx0 - x_pad, 0, w - 1)
    sx1 = _clamp_int(wx1 + x_pad, sx0 + 1, w)
    sy0 = _clamp_int(wy0 - y_pad, 0, h - 1)
    sy1 = _clamp_int(wy1 + y_pad, sy0 + 1, h)

    roi = np.clip(layer_np[sy0:sy1, sx0:sx1, :], 0, 255).astype(np.uint8)
    if roi.size == 0:
        return None, {"applied": False, "reason": "empty_roi"}

    alpha = roi[:, :, 3] > 28
    if int(alpha.sum()) < 32:
        return None, {"applied": False, "reason": "empty_alpha"}

    rgb = roi[:, :, :3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    bright = rgb.mean(axis=2) >= 168.0
    low_sat = hsv[:, :, 1] <= 72.0
    light = alpha & bright & low_sat
    light_ratio = float(light.sum()) / float(max(1, alpha.sum()))
    if light_ratio < 0.16:
        return None, {
            "applied": False,
            "reason": "not_light_waistband",
            "light_ratio": round(light_ratio, 4),
        }

    mask = np.zeros((h, w), dtype=np.float32)
    local = light.astype(np.float32)
    local = cv2.morphologyEx(
        local.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 5), np.uint8), iterations=1
    )
    local = cv2.GaussianBlur(local.astype(np.float32), (5, 5), 0)
    mask[sy0:sy1, sx0:sx1] = np.clip(local, 0.0, 1.0)
    return mask, {
        "applied": True,
        "region": [int(sx0), int(sy0), int(sx1), int(sy1)],
        "light_ratio": round(light_ratio, 4),
        "coverage": round(float((mask > 0.08).mean()), 4),
    }


def _restore_light_waistband_from_garment_cutout(
    layer_rgba: Image.Image,
    garment_image: Image.Image,
    *,
    warp_meta: WarpMetadata | None = None,
    structured_pattern_lower: bool = False,
) -> tuple[Image.Image, dict]:
    """Map a light product waistband onto the target waist before shading/bridge passes."""
    if not structured_pattern_lower or warp_meta is None or warp_meta.waistband_box == (0, 0, 0, 0):
        return layer_rgba, {"applied": False, "reason": "not_applicable"}

    wx0, wy0, wx1, wy1 = warp_meta.waistband_box
    if wx1 <= wx0 or wy1 <= wy0:
        return layer_rgba, {"applied": False, "reason": "invalid_waistband_box"}

    try:
        cutout = cutout_garment_rgba(garment_image).cropped.convert("RGBA")
    except Exception as exc:
        return layer_rgba, {"applied": False, "reason": f"cutout_failed:{exc}"}

    cut_np = np.asarray(cutout, dtype=np.uint8)
    alpha = cut_np[:, :, 3] > 48
    if int(alpha.sum()) < 64:
        return layer_rgba, {"applied": False, "reason": "empty_cutout_alpha"}

    rgb = cut_np[:, :, :3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    bright = rgb.mean(axis=2) >= 165.0
    low_sat = hsv[:, :, 1] <= 78.0
    light = alpha & bright & low_sat

    rows = np.where(alpha.any(axis=1))[0]
    if rows.size == 0:
        return layer_rgba, {"applied": False, "reason": "empty_rows"}
    top_limit = int(rows.min() + max(8, (rows.max() - rows.min() + 1) * 0.30))
    candidate_rows = []
    for yy in range(int(rows.min()), min(cut_np.shape[0], top_limit + 1)):
        row_alpha = alpha[yy, :]
        if int(row_alpha.sum()) < 8:
            continue
        light_ratio = float((light[yy, :] & row_alpha).sum()) / float(max(1, row_alpha.sum()))
        if light_ratio >= 0.32:
            candidate_rows.append(yy)
    if len(candidate_rows) < 3:
        return layer_rgba, {"applied": False, "reason": "no_light_waistband_rows"}

    by0 = max(int(rows.min()), min(candidate_rows) - 2)
    by1 = min(cut_np.shape[0], max(candidate_rows) + 3)
    band_alpha = alpha[by0:by1, :]
    cols = np.where(band_alpha.any(axis=0))[0]
    if cols.size < 8:
        return layer_rgba, {"applied": False, "reason": "narrow_light_waistband"}

    bx0 = max(0, int(cols.min()) - 2)
    bx1 = min(cut_np.shape[1], int(cols.max()) + 3)
    light_pixels = rgb[light]
    if light_pixels.size == 0:
        return layer_rgba, {"applied": False, "reason": "empty_light_pixels"}
    waistband_rgb = np.median(light_pixels.reshape(-1, 3), axis=0).astype(np.float32)
    return layer_rgba, {
        "applied": True,
        "mode": "detect_only",
        "source_band": [int(bx0), int(by0), int(bx1), int(by1)],
        "waistband_rgb": [round(float(v), 2) for v in waistband_rgb.tolist()],
    }


def _trim_lower_waistband_to_body_curve(
    layer_rgba: Image.Image,
    *,
    waistband_box: tuple[int, int, int, int],
    left_leg_box: tuple[int, int, int, int],
    right_leg_box: tuple[int, int, int, int],
    guides: dict | None = None,
) -> tuple[Image.Image, dict]:
    """Suppress horizontally smeared waistband pixels above the body waist curve."""
    if layer_rgba.mode != "RGBA":
        layer_rgba = layer_rgba.convert("RGBA")

    wx0, wy0, wx1, wy1 = waistband_box
    if wx1 <= wx0 or wy1 <= wy0:
        return layer_rgba, {"applied": False, "reason": "no_waistband_box"}

    arr = np.asarray(layer_rgba, dtype=np.uint8).copy()
    alpha = arr[:, :, 3]
    if alpha.max() <= 20:
        return layer_rgba, {"applied": False, "reason": "empty_alpha"}

    h, w = alpha.shape[:2]
    guides = guides or {}
    waist_y = int(guides.get("waist_y", (wy0 + wy1) // 2))
    left_hip = guides.get("left_hip")
    right_hip = guides.get("right_hip")

    waist_pts: list[tuple[int, int]] = []
    if left_hip is not None:
        waist_pts.append((left_hip[0], left_hip[1]))
    if right_hip is not None:
        waist_pts.append((right_hip[0], right_hip[1]))
    if left_hip is not None and right_hip is not None:
        waist_pts.append(
            (
                (left_hip[0] + right_hip[0]) // 2,
                int(round(min(left_hip[1], right_hip[1]) - max(1.0, h * 0.006))),
            )
        )
    waist_curve = _interpolate_body_curve(w, waist_pts, default_y=waist_y)

    band_h = max(2, wy1 - wy0)
    top_margin = max(3.0, band_h * 0.10)
    bottom_margin = max(5.0, band_h * 0.95)
    leg_y0 = min(left_leg_box[1], right_leg_box[1])
    band_bottom = min(max(wy1, leg_y0 + max(2, int(h * 0.004))), h)
    x_pad = max(5, int(w * 0.008))
    body_x0 = _clamp_int(min(left_leg_box[0], wx0) - x_pad, 0, w - 1)
    body_x1 = _clamp_int(max(right_leg_box[2], wx1) + x_pad, body_x0 + 1, w)

    yy = np.arange(h, dtype=np.float32)[:, None]
    top_curve = np.clip(waist_curve[None, :] - top_margin, 0.0, float(h))
    bottom_curve = np.clip(waist_curve[None, :] + bottom_margin, 0.0, float(band_bottom))
    curve_band = (
        (yy >= top_curve)
        & (yy <= bottom_curve)
        & (yy >= max(0, wy0 - max(4, int(h * 0.005))))
        & (yy <= band_bottom)
    )

    preserve = alpha > 20
    preserve[0 : max(0, wy0 - max(4, int(h * 0.005))), :] = False
    preserve[band_bottom:, :] = preserve[band_bottom:, :]
    preserve[:band_bottom, :body_x0] = False
    preserve[:band_bottom, body_x1:] = False
    preserve[:band_bottom, body_x0:body_x1] &= curve_band[:band_bottom, body_x0:body_x1]

    removed = (alpha > 20) & ~preserve
    if int(removed.sum()) == 0:
        return layer_rgba, {
            "applied": False,
            "reason": "nothing_removed",
            "body_x0": int(body_x0),
            "body_x1": int(body_x1),
        }

    arr[removed, 3] = 0
    arr[removed, :3] = 0
    return Image.fromarray(arr, mode="RGBA"), {
        "applied": True,
        "removed_ratio": round(float(removed.mean()), 4),
        "top_margin": round(float(top_margin), 2),
        "bottom_margin": round(float(bottom_margin), 2),
        "body_x0": int(body_x0),
        "body_x1": int(body_x1),
        "band_bottom": int(band_bottom),
    }


def _suppress_structured_lower_top_haze(
    shaded_alpha: np.ndarray,
    *,
    warp_meta: WarpMetadata | None = None,
    structured_pattern_lower: bool = False,
) -> tuple[np.ndarray, dict]:
    """Fade in the first few top rows to remove low-alpha gray haze."""
    alpha = np.clip(shaded_alpha.astype(np.float32), 0.0, 1.0)
    if not structured_pattern_lower or warp_meta is None:
        return alpha, {"applied": False, "reason": "not_structured"}

    top_rows = np.where((alpha > 0.01).any(axis=1))[0]
    if top_rows.size == 0:
        return alpha, {"applied": False, "reason": "empty_alpha"}

    first_row = int(top_rows[0])
    leg_top = min(warp_meta.left_leg_box[1], warp_meta.right_leg_box[1])
    fade_start = max(0, first_row - 1)
    fade_end = min(alpha.shape[0], max(leg_top + 10, fade_start + 12))
    if fade_end <= fade_start + 1:
        return alpha, {"applied": False, "reason": "fade_window_too_small"}

    ramp = np.linspace(0.0, 1.0, fade_end - fade_start, dtype=np.float32)[:, None]
    alpha[fade_start:fade_end, :] *= ramp
    return alpha, {
        "applied": True,
        "first_row": first_row,
        "fade_start": int(fade_start),
        "fade_end": int(fade_end),
    }


def _build_catvton_lower_upper_shape_mask(
    person_rgb: np.ndarray,
    ai_rgb: np.ndarray,
    *,
    layer_alpha: np.ndarray | None = None,
    warp_meta: WarpMetadata | None = None,
    structured_pattern_lower: bool = False,
) -> tuple[np.ndarray, dict]:
    """Extract the valid CatVTON waist/hip shape region for lower-garment recovery.

    This mask is intentionally shape-only. It should describe the upper pants area
    that CatVTON actually generated, without inventing a full-width horizontal band.
    """
    if not structured_pattern_lower or warp_meta is None:
        shape = np.zeros(person_rgb.shape[:2], dtype=np.float32)
        return shape, {"applied": False, "reason": "not_structured"}

    h, w = person_rgb.shape[:2]
    if ai_rgb.shape[:2] != (h, w):
        ai_rgb = np.asarray(
            Image.fromarray(np.clip(ai_rgb, 0, 255).astype(np.uint8), mode="RGB").resize(
                (w, h), Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )

    wx0, wy0, wx1, wy1 = warp_meta.waistband_box
    leg_top = min(warp_meta.left_leg_box[1], warp_meta.right_leg_box[1])
    body_x0 = _clamp_int(wx0 - max(6, int(w * 0.008)), 0, w - 1)
    body_x1 = _clamp_int(wx1 + max(6, int(w * 0.008)), body_x0 + 1, w)
    region_y0 = _clamp_int(wy0 + max(8, int((wy1 - wy0) * 0.20)), 0, h - 1)
    region_y1 = _clamp_int(
        max(
            leg_top + max(10, int(h * 0.010)),
            wy1 + max(22, int(h * 0.020)),
        ),
        region_y0 + 1,
        h,
    )
    if region_y1 <= region_y0 + 2:
        shape = np.zeros((h, w), dtype=np.float32)
        return shape, {"applied": False, "reason": "region_too_small"}

    ai_u8 = np.clip(ai_rgb, 0, 255).astype(np.uint8)
    person_u8 = np.clip(person_rgb, 0, 255).astype(np.uint8)
    diff = np.max(np.abs(ai_u8.astype(np.int16) - person_u8.astype(np.int16)), axis=2).astype(
        np.uint8
    )
    hsv = cv2.cvtColor(ai_u8, cv2.COLOR_RGB2HSV).astype(np.float32)
    val = hsv[:, :, 2]
    sat = hsv[:, :, 1]
    changed = diff > 18
    dark_generated = (val < 208.0) | ((val < 224.0) & (sat > 12.0))

    candidate = np.zeros((h, w), dtype=np.uint8)
    candidate[region_y0:region_y1, body_x0:body_x1] = 255
    candidate = (candidate > 0) & changed & dark_generated
    if candidate.any():
        candidate = cv2.morphologyEx(
            candidate.astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((5, 7), dtype=np.uint8),
            iterations=1,
        ).astype(bool)
        candidate = cv2.morphologyEx(
            candidate.astype(np.uint8),
            cv2.MORPH_OPEN,
            np.ones((3, 5), dtype=np.uint8),
            iterations=1,
        ).astype(bool)

    center_x = (wx0 + wx1) // 2
    row_filled = np.zeros((h, w), dtype=bool)
    connected_columns = 0
    if layer_alpha is not None and layer_alpha.shape[:2] == (h, w):
        existing = np.clip(layer_alpha.astype(np.float32), 0.0, 1.0) > 0.14
        for xx in range(body_x0, body_x1):
            lower_rows = np.where(existing[region_y0:region_y1, xx])[0]
            if lower_rows.size == 0:
                continue
            top_existing = int(region_y0 + lower_rows.min())
            candidate_rows = np.where(candidate[region_y0 : top_existing + 1, xx])[0]
            if candidate_rows.size < 3:
                continue
            top_candidate = int(region_y0 + candidate_rows.min())
            if top_existing - top_candidate < 8:
                continue
            row_filled[top_candidate:top_existing, xx] = True
            connected_columns += 1

    if not row_filled.any():
        for yy_idx in range(region_y0, region_y1):
            xs = np.where(candidate[yy_idx, body_x0:body_x1])[0]
            if xs.size < 6:
                continue
            xs = xs + body_x0
            splits = np.where(np.diff(xs) > 1)[0]
            starts = np.r_[0, splits + 1]
            ends = np.r_[splits, xs.size - 1]
            best = None
            best_score = None
            for s_idx, e_idx in zip(starts, ends):
                seg_x0 = int(xs[s_idx])
                seg_x1 = int(xs[e_idx]) + 1
                seg_w = seg_x1 - seg_x0
                seg_c = (seg_x0 + seg_x1) * 0.5
                score = abs(seg_c - center_x) - seg_w * 0.16
                if best is None or score < best_score:
                    best = (seg_x0, seg_x1)
                    best_score = score
            if best is not None:
                seg_x0, seg_x1 = best
                row_filled[yy_idx, seg_x0:seg_x1] = True

    if row_filled.any():
        row_filled = cv2.morphologyEx(
            row_filled.astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((9, 7), dtype=np.uint8),
            iterations=1,
        ).astype(bool)
        row_filled = cv2.morphologyEx(
            row_filled.astype(np.uint8),
            cv2.MORPH_OPEN,
            np.ones((5, 3), dtype=np.uint8),
            iterations=1,
        ).astype(bool)
        row_filled = _keep_significant_mask_components(
            row_filled,
            min_area_ratio=0.22,
            max_components=2,
        )

    shape_mask = cv2.GaussianBlur(row_filled.astype(np.float32), (7, 7), 0)
    shape_mask = np.clip(shape_mask, 0.0, 1.0)
    return shape_mask, {
        "applied": bool(row_filled.any()),
        "region_y0": int(region_y0),
        "region_y1": int(region_y1),
        "body_x0": int(body_x0),
        "body_x1": int(body_x1),
        "changed_ratio": round(float(changed[region_y0:region_y1, body_x0:body_x1].mean()), 4),
        "candidate_ratio": round(float(candidate.mean()), 4),
        "shape_ratio": round(float((shape_mask > 0.08).mean()), 4),
        "connected_columns": int(connected_columns),
    }


def _bridge_structured_lower_upper_texture(
    shaded_layer_np: np.ndarray,
    shaded_alpha: np.ndarray,
    ai_rgb: np.ndarray,
    *,
    person_rgb: np.ndarray | None = None,
    warp_meta: WarpMetadata | None = None,
    guides: dict | None = None,
    structured_pattern_lower: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Extend upper plaid texture into the AI waist/hip shape without flat repaint."""
    rgb = shaded_layer_np[:, :, :3].astype(np.float32).copy()
    alpha = np.clip(shaded_alpha.astype(np.float32), 0.0, 1.0).copy()
    if not structured_pattern_lower or warp_meta is None:
        return rgb, alpha, {"applied": False, "reason": "not_structured"}

    h, w = alpha.shape[:2]
    wx0, wy0, wx1, wy1 = warp_meta.waistband_box
    if wx1 <= wx0 or wy1 <= wy0:
        return rgb, alpha, {"applied": False, "reason": "no_waistband_box"}

    leg_top = min(warp_meta.left_leg_box[1], warp_meta.right_leg_box[1])
    body_x0 = _clamp_int(wx0 - max(6, int(w * 0.008)), 0, w - 1)
    body_x1 = _clamp_int(wx1 + max(6, int(w * 0.008)), body_x0 + 1, w)
    fill_y0 = _clamp_int(wy0 + max(8, int((wy1 - wy0) * 0.22)), 0, h - 1)
    fill_y1 = _clamp_int(
        min(leg_top + max(6, int(h * 0.006)), wy1 + max(4, int(h * 0.008))), fill_y0 + 1, h
    )
    if fill_y1 <= fill_y0 + 2:
        return rgb, alpha, {"applied": False, "reason": "fill_window_too_small"}

    ai_u8 = np.clip(ai_rgb, 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(ai_u8, cv2.COLOR_RGB2HSV).astype(np.float32)
    val = hsv[:, :, 2]
    sat = hsv[:, :, 1]
    darkness = (val < 208.0) | ((val < 222.0) & (sat > 18.0))
    if person_rgb is not None and person_rgb.shape[:2] == ai_rgb.shape[:2]:
        diff = np.max(np.abs(ai_rgb.astype(np.float32) - person_rgb.astype(np.float32)), axis=2)
        changed = diff > 18.0
    else:
        changed = np.ones((h, w), dtype=bool)

    candidate = np.zeros((h, w), dtype=bool)
    candidate[fill_y0:fill_y1, body_x0:body_x1] = True
    candidate &= darkness
    candidate &= changed
    candidate &= alpha < 0.22
    if candidate.any():
        candidate = cv2.morphologyEx(
            candidate.astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((5, 9), dtype=np.uint8),
            iterations=1,
        ).astype(bool)
        candidate = cv2.morphologyEx(
            candidate.astype(np.uint8),
            cv2.MORPH_OPEN,
            np.ones((3, 5), dtype=np.uint8),
            iterations=1,
        ).astype(bool)
        row_filled = np.zeros_like(candidate, dtype=bool)
        center_x = (wx0 + wx1) // 2
        for yy_idx in range(fill_y0, fill_y1):
            xs = np.where(candidate[yy_idx, body_x0:body_x1])[0]
            if xs.size < 8:
                continue
            xs = xs + body_x0
            splits = np.where(np.diff(xs) > 1)[0]
            starts = np.r_[0, splits + 1]
            ends = np.r_[splits, xs.size - 1]
            best = None
            best_score = None
            for s_idx, e_idx in zip(starts, ends):
                seg_x0 = int(xs[s_idx])
                seg_x1 = int(xs[e_idx]) + 1
                seg_w = seg_x1 - seg_x0
                seg_c = (seg_x0 + seg_x1) * 0.5
                score = abs(seg_c - center_x) - seg_w * 0.18
                if best is None or score < best_score:
                    best = (seg_x0, seg_x1)
                    best_score = score
            if best is not None:
                seg_x0, seg_x1 = best
                row_filled[yy_idx, seg_x0:seg_x1] = True
        candidate = row_filled
        if candidate.any():
            candidate = cv2.GaussianBlur(candidate.astype(np.float32), (5, 5), 0) > 0.16

    if not candidate.any():
        return (
            rgb,
            alpha,
            {
                "applied": False,
                "reason": "no_candidate",
                "fill_y0": int(fill_y0),
                "fill_y1": int(fill_y1),
            },
        )

    src_y0 = _clamp_int(leg_top, 0, h - 1)
    src_y1 = _clamp_int(src_y0 + max(14, int(h * 0.018)), src_y0 + 1, h)
    texture_support = alpha[src_y0:src_y1, body_x0:body_x1] > 0.35
    if not texture_support.any():
        return rgb, alpha, {"applied": False, "reason": "no_texture_source"}

    texture_patch = rgb[src_y0:src_y1, body_x0:body_x1, :].copy()
    if texture_patch.size == 0:
        return rgb, alpha, {"applied": False, "reason": "empty_texture_patch"}

    fill_h = fill_y1 - fill_y0
    fill_w = body_x1 - body_x0
    texture_patch = np.asarray(
        Image.fromarray(np.clip(texture_patch, 0, 255).astype(np.uint8), mode="RGB").resize(
            (fill_w, fill_h), Image.Resampling.BILINEAR
        ),
        dtype=np.float32,
    )
    ai_crop = ai_rgb[fill_y0:fill_y1, body_x0:body_x1, :].astype(np.float32)
    ai_gray = cv2.cvtColor(np.clip(ai_crop, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(
        np.float32
    )
    tex_gray = cv2.cvtColor(
        np.clip(texture_patch, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY
    ).astype(np.float32)
    luminance_ratio = np.clip((ai_gray + 10.0) / np.maximum(tex_gray + 10.0, 1.0), 0.72, 1.24)
    shaded_patch = np.clip(texture_patch * luminance_ratio[:, :, None], 0.0, 255.0)

    candidate_crop = candidate[fill_y0:fill_y1, body_x0:body_x1].astype(np.float32)
    blur_mask = cv2.GaussianBlur(candidate_crop, (9, 9), 0)
    vertical = np.linspace(0.48, 0.96, fill_h, dtype=np.float32)[:, None]
    bridge_alpha = np.clip(blur_mask * vertical, 0.0, 0.96)
    bridge_alpha = np.where(
        candidate_crop > 0, np.maximum(bridge_alpha, 0.52 * vertical), bridge_alpha
    )

    existing = rgb[fill_y0:fill_y1, body_x0:body_x1, :]
    rgb[fill_y0:fill_y1, body_x0:body_x1, :] = (
        existing * (1.0 - bridge_alpha[:, :, None]) + shaded_patch * bridge_alpha[:, :, None]
    )
    alpha[fill_y0:fill_y1, body_x0:body_x1] = np.maximum(
        alpha[fill_y0:fill_y1, body_x0:body_x1],
        bridge_alpha,
    )

    return (
        rgb,
        alpha,
        {
            "applied": True,
            "fill_y0": int(fill_y0),
            "fill_y1": int(fill_y1),
            "body_x0": int(body_x0),
            "body_x1": int(body_x1),
            "candidate_ratio": round(float(candidate.mean()), 4),
            "source_y0": int(src_y0),
            "source_y1": int(src_y1),
        },
    )


def _fill_structured_lower_upper_from_shape_mask(
    shaded_layer_np: np.ndarray,
    shaded_alpha: np.ndarray,
    shape_mask: np.ndarray,
    ai_rgb: np.ndarray,
    *,
    warp_meta: WarpMetadata | None = None,
    structured_pattern_lower: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Fill missing upper-waist texture only inside the extracted CatVTON shape mask."""
    rgb = shaded_layer_np[:, :, :3].astype(np.float32).copy()
    alpha = np.clip(shaded_alpha.astype(np.float32), 0.0, 1.0).copy()
    if not structured_pattern_lower or warp_meta is None:
        return rgb, alpha, {"applied": False, "reason": "not_structured"}

    mask = np.clip(shape_mask.astype(np.float32), 0.0, 1.0)
    mask_bool = mask > 0.08
    if not mask_bool.any():
        return rgb, alpha, {"applied": False, "reason": "empty_shape_mask"}

    h, w = alpha.shape[:2]
    ys, xs = np.where(mask_bool)
    fill_y0, fill_y1 = int(ys.min()), int(ys.max() + 1)
    fill_x0, fill_x1 = int(xs.min()), int(xs.max() + 1)

    leg_top = min(warp_meta.left_leg_box[1], warp_meta.right_leg_box[1])
    src_y0 = _clamp_int(leg_top, 0, h - 1)
    src_y1 = _clamp_int(src_y0 + max(18, int(h * 0.024)), src_y0 + 1, h)
    body_x0 = _clamp_int(min(warp_meta.left_leg_box[0], fill_x0), 0, w - 1)
    body_x1 = _clamp_int(max(warp_meta.right_leg_box[2], fill_x1), body_x0 + 1, w)

    src_alpha = alpha[src_y0:src_y1, body_x0:body_x1]
    src_mask = src_alpha > 0.28
    if not src_mask.any():
        return rgb, alpha, {"applied": False, "reason": "no_texture_source"}

    source_rows = np.where((src_mask.sum(axis=1) >= 8))[0]
    if source_rows.size == 0:
        return rgb, alpha, {"applied": False, "reason": "no_dense_source_rows"}

    target_rgb = rgb.copy()
    target_alpha = alpha.copy()
    ai_gray_full = cv2.cvtColor(
        np.clip(ai_rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY
    ).astype(np.float32)
    center_x = 0.5 * float(warp_meta.left_leg_box[2] + warp_meta.right_leg_box[0])

    fill_rows = 0
    fill_pixels = 0
    left_pixels = 0
    right_pixels = 0
    center_pixels = 0
    existing_mean_acc = 0.0
    src_progress_max = float(max(1, source_rows.size - 1))
    target_progress_max = float(max(1, fill_y1 - fill_y0 - 1))

    for yy in range(fill_y0, fill_y1):
        row_mask = mask[yy, :] > 0.08
        row_xs = np.where(row_mask)[0]
        if row_xs.size < 6:
            continue

        row_progress = float(yy - fill_y0) / target_progress_max
        source_row_idx = int(round(row_progress * src_progress_max))
        source_row_idx = int(source_rows[_clamp_int(source_row_idx, 0, source_rows.size - 1)])
        source_row_mask = src_mask[source_row_idx]
        source_xs = np.where(source_row_mask)[0] + body_x0
        if source_xs.size < 8:
            continue

        src_left = source_xs[source_xs < center_x]
        src_right = source_xs[source_xs >= center_x]
        target_left = row_xs[row_xs < center_x]
        target_right = row_xs[row_xs >= center_x]
        if target_left.size == 0 and target_right.size == 0:
            continue

        row_fill = np.zeros((w, 3), dtype=np.float32)
        row_written = np.zeros(w, dtype=bool)

        if target_left.size and src_left.size >= 4:
            mapped_left = np.interp(
                np.linspace(0.0, 1.0, target_left.size, dtype=np.float32),
                np.linspace(0.0, 1.0, src_left.size, dtype=np.float32),
                src_left.astype(np.float32),
            )
            mapped_left = np.clip(np.rint(mapped_left).astype(np.int32), 0, w - 1)
            row_fill[target_left, :] = rgb[source_row_idx + src_y0, mapped_left, :]
            row_written[target_left] = True
            left_pixels += int(target_left.size)

        if target_right.size and src_right.size >= 4:
            mapped_right = np.interp(
                np.linspace(0.0, 1.0, target_right.size, dtype=np.float32),
                np.linspace(0.0, 1.0, src_right.size, dtype=np.float32),
                src_right.astype(np.float32),
            )
            mapped_right = np.clip(np.rint(mapped_right).astype(np.int32), 0, w - 1)
            row_fill[target_right, :] = rgb[source_row_idx + src_y0, mapped_right, :]
            row_written[target_right] = True
            right_pixels += int(target_right.size)

        if not row_written[row_xs].all():
            if source_xs.size < 4:
                continue
            missing_x = row_xs[~row_written[row_xs]]
            mapped_all = np.interp(
                np.linspace(0.0, 1.0, missing_x.size, dtype=np.float32),
                np.linspace(0.0, 1.0, source_xs.size, dtype=np.float32),
                source_xs.astype(np.float32),
            )
            mapped_all = np.clip(np.rint(mapped_all).astype(np.int32), 0, w - 1)
            row_fill[missing_x, :] = rgb[source_row_idx + src_y0, mapped_all, :]
            row_written[missing_x] = True
            center_pixels += int(missing_x.size)

        if not row_written[row_xs].any():
            continue

        row_gray = cv2.cvtColor(
            np.clip(row_fill[row_xs, :], 0, 255).astype(np.uint8)[None, :, :],
            cv2.COLOR_RGB2GRAY,
        ).astype(np.float32)[0]
        ai_gray_row = ai_gray_full[yy, row_xs]
        luminance_ratio = np.clip(
            (ai_gray_row + 10.0) / np.maximum(row_gray + 10.0, 1.0), 0.84, 1.12
        )
        row_fill[row_xs, :] = np.clip(row_fill[row_xs, :] * luminance_ratio[:, None], 0.0, 255.0)

        local_mask = mask[yy, row_xs]
        vertical_strength = 0.26 + 0.46 * row_progress
        row_alpha = np.clip(local_mask * vertical_strength, 0.0, 0.78)
        row_alpha = np.where(
            local_mask > 0.34, np.maximum(row_alpha, 0.18 + 0.32 * row_progress), row_alpha
        )
        row_alpha = np.where(alpha[yy, row_xs] > 0.18, np.minimum(row_alpha, 0.42), row_alpha)

        existing = target_rgb[yy, row_xs, :]
        target_rgb[yy, row_xs, :] = (
            existing * (1.0 - row_alpha[:, None]) + row_fill[row_xs, :] * row_alpha[:, None]
        )
        target_alpha[yy, row_xs] = np.maximum(target_alpha[yy, row_xs], row_alpha)
        fill_rows += 1
        fill_pixels += int(row_xs.size)
        existing_mean_acc += float(existing.mean()) if existing.size else 0.0

    if fill_pixels == 0:
        return rgb, alpha, {"applied": False, "reason": "no_rows_filled"}

    soft_mask = cv2.GaussianBlur(mask.astype(np.float32), (5, 5), 0)
    blend_region = soft_mask > 0.10
    target_rgb[blend_region, :] = target_rgb[blend_region, :] * soft_mask[blend_region, None] + rgb[
        blend_region, :
    ] * (1.0 - soft_mask[blend_region, None])
    target_alpha = np.where(
        blend_region,
        np.maximum(alpha, np.maximum(target_alpha * soft_mask, target_alpha * 0.78)),
        target_alpha,
    )

    rgb = target_rgb
    alpha = target_alpha
    return (
        rgb,
        alpha,
        {
            "applied": True,
            "mode": "rowwise_shape_projection",
            "fill_bbox": [fill_x0, fill_y0, fill_x1, fill_y1],
            "source_bbox": [body_x0, src_y0, body_x1, src_y1],
            "shape_ratio": round(float(mask_bool.mean()), 4),
            "filled_rows": int(fill_rows),
            "filled_pixels": int(fill_pixels),
            "left_pixels": int(left_pixels),
            "right_pixels": int(right_pixels),
            "center_pixels": int(center_pixels),
            "source_rows": int(source_rows.size),
        },
    )


def _apply_lower_luminance_shading(
    layer_np: np.ndarray,
    ai_rgb: np.ndarray,
    blend_mask: np.ndarray,
    *,
    shading_strength: float = 1.0,
) -> tuple[np.ndarray, dict]:
    """Remodulate warped garment texture with CatVTON luminance and wrinkle detail."""
    if layer_np.ndim != 3 or layer_np.shape[2] < 4:
        return layer_np, {"reason": "missing_rgba"}

    h, w = layer_np.shape[:2]
    if ai_rgb.shape[:2] != (h, w):
        ai_rgb = np.asarray(
            Image.fromarray(ai_rgb.astype(np.uint8), mode="RGB").resize(
                (w, h), Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )

    layer_rgb = layer_np[:, :, :3].astype(np.float32)
    alpha = np.clip(layer_np[:, :, 3].astype(np.float32) / 255.0, 0.0, 1.0)
    mask = np.clip(blend_mask.astype(np.float32), 0.0, 1.0) * (alpha > 0.02).astype(np.float32)
    if mask.max() < 0.01:
        return layer_np, {"reason": "mask_too_small"}

    ai_gray = cv2.cvtColor(ai_rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    layer_gray = cv2.cvtColor(layer_rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    kernel = max(15, int(min(w, h) * 0.06))
    if kernel % 2 == 0:
        kernel += 1
    ai_low = cv2.GaussianBlur(ai_gray, (kernel, kernel), 0)
    layer_low = cv2.GaussianBlur(layer_gray, (kernel, kernel), 0)
    luminance_ratio = np.clip((ai_low + 8.0) / np.maximum(layer_low + 8.0, 1.0), 0.72, 1.38)

    ai_detail = ai_gray - ai_low
    detail_gain = np.clip(ai_detail / 255.0, -0.11, 0.11)
    shading_raw = np.clip(
        np.power(luminance_ratio, 0.95) * (1.0 + detail_gain * 0.65),
        0.68,
        1.42,
    )
    shade_strength = float(np.clip(shading_strength, 0.0, 1.0))
    shading = 1.0 + (shading_raw - 1.0) * shade_strength

    shaded_rgb = np.clip(layer_rgb * shading[:, :, None], 0.0, 255.0)
    mixed_rgb = layer_rgb * (1.0 - mask[:, :, None]) + shaded_rgb * mask[:, :, None]

    out = layer_np.copy()
    out[:, :, :3] = np.clip(mixed_rgb, 0.0, 255.0).astype(np.uint8)
    return out, {
        "kernel": kernel,
        "mask_coverage": round(float((mask > 0.08).mean()), 4),
        "luminance_ratio_mean": round(float(luminance_ratio[mask > 0.08].mean()), 4),
        "detail_gain_mean": round(float(detail_gain[mask > 0.08].mean()), 4),
        "shading_strength": round(float(shade_strength), 4),
    }


def _raw_mask_bbox(
    mask_image: Image.Image | None,
    size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    """Return a resized lower-garment mask bbox, if one is available."""
    if mask_image is None:
        return None
    w, h = size
    mask = np.asarray(mask_image.convert("L").resize((w, h), Image.Resampling.NEAREST))
    ys, xs = np.where(mask > 20)
    if xs.size < 128 or ys.size < 128:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def _denim_extension_from_mask(
    *,
    mask_bbox: tuple[int, int, int, int] | None,
    waist_box: tuple[int, int, int, int],
    left_leg_box: tuple[int, int, int, int],
    image_h: int,
) -> tuple[float, float, dict]:
    """Adapt denim top/bottom extension to the current person's lower mask."""
    if mask_bbox is None:
        return 0.045, 0.03, {"source": "fallback"}

    _mx0, my0, _mx1, my1 = mask_bbox
    waist_y0 = int(waist_box[1])
    leg_y1 = int(left_leg_box[3])
    top_px = int(np.clip(waist_y0 - my0 + image_h * 0.010, 0, image_h * 0.060))
    bottom_px = int(np.clip(my1 - leg_y1 + image_h * 0.006, 0, image_h * 0.040))
    return (
        top_px / float(max(1, image_h)),
        bottom_px / float(max(1, image_h)),
        {
            "source": "raw_mask",
            "mask_bbox": list(mask_bbox),
            "top_extend_px": int(top_px),
            "bottom_extend_px": int(bottom_px),
        },
    )


def _normalize_lower_layer_to_source_color(
    layer_np: np.ndarray,
    original_garment: Image.Image,
    blend_mask: np.ndarray,
    *,
    strength: float = 0.72,
) -> tuple[np.ndarray, dict]:
    """Reduce large low-frequency brightness/color drift while keeping denim texture."""
    try:
        if layer_np.ndim != 3 or layer_np.shape[2] < 4:
            return layer_np, {"reason": "missing_rgba"}
        cutout = cutout_garment_rgba(original_garment.convert("RGB")).cropped.convert("RGBA")
        src = np.asarray(cutout, dtype=np.uint8)
        src_alpha = src[:, :, 3] > 30
        if int(src_alpha.sum()) < 128:
            return layer_np, {"reason": "source_alpha_too_small"}

        h, w = layer_np.shape[:2]
        mask = (np.clip(blend_mask.astype(np.float32), 0.0, 1.0) > 0.08) & (layer_np[:, :, 3] > 20)
        if int(mask.sum()) < 128:
            return layer_np, {"reason": "mask_too_small"}

        src_rgb = src[:, :, :3][src_alpha]
        src_lab = cv2.cvtColor(src_rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3)
        source_l = float(np.median(src_lab[:, 0].astype(np.float32)))
        source_ab = np.median(src_lab[:, 1:3].astype(np.float32), axis=0)

        rgb = np.clip(layer_np[:, :, :3], 0, 255).astype(np.uint8)
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        kernel = max(31, int(min(w, h) * 0.085))
        if kernel % 2 == 0:
            kernel += 1
        low_l = cv2.GaussianBlur(lab[:, :, 0], (kernel, kernel), 0)
        detail_l = np.clip(lab[:, :, 0] - low_l, -34.0, 34.0)
        target_l = np.clip(source_l + detail_l * 0.72, 0.0, 255.0)
        s = float(np.clip(strength, 0.0, 1.0))

        normalized = lab.copy()
        normalized[mask, 0] = lab[mask, 0] * (1.0 - s) + target_l[mask] * s
        normalized[mask, 1] = lab[mask, 1] * (1.0 - s * 0.62) + source_ab[0] * (s * 0.62)
        normalized[mask, 2] = lab[mask, 2] * (1.0 - s * 0.62) + source_ab[1] * (s * 0.62)
        out_rgb = cv2.cvtColor(
            np.clip(normalized, 0, 255).astype(np.uint8),
            cv2.COLOR_LAB2RGB,
        )
        out = layer_np.copy()
        out[:, :, :3] = out_rgb
        return out, {
            "source_lab_median": [
                round(float(source_l), 3),
                round(float(source_ab[0]), 3),
                round(float(source_ab[1]), 3),
            ],
            "strength": round(float(s), 4),
            "kernel": int(kernel),
        }
    except Exception as e:
        return layer_np, {"reason": str(e)}


def _estimate_pants_flare_ratio(cropped_rgba: Image.Image) -> tuple[float, bool]:
    """Estimate whether a pants product is straight or wide-leg/flared."""
    alpha = np.asarray(cropped_rgba.convert("RGBA"))[:, :, 3]
    if int((alpha > 20).sum()) < 64:
        return 1.0, False

    h = alpha.shape[0]
    upper_w = _alpha_band_width(alpha, int(h * 0.18))
    mid_w = _alpha_band_width(alpha, int(h * 0.52))
    hem_w = _alpha_band_width(alpha, int(h * 0.90))
    ref_w = max(upper_w, mid_w, 1)
    flare_ratio = float(np.clip(hem_w / float(ref_w), 0.92, 1.65))
    wide_leg = hem_w >= max(int(ref_w * 1.08), ref_w + 10) and flare_ratio >= 1.12
    return flare_ratio, wide_leg


def _expand_pants_target_boxes(
    waistband_box: tuple[int, int, int, int],
    left_leg_box: tuple[int, int, int, int],
    right_leg_box: tuple[int, int, int, int],
    *,
    image_w: int,
    flare_ratio: float,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Widen pants warp boxes so real garment texture reaches the outer sides."""
    body_x0 = min(left_leg_box[0], waistband_box[0])
    body_x1 = max(right_leg_box[2], waistband_box[2])
    body_w = max(2, body_x1 - body_x0)

    flare_boost = max(0.0, float(flare_ratio) - 1.0)
    outer_scale = 0.04 + min(0.05, flare_boost * 0.09)
    inner_scale = 0.012 + min(0.015, flare_boost * 0.02)

    outer_pad = max(4, int(body_w * outer_scale), int(image_w * 0.012))
    inner_pad = max(2, int(body_w * inner_scale))
    waist_outer_pad = max(inner_pad, int(outer_pad * 0.55))

    wx0, wy0, wx1, wy1 = waistband_box
    lx0, ly0, lx1, ly1 = left_leg_box
    rx0, ry0, rx1, ry1 = right_leg_box

    waistband_box = (
        max(0, wx0 - waist_outer_pad),
        wy0,
        min(image_w, wx1 + waist_outer_pad),
        wy1,
    )
    left_leg_box = (
        max(0, lx0 - outer_pad),
        ly0,
        min(image_w, lx1 + inner_pad),
        ly1,
    )
    right_leg_box = (
        max(0, rx0 - inner_pad),
        ry0,
        min(image_w, rx1 + outer_pad),
        ry1,
    )
    return waistband_box, left_leg_box, right_leg_box


def _alpha_bbox(
    alpha: np.ndarray,
    *,
    threshold: int = 12,
) -> tuple[int, int, int, int] | None:
    """Return the visible alpha bbox as (x0, y0, x1, y1)."""
    ys, xs = np.where(alpha > threshold)
    if xs.size == 0 or ys.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _fill_mask_holes(mask_bool: np.ndarray) -> np.ndarray:
    """Fill enclosed holes inside a binary mask."""
    if mask_bool.size == 0:
        return mask_bool
    mask_u8 = mask_bool.astype(np.uint8) * 255
    flood = mask_u8.copy()
    h, w = flood.shape[:2]
    flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flood)
    filled = cv2.bitwise_or(mask_u8, holes)
    return filled > 0


def _keep_largest_mask_component(mask_bool: np.ndarray) -> np.ndarray:
    """Keep only the largest connected component of a boolean mask."""
    if not mask_bool.any():
        return mask_bool

    labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask_bool.astype(np.uint8),
        8,
    )
    if labels_count <= 2:
        return mask_bool

    largest_label = 1
    largest_area = int(stats[1, cv2.CC_STAT_AREA])
    for label_idx in range(2, labels_count):
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if area > largest_area:
            largest_area = area
            largest_label = label_idx
    return labels == largest_label


def _keep_significant_mask_components(
    mask_bool: np.ndarray,
    *,
    min_area_ratio: float = 0.18,
    max_components: int = 3,
) -> np.ndarray:
    """Keep the main components of a mask.

    Pants commonly have two disconnected leg components. Keeping only the
    single largest component drops one leg from the fidelity pass.
    """
    if not mask_bool.any():
        return mask_bool

    labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask_bool.astype(np.uint8),
        8,
    )
    if labels_count <= 2:
        return mask_bool

    areas = stats[1:, cv2.CC_STAT_AREA]
    max_area = int(areas.max()) if areas.size else 0
    if max_area <= 0:
        return mask_bool

    min_area = max(16, int(max_area * float(min_area_ratio)))
    component_labels = [
        idx + 1
        for idx, area in sorted(
            enumerate(areas),
            key=lambda item: int(item[1]),
            reverse=True,
        )
        if int(area) >= min_area
    ][: max(1, int(max_components))]
    if not component_labels:
        return mask_bool

    keep = np.zeros_like(mask_bool, dtype=bool)
    for label_idx in component_labels:
        keep |= labels == label_idx
    return keep


def _keep_significant_alpha_components(
    rgba: Image.Image,
    *,
    alpha_threshold: int = 10,
    min_area_ratio: float = 0.18,
    max_components: int = 3,
) -> Image.Image:
    """Remove tiny alpha islands while preserving multi-part garments."""
    rgba_np = np.array(rgba.convert("RGBA"), dtype=np.uint8)
    alpha = rgba_np[:, :, 3]
    keep = _keep_significant_mask_components(
        alpha > alpha_threshold,
        min_area_ratio=min_area_ratio,
        max_components=max_components,
    )
    if keep.shape != alpha.shape or not keep.any():
        return rgba
    rgba_np[~keep, 3] = 0
    return Image.fromarray(rgba_np, mode="RGBA")


def _mask_row_bounds(mask_bool: np.ndarray, y: int) -> tuple[int, int] | None:
    """Return [x0, x1) bounds for one row of a boolean mask."""
    if y < 0 or y >= mask_bool.shape[0]:
        return None
    xs = np.where(mask_bool[y])[0]
    if xs.size == 0:
        return None
    return int(xs[0]), int(xs[-1]) + 1


def _keep_largest_alpha_component(
    rgba: Image.Image,
    *,
    alpha_threshold: int = 10,
) -> Image.Image:
    """Remove isolated tiny alpha islands while keeping the main garment body."""
    rgba_np = np.asarray(rgba.convert("RGBA"), dtype=np.uint8)
    alpha = rgba_np[:, :, 3]
    mask = alpha > alpha_threshold
    if not mask.any():
        return rgba

    labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8),
        8,
    )
    if labels_count <= 2:
        return rgba

    largest_label = 1
    largest_area = int(stats[1, cv2.CC_STAT_AREA])
    for label_idx in range(2, labels_count):
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if area > largest_area:
            largest_area = area
            largest_label = label_idx

    keep = labels == largest_label
    rgba_np[~keep, 3] = 0
    return Image.fromarray(rgba_np, mode="RGBA")


def _detect_pattern_strength(img: Image.Image) -> float:
    """
    Detect whether a garment image contains high-contrast patterns (checkered, striped, etc.)

    that would be destroyed by aggressive brightness transfer.

    Returns a score [0, 1]:
      - 0.0 ~ 0.35: solid or low-contrast fabric → apply brightness transfer (gentle)
      - 0.35 ~ 0.50: moderate pattern → careful transfer (reduced blend)
      - 0.50 ~ 1.00: high-contrast pattern (checkered, bold stripes, plaid) → skip all effects

    Method: Compare gradient energy at multiple scales to distinguish sharp patterns from noise.
    High local variance in small neighborhoods with many edge pixels → pattern.
    """
    return detect_pattern_strength(img)

    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    if h < 16 or w < 16:
        return 0.0

    gray = arr.mean(axis=2)

    # Multi-scale gradient energy: captures patterns at different scales
    scores = []

    # Small scale (4px): fine checkered / thin stripes
    gy, gx = np.gradient(gray.astype(np.float32))
    grad = np.sqrt(gx**2 + gy**2)
    grad_nonzero = grad[grad > 0]
    if grad_nonzero.size == 0:
        return 0.0  # Solid color image — no pattern
    threshold = np.percentile(grad_nonzero, 75)
    edge_density_small = float((grad > threshold).mean())
    scores.append(edge_density_small)

    # Medium scale (8px): medium patterns
    local_mean = np.array(
        Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.BoxBlur(radius=4))
    )
    local_var = (gray - local_mean) ** 2
    var_score = float(np.percentile(local_var, 95) / max(1, gray.var()))
    scores.append(min(1.0, var_score))

    # Check color variance per channel (high per-channel variance = colorful pattern)
    channel_ranges = []
    for c in range(3):
        ch = arr[:, :, c]
        ch_range = float(ch.max() - ch.min()) / 255.0
        channel_ranges.append(ch_range)
    color_variance = np.std(channel_ranges)
    scores.append(min(1.0, color_variance * 1.5))

    # Combined score: weighted average
    combined = 0.5 * scores[0] + 0.3 * scores[1] + 0.2 * scores[2]

    return float(np.clip(combined, 0.0, 1.0))


def _suppress_light_fidelity_artifact_candidates(
    motif_candidate: np.ndarray,
    layer_rgb: np.ndarray,
    motif_source: np.ndarray,
    *,
    gar_x0: int,
    gar_y0: int,
    gar_x1: int,
    gar_y1: int,
    body_cx: int,
    light_pattern_base: bool,
) -> tuple[np.ndarray, float]:
    """Drop blocky off-center white artifacts while keeping central print detail."""
    if not light_pattern_base or not motif_candidate.any():
        return motif_candidate, 0.0

    h, w = motif_candidate.shape
    garment_w = max(1, gar_x1 - gar_x0)
    garment_h = max(1, gar_y1 - gar_y0)
    hsv = cv2.cvtColor(layer_rgb.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    pale_candidate = motif_candidate & motif_source & (val > 212.0) & (sat < 58.0)
    if not pale_candidate.any():
        return motif_candidate, 0.0

    grid_y, grid_x = np.indices((h, w))
    central_print_band = (
        (np.abs(grid_x - float(body_cx)) <= garment_w * 0.28)
        & (grid_y >= gar_y0 + garment_h * 0.18)
        & (grid_y <= gar_y0 + garment_h * 0.86)
    )
    shoulder_or_edge_band = (grid_y < gar_y0 + garment_h * 0.30) | (
        np.abs(grid_x - float(body_cx)) > garment_w * 0.34
    )

    labels_count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        pale_candidate.astype(np.uint8),
        8,
    )
    remove_mask = np.zeros_like(motif_candidate, dtype=bool)
    min_block_area = max(18, int(garment_w * garment_h * 0.00035))
    for label_idx in range(1, labels_count):
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if area < min_block_area:
            continue
        bbox_w = int(stats[label_idx, cv2.CC_STAT_WIDTH])
        bbox_h = int(stats[label_idx, cv2.CC_STAT_HEIGHT])
        bbox_area = max(1, bbox_w * bbox_h)
        fill_ratio = area / float(bbox_area)
        component = labels == label_idx
        central_overlap = float((component & central_print_band).sum()) / float(area)
        edge_overlap = float((component & shoulder_or_edge_band).sum()) / float(area)
        cx, cy = centroids[label_idx]
        side_upper_artifact = (
            cy < gar_y0 + garment_h * 0.32 and abs(cx - float(body_cx)) > garment_w * 0.18
        )
        near_garment_edge = (
            cx < gar_x0 + garment_w * 0.18
            or cx > gar_x1 - garment_w * 0.18
            or cy < gar_y0 + garment_h * 0.20
            or cy > gar_y1 - garment_h * 0.08
        )
        blocky = fill_ratio >= 0.34 and max(bbox_w, bbox_h) >= 5
        if (
            central_overlap < 0.22
            and blocky
            and (edge_overlap > 0.45 or near_garment_edge or side_upper_artifact)
        ) or (side_upper_artifact and blocky and central_overlap < 0.45):
            remove_mask |= component

    if not remove_mask.any():
        return motif_candidate, 0.0

    filtered = motif_candidate & ~remove_mask
    removed_ratio = float(remove_mask.sum()) / float(max(1, motif_source.sum()))
    return filtered, removed_ratio


def _repair_light_garment_block_artifacts(
    result_np: np.ndarray,
    garment_mask: np.ndarray,
    motif_gate: np.ndarray,
    *,
    gar_x0: int,
    gar_y0: int,
    gar_x1: int,
    gar_y1: int,
    body_cx: int,
    light_pattern_base: bool,
) -> tuple[np.ndarray, float]:
    """Blend shoulder/edge pale blocks back into the local fabric tone."""
    if not light_pattern_base or not garment_mask.any():
        return result_np, 0.0

    h, w = garment_mask.shape
    garment_w = max(1, gar_x1 - gar_x0)
    garment_h = max(1, gar_y1 - gar_y0)
    grid_y, grid_x = np.indices((h, w))
    central_print_band = (
        (np.abs(grid_x - float(body_cx)) <= garment_w * 0.26)
        & (grid_y >= gar_y0 + garment_h * 0.18)
        & (grid_y <= gar_y0 + garment_h * 0.86)
    )
    artifact_zone = (
        (grid_y < gar_y0 + garment_h * 0.34)
        | (np.abs(grid_x - float(body_cx)) > garment_w * 0.31)
        | (grid_y > gar_y1 - garment_h * 0.12)
    )

    hsv = cv2.cvtColor(result_np.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    fabric_reference = garment_mask & ~central_print_band & (motif_gate < 0.12)
    ref_vals = val[fabric_reference]
    if ref_vals.size < 32:
        return result_np, 0.0

    median_val = float(np.median(ref_vals))
    fabric_refined = fabric_reference & (val <= float(np.percentile(ref_vals, 58)))
    ref_rgb = result_np[fabric_refined if fabric_refined.sum() >= 32 else fabric_reference]
    if ref_rgb.size == 0:
        return result_np, 0.0
    fabric_rgb = np.median(ref_rgb.reshape(-1, 3), axis=0).astype(np.float32)
    candidate = (
        garment_mask
        & artifact_zone
        & ~central_print_band
        & (sat < 48.0)
        & (val > max(206.0, median_val + 18.0))
    )
    candidate = cv2.morphologyEx(
        candidate.astype(np.uint8),
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
    ).astype(bool)
    if not candidate.any():
        return result_np, 0.0

    labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        candidate.astype(np.uint8),
        8,
    )
    repair_mask = np.zeros_like(candidate, dtype=bool)
    min_area = max(18, int(garment_w * garment_h * 0.00035))
    for label_idx in range(1, labels_count):
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        bbox_w = int(stats[label_idx, cv2.CC_STAT_WIDTH])
        bbox_h = int(stats[label_idx, cv2.CC_STAT_HEIGHT])
        fill_ratio = area / float(max(1, bbox_w * bbox_h))
        if fill_ratio >= 0.22 and max(bbox_w, bbox_h) >= 5:
            repair_mask |= labels == label_idx

    if not repair_mask.any():
        return result_np, 0.0

    soft = cv2.GaussianBlur(repair_mask.astype(np.float32), (9, 9), 0)
    soft = np.clip(soft * 0.96, 0.0, 0.96)[:, :, np.newaxis]
    local_blur = cv2.GaussianBlur(result_np.astype(np.float32), (0, 0), 4.0)
    repair_rgb = np.clip(fabric_rgb * 0.88 + local_blur * 0.12, 0, 255)
    repaired = result_np.astype(np.float32).copy()
    repaired[:, :, :3] = repair_rgb * soft + repaired[:, :, :3] * (1.0 - soft)
    repaired = np.clip(repaired, 0, 255).astype(np.float32)
    repaired_ratio = float(repair_mask.sum()) / float(max(1, garment_mask.sum()))
    return repaired, repaired_ratio


def _build_lower_fidelity_clip_mask(
    catvton_mask_np: np.ndarray | None,
    changed_garment: np.ndarray,
    garment_layer_present: np.ndarray,
    protected_by_mask: np.ndarray,
    *,
    layer_alpha: np.ndarray | None = None,
    left_leg_box: tuple[int, int, int, int] | None = None,
    right_leg_box: tuple[int, int, int, int] | None = None,
) -> np.ndarray | None:
    """Build a lower-body clip from real warp coverage plus a modest shape guide.

    For lower garments we want more than the narrow raw CatVTON mask, otherwise
    outer-leg plaid never has a chance to land. But using the full widened warp
    silhouette as the repaint clip makes side ghost panels show up. So the clip
    follows the real warp coverage while still being constrained by a moderately
    expanded lower-body shape guide derived from the CatVTON mask / changed area.
    """
    clip_bool = garment_layer_present & ~protected_by_mask
    if not clip_bool.any():
        return catvton_mask_np

    if catvton_mask_np is not None:
        mask_core = _keep_largest_mask_component(catvton_mask_np > 0.08)
        if mask_core.any():
            if layer_alpha is not None and left_leg_box is not None and right_leg_box is not None:
                upper_guide = cv2.dilate(
                    mask_core.astype(np.uint8),
                    np.ones((5, 9), dtype=np.uint8),
                    iterations=1,
                ).astype(bool)
                upper_guide = _keep_largest_mask_component(upper_guide)

                lower_core = ((layer_alpha > 0.32) & clip_bool).astype(bool)
                if not lower_core.any():
                    lower_core = clip_bool.copy()
                lower_core = cv2.morphologyEx(
                    lower_core.astype(np.uint8),
                    cv2.MORPH_CLOSE,
                    np.ones((5, 5), dtype=np.uint8),
                ).astype(bool)
                lower_core = _keep_significant_mask_components(
                    lower_core,
                    min_area_ratio=0.14,
                    max_components=3,
                )

                h, _w = mask_core.shape
                leg_top = max(0, min(left_leg_box[1], right_leg_box[1]))
                leg_bottom = min(h, max(left_leg_box[3], right_leg_box[3]))
                split_y0 = max(0, min(leg_top, h - 1))
                split_y1 = min(h, split_y0 + max(24, int(max(1, leg_bottom - split_y0) * 0.22)))
                shape_guide = np.zeros_like(mask_core, dtype=bool)
                if split_y0 > 0:
                    shape_guide[:split_y0] = upper_guide[:split_y0]
                if split_y1 < h:
                    shape_guide[split_y1:] = lower_core[split_y1:]

                for y in range(split_y0, split_y1):
                    upper_bounds = _mask_row_bounds(upper_guide, y)
                    lower_bounds = _mask_row_bounds(lower_core, y)
                    if upper_bounds is None and lower_bounds is None:
                        continue
                    if upper_bounds is None:
                        upper_bounds = lower_bounds
                    if lower_bounds is None:
                        lower_bounds = upper_bounds
                    if upper_bounds is None or lower_bounds is None:
                        continue
                    denom = max(1, split_y1 - split_y0)
                    t = float(y - split_y0) / float(denom)
                    x0 = int(round(upper_bounds[0] * (1.0 - t) + lower_bounds[0] * t))
                    x1 = int(round(upper_bounds[1] * (1.0 - t) + lower_bounds[1] * t))
                    if x1 > x0:
                        shape_guide[y, x0:x1] = True
            else:
                shape_guide = cv2.dilate(
                    mask_core.astype(np.uint8),
                    np.ones((7, 21), dtype=np.uint8),
                    iterations=1,
                ).astype(bool)
            guided_clip = clip_bool & shape_guide
            if guided_clip.any():
                clip_bool = guided_clip

            retained_ratio = float(clip_bool.sum()) / float(
                max(1, (garment_layer_present & ~protected_by_mask).sum())
            )
            if retained_ratio < 0.55:
                logger.info(
                    "lower fidelity clip retained only %.3f of warped pants layer; "
                    "falling back to full significant lower components",
                    retained_ratio,
                )
                clip_bool = _keep_significant_mask_components(
                    garment_layer_present & ~protected_by_mask,
                    min_area_ratio=0.14,
                    max_components=3,
                )
    elif changed_garment.any():
        changed_guide = cv2.morphologyEx(
            changed_garment.astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((7, 7), dtype=np.uint8),
        )
        changed_guide = cv2.dilate(
            changed_guide,
            np.ones((5, 11), dtype=np.uint8),
            iterations=1,
        ).astype(bool)
        guided_clip = clip_bool & changed_guide
        if guided_clip.any():
            clip_bool = guided_clip

    clip_float = cv2.GaussianBlur(
        clip_bool.astype(np.float32),
        (7, 7),
        0,
    )
    return np.clip(clip_float, 0.0, 1.0)


def _build_lower_texture_support_mask(
    base_alpha: np.ndarray,
    protected_by_mask: np.ndarray,
    *,
    min_alpha: float = 0.18,
    x_pad: int = 5,
    y_pad: int = 5,
    row_fill_min_coverage: float = 0.0,
) -> np.ndarray:
    """Return where uploaded lower-garment texture has real warped support."""
    if base_alpha.shape != protected_by_mask.shape:
        return np.zeros_like(base_alpha, dtype=bool)

    support = (base_alpha > float(min_alpha)) & ~protected_by_mask
    if not support.any():
        return support

    support = cv2.morphologyEx(
        support.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
    ).astype(bool)
    support = _keep_significant_mask_components(
        support,
        min_area_ratio=0.08,
        max_components=3,
    )
    if not support.any():
        return support

    if row_fill_min_coverage > 0.0:
        labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
            support.astype(np.uint8),
            8,
        )
        row_filled = np.zeros_like(support, dtype=bool)
        for label_idx in range(1, labels_count):
            width = int(stats[label_idx, cv2.CC_STAT_WIDTH])
            area = int(stats[label_idx, cv2.CC_STAT_AREA])
            if width < 10 or area < 96:
                continue
            component = labels == label_idx
            min_row_pixels = max(
                6,
                int(math.ceil(width * float(row_fill_min_coverage))),
            )
            ys_comp = np.where(component.any(axis=1))[0]
            for yy_comp in ys_comp:
                xs_comp = np.where(component[yy_comp, :])[0]
                if xs_comp.size >= min_row_pixels:
                    row_filled[yy_comp, int(xs_comp[0]) : int(xs_comp[-1]) + 1] = True
        if row_filled.any():
            support |= row_filled

    kernel_h = max(1, int(y_pad) * 2 + 1)
    kernel_w = max(1, int(x_pad) * 2 + 1)
    support = cv2.dilate(
        support.astype(np.uint8),
        np.ones((kernel_h, kernel_w), dtype=np.uint8),
        iterations=1,
    ).astype(bool)
    return support & ~protected_by_mask


def _expand_lower_layer_to_clip(
    layer_np: np.ndarray,
    clip_mask: np.ndarray | None,
    *,
    min_alpha: float = 0.12,
) -> np.ndarray:
    """Compatibility helper kept as a no-op.

    We intentionally no longer synthesize lower-body pixels outside the real
    warped layer, because that caused the side ghosting regression.
    """
    del clip_mask, min_alpha
    return layer_np


def _fill_lower_layer_gaps_from_fabric(
    layer_np: np.ndarray,
    fill_mask: np.ndarray,
    *,
    min_source_alpha: float = 0.12,
) -> tuple[np.ndarray, float]:
    """Fill lower-body mask holes with nearby warped fabric pixels.

    CatVTON often generates a wider dark pants block than the deterministic
    pants warp. If we only blend where the warp has alpha, those side/waist
    blocks remain black. Inpainting the layer itself gives the blend real
    garment color to use while staying clipped to the lower-body mask.
    """
    if layer_np.ndim != 3 or layer_np.shape[2] != 4:
        return layer_np, 0.0
    if fill_mask.shape != layer_np.shape[:2]:
        return layer_np, 0.0

    alpha = layer_np[:, :, 3] / 255.0
    rgb_u8 = np.clip(layer_np[:, :, :3], 0, 255).astype(np.uint8)
    value = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2HSV)[:, :, 2].astype(np.float32)
    source_candidate = alpha > float(min_source_alpha)
    dark_artifact = np.zeros_like(source_candidate, dtype=bool)
    median_value = 0.0
    median_rgb: np.ndarray | None = None
    if source_candidate.any():
        source_values = value[source_candidate]
        median_value = float(np.median(source_values))
        source_for_color = source_candidate & (value >= max(40.0, median_value * 0.55))
        if source_for_color.any():
            median_rgb = np.median(
                rgb_u8[source_for_color].astype(np.float32),
                axis=0,
            )
        if median_value > 70.0:
            dark_artifact = source_candidate & (value < max(35.0, median_value * 0.35))
    source_mask = source_candidate & ~dark_artifact
    target_mask = fill_mask & (~source_mask | dark_artifact)
    if not source_mask.any() or not target_mask.any():
        return layer_np, 0.0

    target_u8 = target_mask.astype(np.uint8) * 255
    filled_rgb = cv2.inpaint(rgb_u8, target_u8, 5, cv2.INPAINT_TELEA)
    h, _w = target_mask.shape
    source_rows = np.flatnonzero(source_mask.any(axis=1))
    for y in range(h):
        target_x = np.flatnonzero(target_mask[y])
        if target_x.size == 0:
            continue
        source_x = np.flatnonzero(source_mask[y])
        source_y = y
        if source_x.size == 0:
            if source_rows.size == 0:
                continue
            source_y = int(source_rows[np.argmin(np.abs(source_rows - y))])
            source_x = np.flatnonzero(source_mask[source_y])
            if source_x.size == 0:
                continue
        insert_at = np.searchsorted(source_x, target_x)
        left_idx = np.clip(insert_at - 1, 0, source_x.size - 1)
        right_idx = np.clip(insert_at, 0, source_x.size - 1)
        left_x = source_x[left_idx]
        right_x = source_x[right_idx]
        nearest_x = np.where(
            np.abs(target_x - left_x) <= np.abs(right_x - target_x),
            left_x,
            right_x,
        )
        filled_rgb[y, target_x] = rgb_u8[source_y, nearest_x]
    if median_value > 70.0 and median_rgb is not None:
        filled_value = cv2.cvtColor(filled_rgb, cv2.COLOR_RGB2HSV)[:, :, 2].astype(np.float32)
        underfilled = target_mask & (filled_value < median_value * 0.55)
        filled_rgb[underfilled] = np.clip(median_rgb, 0, 255).astype(np.uint8)

    filled = layer_np.copy()
    soft_alpha = cv2.GaussianBlur(target_mask.astype(np.float32), (9, 9), 0)
    soft_alpha = np.clip(soft_alpha, 0.0, 1.0)
    blend = soft_alpha[:, :, np.newaxis]
    filled[:, :, :3] = filled_rgb.astype(np.float32) * blend + filled[:, :, :3] * (1.0 - blend)
    filled[:, :, 3] = np.maximum(filled[:, :, 3], soft_alpha * 245.0)
    filled[:, :, 3] = np.where(target_mask, np.maximum(filled[:, :, 3], 235.0), filled[:, :, 3])

    ratio = float(target_mask.sum()) / float(max(1, fill_mask.sum()))
    return filled, ratio


def _expand_lower_mask_bbox(
    mask_bbox: tuple[int, int, int, int],
    *,
    image_w: int,
    image_h: int,
    waist_y: int,
    ankle_y: int | None,
) -> tuple[int, int, int, int]:
    """Widen lower-body mask boxes before warping garment texture into them."""
    x0, y0, x1, y1 = mask_bbox
    box_w = max(1, x1 - x0)
    lower_span = max(1, (ankle_y or y1) - waist_y)

    side_pad = max(
        int(box_w * 0.12),
        int(image_w * 0.025),
        int(lower_span * 0.035),
    )
    top_band = max(0, int(image_h * 0.055))
    y0_limit = max(0, waist_y - top_band)
    new_x0 = max(0, x0 - side_pad)
    new_x1 = min(image_w, x1 + side_pad)
    new_y0 = min(y0, y0_limit)
    new_y1 = min(image_h, max(y1, (ankle_y or y1) + int(image_h * 0.02)))
    return new_x0, new_y0, new_x1, new_y1


def _pil_quad_warp(
    src_rgba: Image.Image, dst_size: tuple[int, int], quad: tuple[int, ...]
) -> Image.Image:
    """Warp src into dst_size using a quad mapping (PIL perspective)."""
    return src_rgba.transform(
        dst_size,
        Image.Transform.QUAD,
        quad,
        resample=Image.Resampling.BICUBIC,
    )


def _feather_alpha(rgba: Image.Image, radius_px: int) -> Image.Image:
    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")
    r, g, b, a = rgba.split()
    if radius_px <= 0:
        return rgba
    a2 = a.filter(ImageFilter.GaussianBlur(radius=float(radius_px)))
    return Image.merge("RGBA", (r, g, b, a2))


def _upper_protect_mask(size: tuple[int, int], protect_until_y: int) -> Image.Image:
    """Build L mask where protected area has alpha=0 (no overwrite)."""
    w, h = size
    protect_until_y = _clamp_int(protect_until_y, 0, h)
    mask = Image.new("L", (w, h), color=255)
    if protect_until_y > 0:
        mask.paste(0, (0, 0, w, protect_until_y))
    return mask


def _detect_face_box_from_result(
    catvton_result: Image.Image,
    cw: int,
    ch: int,
    original_person: Image.Image | None = None,
) -> tuple[int, int, int, int] | None:
    """Detect face bounding box for CatVTON result using Haar cascade.

    Strategy (priority order):
      1. Detect face in ORIGINAL person image (much clearer, more reliable).
         Then SCALE the detected bbox to catvton_result coordinates proportionally.
         This solves the core problem: CatVTON output degrades face quality,
         making Haar cascade detection unreliable on AI-generated faces.
      2. Fallback: detect face directly in catvton_result with histogram equalization.
      3. Final fallback: return None (caller uses coarse neck-based protection).

    Returns (x, y, w, h) in catvton_result pixel coordinates, or None if undetected.
    """
    try:
        from app.services.cascade_manager import load_cascade

        cascade = load_cascade("haarcascade_frontalface_default.xml")
        if cascade is None or cascade.empty():
            logger.warning(
                "catvton_color_fidelity_spatial: Haar cascade unavailable, "
                "falling back to coarse face protection"
            )
            return None

        # ── Priority 1: Detect on ORIGINAL person image (clear, reliable) ───────
        if original_person is not None:
            try:
                orig_arr = np.asarray(original_person.convert("RGB"))
                orig_h, orig_w = orig_arr.shape[:2]

                if orig_h < 64 or orig_w < 64:
                    raise ValueError("Original person image too small")

                orig_gray = cv2.cvtColor(orig_arr, cv2.COLOR_RGB2GRAY)
                orig_gray_eq = cv2.equalizeHist(orig_gray)

                orig_faces = cascade.detectMultiScale(
                    orig_gray_eq,
                    scaleFactor=1.1,
                    minNeighbors=4,
                    minSize=(int(orig_w * 0.06), int(orig_h * 0.06)),
                    maxSize=(int(orig_w * 0.60), int(orig_h * 0.60)),
                )

                if orig_faces is not None and len(orig_faces) > 0:
                    orig_face_list = sorted(orig_faces, key=lambda f: f[2] * f[3], reverse=True)
                    ofx, ofy, ofw, ofh = [int(v) for v in orig_face_list[0]]

                    # Scale from original person coords → catvton_result coords
                    scale_x = cw / float(orig_w)
                    scale_y = ch / float(orig_h)
                    fx = int(ofx * scale_x)
                    fy = int(ofy * scale_y)
                    fw = int(ofw * scale_x)
                    fh = int(ofh * scale_y)

                    # Safety clamp
                    fx = _clamp_int(fx, 0, cw - 1)
                    fy = _clamp_int(fy, 0, ch - 1)
                    fw = _clamp_int(fw, 4, cw)
                    fh = _clamp_int(fh, 4, ch)

                    logger.info(
                        "catvton_color_fidelity_spatial: face detected on ORIGINAL person "
                        "([%d,%d,%d,%d] at %dx%d) -> scaled to catvton([%d,%d,%d,%d] at %dx%d) "
                        "(sx=%.4f, sy=%.4f)",
                        ofx,
                        ofy,
                        ofw,
                        ofh,
                        orig_w,
                        orig_h,
                        fx,
                        fy,
                        fw,
                        fh,
                        cw,
                        ch,
                        scale_x,
                        scale_y,
                    )
                    return (fx, fy, fw, fh)
            except Exception as orig_err:
                logger.debug(
                    "catvton_color_fidelity_spatial: face detection on original failed (%s), "
                    "falling back to catvton result detection",
                    orig_err,
                )

        # ── Priority 2: Detect on CatVTON result directly (fallback) ──────────
        arr = np.asarray(catvton_result.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        gray_eq = cv2.equalizeHist(gray)

        faces = cascade.detectMultiScale(
            gray_eq,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(int(cw * 0.06), int(ch * 0.06)),
            maxSize=(int(cw * 0.60), int(ch * 0.60)),
        )
        if faces is None or len(faces) == 0:
            logger.debug(
                "catvton_color_fidelity_spatial: no face detected by Haar cascade "
                "(will use coarse neck-based protection)"
            )
            return None

        face_list = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, fy, fw, fh = [int(v) for v in face_list[0]]
        logger.info(
            "catvton_color_fidelity_spatial: face detected on CatVTON result "
            "bbox=[%d,%d,%d,%d] (%.1f%%w x %.1f%%h)",
            fx,
            fy,
            fw,
            fh,
            fw / cw * 100,
            fh / ch * 100,
        )
        return (fx, fy, fw, fh)

    except Exception as e:
        logger.warning(
            "catvton_color_fidelity_spatial: face detection failed (%s), "
            "falling back to coarse neck-based protection",
            e,
        )
        return None


def _person_foreground_mask(person_image: Image.Image) -> np.ndarray | None:
    """Best-effort person foreground mask (H,W) bool.

    Uses OpenCV GrabCut if available. This mask is used to better localize torso/legs
    so garments can auto-adjust position and size based on the person's shape.
    """
    try:

        arr = np.asarray(person_image.convert("RGB"))
        h, w = arr.shape[:2]
        if h < 96 or w < 96:
            return None

        mask = np.zeros((h, w), np.uint8)
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)
        rect = (int(w * 0.10), int(h * 0.06), int(w * 0.80), int(h * 0.90))
        cv2.grabCut(arr, mask, rect, bgdModel, fgdModel, 2, cv2.GC_INIT_WITH_RECT)
        fg = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
        if fg.mean() < 0.05:
            return None
        return fg
    except Exception:
        return None


def _bounds_from_mask(
    fg: np.ndarray, *, y0: int, y1: int, col_q: float, row_q: float
) -> tuple[int, int, int, int] | None:
    """Estimate (x0,x1, y_top, y_bottom) from a foreground mask within a y-range."""
    h, w = fg.shape[:2]
    y0 = _clamp_int(int(y0), 0, h - 2)
    y1 = _clamp_int(int(y1), y0 + 2, h)
    roi = fg[y0:y1, :]
    if roi.size == 0:
        return None

    col = roi.mean(axis=0)
    cthr = float(np.quantile(col, col_q))
    xs = np.where(col >= max(cthr, 0.05))[0]
    if xs.size < max(10, int(w * 0.10)):
        return None
    x0, x1 = int(xs.min()), int(xs.max()) + 1

    row = fg[:, x0:x1].mean(axis=1)
    seg = row[y0:y1]
    rthr = float(np.quantile(seg, row_q)) if seg.size else float(np.quantile(row, row_q))
    ys = np.where(row >= max(rthr, 0.06))[0]
    ys = ys[(ys >= y0) & (ys <= y1)]
    if ys.size < 10:
        return None
    yt, yb = int(ys.min()), int(ys.max()) + 1
    return _clamp_int(x0, 0, w - 2), _clamp_int(x1, x0 + 2, w), yt, yb


def _estimate_lower_body_bounds(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Estimate (x0, x1, waist_y, ankle_y) for person image.

    Uses gradient energy distribution (model-free, fast) to reduce the
    "floating pants" effect when the person is off-center or legs are long.
    """
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return int(w * 0.22), int(w * 0.78), int(h * 0.40), int(h * 0.96)

    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx * gx + gy * gy)

    y_roi0 = int(h * 0.28)
    y_roi1 = int(h * 0.98)
    roi = grad[y_roi0:y_roi1, :]
    if roi.size == 0:
        return int(w * 0.22), int(w * 0.78), int(h * 0.40), int(h * 0.96)

    col_energy = roi.mean(axis=0)
    thr = float(np.quantile(col_energy, 0.80))
    cols = np.where(col_energy >= thr)[0]
    if cols.size >= max(8, int(w * 0.06)):
        x0 = int(cols.min())
        x1 = int(cols.max()) + 1
        # Keep pad conservative; too much pad causes "floating cloth" on sides.
        pad = int((x1 - x0) * 0.06)
        x0 = _clamp_int(x0 - pad, 0, w - 2)
        x1 = _clamp_int(x1 + pad, x0 + 2, w)
    else:
        x0 = int(w * 0.22)
        x1 = int(w * 0.78)

    row_energy = grad[:, x0:x1].mean(axis=1)
    waist_search0 = int(h * 0.26)
    waist_search1 = int(h * 0.60)
    seg = row_energy[waist_search0:waist_search1]
    rthr = float(np.quantile(seg, 0.70)) if seg.size else float(np.quantile(row_energy, 0.70))
    candidates = np.where(row_energy >= rthr)[0]
    candidates = candidates[(candidates >= waist_search0) & (candidates <= waist_search1)]
    waist_y = int(candidates.min()) if candidates.size else int(h * 0.40)

    ankle_search0 = int(h * 0.65)
    ankle_search1 = int(h * 0.98)
    seg2 = row_energy[ankle_search0:ankle_search1]
    rthr2 = float(np.quantile(seg2, 0.55)) if seg2.size else rthr
    candidates2 = np.where(row_energy >= rthr2)[0]
    candidates2 = candidates2[(candidates2 >= ankle_search0) & (candidates2 <= ankle_search1)]
    ankle_y = int(candidates2.max()) if candidates2.size else int(h * 0.96)

    waist_y = _clamp_int(waist_y, int(h * 0.30), int(h * 0.55))
    ankle_y = _clamp_int(ankle_y, int(h * 0.75), int(h * 0.98))
    return x0, x1, waist_y, ankle_y


def _estimate_upper_body_bounds(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Estimate (x0, x1, neck_y, waist_y) for upper body placement."""
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return int(w * 0.20), int(w * 0.80), int(h * 0.14), int(h * 0.62)

    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx * gx + gy * gy)

    y_roi0 = int(h * 0.08)
    y_roi1 = int(h * 0.70)
    roi = grad[y_roi0:y_roi1, :]
    if roi.size == 0:
        return int(w * 0.20), int(w * 0.80), int(h * 0.14), int(h * 0.62)

    col_energy = roi.mean(axis=0)
    thr = float(np.quantile(col_energy, 0.82))
    cols = np.where(col_energy >= thr)[0]
    if cols.size >= max(8, int(w * 0.06)):
        x0 = int(cols.min())
        x1 = int(cols.max()) + 1
        pad = int((x1 - x0) * 0.10)
        x0 = _clamp_int(x0 - pad, 0, w - 2)
        x1 = _clamp_int(x1 + pad, x0 + 2, w)
    else:
        x0 = int(w * 0.20)
        x1 = int(w * 0.80)

    row_energy = grad[:, x0:x1].mean(axis=1)
    neck_search0 = int(h * 0.06)
    neck_search1 = int(h * 0.30)
    seg = row_energy[neck_search0:neck_search1]
    rthr = float(np.quantile(seg, 0.72)) if seg.size else float(np.quantile(row_energy, 0.72))
    candidates = np.where(row_energy >= rthr)[0]
    candidates = candidates[(candidates >= neck_search0) & (candidates <= neck_search1)]
    neck_y = int(candidates.min()) if candidates.size else int(h * 0.14)

    waist_search0 = int(h * 0.30)
    waist_search1 = int(h * 0.72)
    seg2 = row_energy[waist_search0:waist_search1]
    rthr2 = float(np.quantile(seg2, 0.58)) if seg2.size else rthr
    candidates2 = np.where(row_energy >= rthr2)[0]
    candidates2 = candidates2[(candidates2 >= waist_search0) & (candidates2 <= waist_search1)]
    waist_y = int(candidates2.max()) if candidates2.size else int(h * 0.62)

    neck_y = _clamp_int(neck_y, int(h * 0.08), int(h * 0.28))
    waist_y = _clamp_int(waist_y, int(h * 0.42), int(h * 0.78))
    return x0, x1, neck_y, waist_y


def _compute_target_boxes(
    person_image: Image.Image,
) -> tuple[tuple[int, int, int, int], ...]:
    """Adaptive target boxes (waist, left leg, right leg) in person coordinates."""
    gray = np.asarray(person_image.convert("L"), dtype=np.float32)
    ph, pw = gray.shape[:2]

    fg = _person_foreground_mask(person_image)
    if fg is not None:
        b = _bounds_from_mask(fg, y0=int(ph * 0.28), y1=int(ph * 0.98), col_q=0.70, row_q=0.55)
    else:
        b = None
    if b is not None:
        x0, x1, y_top, y_bottom = b
        waist_y = _clamp_int(int(y_top + (y_bottom - y_top) * 0.20), int(ph * 0.30), int(ph * 0.55))
        ankle_y = _clamp_int(int(y_bottom), int(ph * 0.75), int(ph * 0.98))
    else:
        x0, x1, waist_y, ankle_y = _estimate_lower_body_bounds(gray)
    body_w = max(2, x1 - x0)
    mid = x0 + body_w // 2

    waist_h = _clamp_int(int(ph * 0.055), 28, int(ph * 0.08))
    wy0 = _clamp_int(waist_y - waist_h // 2, 0, ph - 2)
    wy1 = _clamp_int(waist_y + waist_h // 2, wy0 + 2, ph)
    waistband_box = (x0, wy0, x1, wy1)

    leg_y0 = _clamp_int(wy1 - max(2, int(ph * 0.006)), 0, ph - 2)
    leg_y1 = _clamp_int(ankle_y, leg_y0 + 2, ph)
    mid = _clamp_int(mid, x0 + 2, x1 - 2)

    left_leg_box = (x0, leg_y0, mid, leg_y1)
    right_leg_box = (mid, leg_y0, x1, leg_y1)
    return waistband_box, left_leg_box, right_leg_box


def _resolve_pants_target_boxes(
    person_image: Image.Image,
    *,
    flare_ratio: float,
    pose_keypoints: dict[str, tuple[float, float]] | None = None,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int], bool]:
    """Compute widened pants target boxes and whether pose bounds were available."""
    pw, ph = person_image.size
    kpts = pose_keypoints if pose_keypoints is not None else detect_pose_keypoints(person_image)

    if kpts:
        bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "bottom")
        if bounds.get("valid"):
            x0 = bounds["x0"]
            x1 = bounds["x1"]
            waist_y = bounds["waist_y"]
            ankle_y = bounds["ankle_y"]
            body_w = max(2, x1 - x0)
            mid = x0 + body_w // 2

            waist_h = _clamp_int(int(ph * 0.055), 28, int(ph * 0.08))
            wy0 = _clamp_int(waist_y - waist_h // 2, 0, ph - 2)
            wy1 = _clamp_int(waist_y + waist_h // 2, wy0 + 2, ph)
            waistband_box: tuple[int, int, int, int] = (x0, wy0, x1, wy1)

            leg_y0 = _clamp_int(wy1 - max(2, int(ph * 0.006)), 0, ph - 2)
            leg_y1 = _clamp_int(ankle_y, leg_y0 + 2, ph)
            mid = _clamp_int(mid, x0 + 2, x1 - 2)
            left_leg_box: tuple[int, int, int, int] = (x0, leg_y0, mid, leg_y1)
            right_leg_box: tuple[int, int, int, int] = (mid, leg_y0, x1, leg_y1)
            used_pose = True
        else:
            waistband_box, left_leg_box, right_leg_box = _compute_target_boxes(person_image)
            used_pose = False
    else:
        waistband_box, left_leg_box, right_leg_box = _compute_target_boxes(person_image)
        used_pose = False

    waistband_box, left_leg_box, right_leg_box = _expand_pants_target_boxes(
        waistband_box,
        left_leg_box,
        right_leg_box,
        image_w=pw,
        flare_ratio=flare_ratio,
    )
    return waistband_box, left_leg_box, right_leg_box, used_pose


def _build_pants_warp_layer(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.012,
    use_knee_split: bool = False,
    include_waistband: bool = False,
    top_extend_ratio: float = 0.0,
    bottom_extend_ratio: float = 0.0,
    waist_raise_ratio: float = 0.0,
    skip_waistband_trim: bool = False,
    protect_upper_body: bool = True,
) -> tuple[Image.Image, WarpMetadata]:
    """Build an RGBA pants warp layer that can be reused by stage-1 and step-12.

    waist_raise_ratio: optional upward shift of the waistband (fraction of image height).
    Used by lower_warp_primary to cover high-waist original pants; default 0 keeps
    other callers unchanged.
    skip_waistband_trim: when True, keep the raised waistband (body-curve trim would
    otherwise erase the high-waist coverage we just added).
    """
    pw, ph = person_image.size

    cutout = cutout_garment_rgba(garment_image)
    flare_ratio, wide_leg = _estimate_pants_flare_ratio(cutout.cropped)

    kpts = detect_pose_keypoints(person_image)
    _left_knee_y: float | None = None
    _right_knee_y: float | None = None
    _left_ankle_y: float | None = None
    _right_ankle_y: float | None = None
    _knee_garment_ratio: float | None = None

    if kpts:
        lk = kpts.get("left_knee")
        rk = kpts.get("right_knee")
        la = kpts.get("left_ankle")
        ra = kpts.get("right_ankle")
        if lk and la:
            leg_total = la[1] - lk[1]
            if leg_total > 0:
                _left_knee_y = lk[1]
                _left_ankle_y = la[1]
        if rk and ra:
            leg_total = ra[1] - rk[1]
            if leg_total > 0:
                _right_knee_y = rk[1]
                _right_ankle_y = ra[1]
        ratios = []
        if _left_knee_y and _left_ankle_y:
            ratios.append((_left_knee_y - 0.20) / (_left_ankle_y - 0.20))
        if _right_knee_y and _right_ankle_y:
            ratios.append((_right_knee_y - 0.20) / (_right_ankle_y - 0.20))
        if ratios:
            avg = sum(ratios) / len(ratios)
            _knee_garment_ratio = max(0.30, min(0.65, avg))

    if use_knee_split and _knee_garment_ratio is not None:
        parts = split_pants_parts(cutout.cropped, knee_garment_ratio=_knee_garment_ratio)
    else:
        parts = split_pants_parts(cutout.cropped)

    waistband_box, left_leg_box, right_leg_box, used_pose = _resolve_pants_target_boxes(
        person_image,
        flare_ratio=flare_ratio,
        pose_keypoints=kpts,
    )
    if bottom_extend_ratio > 0:
        extend_px = max(0, int(round(ph * float(bottom_extend_ratio))))
        if extend_px:
            left_leg_box = (
                left_leg_box[0],
                left_leg_box[1],
                left_leg_box[2],
                _clamp_int(left_leg_box[3] + extend_px, left_leg_box[1] + 2, ph),
            )
            right_leg_box = (
                right_leg_box[0],
                right_leg_box[1],
                right_leg_box[2],
                _clamp_int(right_leg_box[3] + extend_px, right_leg_box[1] + 2, ph),
            )

    if waist_raise_ratio > 0:
        raise_px = max(0, int(round(ph * float(waist_raise_ratio))))
        if raise_px:
            # Stay below upper-body protect band (~0.30ph).
            min_wy0 = _clamp_int(int(ph * 0.32), 0, ph - 4)
            wx0, wy0, wx1, wy1 = waistband_box
            band_h = max(2, wy1 - wy0)
            # Shift the band up; keep height so waist texture is not vertically smeared.
            new_wy0 = _clamp_int(wy0 - raise_px, min_wy0, ph - band_h - 2)
            new_wy1 = _clamp_int(new_wy0 + band_h, new_wy0 + 2, ph)
            waistband_box = (wx0, new_wy0, wx1, new_wy1)
            # Attach leg tops under the raised band.
            leg_y0 = _clamp_int(new_wy1 - max(2, int(ph * 0.006)), 0, ph - 2)
            left_leg_box = (
                left_leg_box[0],
                leg_y0,
                left_leg_box[2],
                left_leg_box[3],
            )
            right_leg_box = (
                right_leg_box[0],
                leg_y0,
                right_leg_box[2],
                right_leg_box[3],
            )

    logger.info(
        "pants_warp_layer: flare_ratio=%.3f wide_leg=%s boxes waist=%s left=%s right=%s",
        flare_ratio,
        wide_leg,
        waistband_box,
        left_leg_box,
        right_leg_box,
    )

    if not include_waistband:
        top_extend_px = max(0, int(round(ph * float(top_extend_ratio))))
        leg_start_y = _clamp_int(waistband_box[1] - top_extend_px, 0, ph - 2)
        left_leg_box = (left_leg_box[0], leg_start_y, left_leg_box[2], left_leg_box[3])
        right_leg_box = (right_leg_box[0], leg_start_y, right_leg_box[2], right_leg_box[3])
        visible_waistband_box = (0, 0, 0, 0)
    else:
        visible_waistband_box = waistband_box

    leg_taper_ratio = 0.04 if wide_leg else (0.06 if flare_ratio >= 1.08 else 0.10)

    def _warp_into_box(src: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
        x0, y0, x1, y1 = box
        tw = max(2, x1 - x0)
        th = max(2, y1 - y0)
        inset = int(tw * leg_taper_ratio)
        quad = (
            0,
            0,
            src.size[0],
            0,
            src.size[0],
            src.size[1],
            0,
            src.size[1],
        )
        warped = _pil_quad_warp(src, (tw, th), quad)
        if box in (left_leg_box, right_leg_box) and tw >= 12:
            tw2, th2 = warped.size
            quad2 = (
                inset,
                0,
                tw2 - inset,
                0,
                tw2,
                th2,
                0,
                th2,
            )
            warped = _pil_quad_warp(warped, (tw2, th2), quad2)
        canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        canvas.paste(warped, (x0, y0), warped)
        return canvas

    if include_waistband:
        layer_waist = _warp_into_box(parts.waistband, waistband_box)
    else:
        layer_waist = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))

    def _warp_two_stage(
        src_upper: Image.Image,
        src_lower: Image.Image,
        leg_box: tuple[int, int, int, int],
        knee_person_y: float | None = None,
    ) -> Image.Image:
        if knee_person_y is None:
            return _warp_into_box(src_upper, leg_box)

        x0, y0_full, x1, y1_full = leg_box
        knee_y_clamped = _clamp_int(int(knee_person_y), y0_full + 2, y1_full - 2)
        upper_box = (x0, y0_full, x1, knee_y_clamped)
        lower_box = (x0, knee_y_clamped, x1, y1_full)

        # Overlap at the knee so upper/lower halves don't leave a bright seam.
        overlap = _clamp_int(int((y1_full - y0_full) * 0.04), 6, 28)
        upper_box = (x0, y0_full, x1, _clamp_int(knee_y_clamped + overlap, y0_full + 2, y1_full))
        lower_box = (x0, _clamp_int(knee_y_clamped - overlap, y0_full, y1_full - 2), x1, y1_full)

        canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        upper_layer = _warp_into_box(src_upper, upper_box)
        canvas = Image.alpha_composite(canvas, upper_layer)
        lower_layer = _warp_into_box(src_lower, lower_box)
        canvas = Image.alpha_composite(canvas, lower_layer)
        return canvas

    if (
        use_knee_split
        and parts.left_upper is not None
        and parts.left_lower is not None
        and parts.right_upper is not None
        and parts.right_lower is not None
        and _left_knee_y is not None
        and _right_knee_y is not None
    ):
        left_knee_px = int(_left_knee_y * ph)
        right_knee_px = int(_right_knee_y * ph)
        layer_left = _warp_two_stage(
            parts.left_upper,
            parts.left_lower,
            left_leg_box,
            knee_person_y=left_knee_px,
        )
        layer_right = _warp_two_stage(
            parts.right_upper,
            parts.right_lower,
            right_leg_box,
            knee_person_y=right_knee_px,
        )
    else:
        layer_left = _warp_into_box(parts.left_leg, left_leg_box)
        layer_right = _warp_into_box(parts.right_leg, right_leg_box)

    merged = Image.alpha_composite(Image.alpha_composite(layer_left, layer_right), layer_waist)
    waistband_trim_meta: dict | None = None
    if include_waistband and visible_waistband_box != (0, 0, 0, 0) and not skip_waistband_trim:
        guides = _estimate_lower_structure_guides(person_image)
        merged, waistband_trim_meta = _trim_lower_waistband_to_body_curve(
            merged,
            waistband_box=visible_waistband_box,
            left_leg_box=left_leg_box,
            right_leg_box=right_leg_box,
            guides=guides,
        )
    elif skip_waistband_trim and include_waistband:
        waistband_trim_meta = {"applied": False, "reason": "skipped_for_waist_raise"}
        logger.info("pants_warp_layer: waistband trim skipped (preserve raised waist)")

    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 12)
    if wide_leg:
        feather_px = min(feather_px, max(4, int(min(pw, ph) * 0.0075)))
    elif flare_ratio >= 1.08:
        feather_px = min(feather_px, max(3, int(min(pw, ph) * 0.0090)))
    merged = _feather_alpha(merged, radius_px=feather_px)

    if protect_upper_body:
        protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.30))
        if merged.mode != "RGBA":
            merged = merged.convert("RGBA")
        r, g, b, a = merged.split()
        a = ImageChops.multiply(a, protect)
        merged = Image.merge("RGBA", (r, g, b, a))

    engine_tag = "pants_warp_v2_pose" if used_pose else "pants_warp_v1_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=visible_waistband_box,
        left_leg_box=left_leg_box,
        right_leg_box=right_leg_box,
        alpha_feather_px=feather_px,
    )
    if waistband_trim_meta:
        logger.info("pants_warp_layer: waistband trim meta=%s", waistband_trim_meta)
    return merged, meta


def _lower_warp_primary_box_extends(
    person_image: Image.Image,
) -> tuple[float, float, dict]:
    """Compute waist-raise / hem-extend ratios for lower_warp_primary only.

    Default pose boxes stop at the ankle joint and natural waist; high-waist
    long pants need the warp target raised and extended toward the shoe line.
    """
    pw, ph = person_image.size
    kpts = detect_pose_keypoints(person_image)
    bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "bottom") if kpts else {"valid": False}

    waist_raise = 0.07
    hem_extend = 0.10
    ankle_y = int(bounds.get("ankle_y", int(ph * 0.81))) if bounds.get("valid") else int(ph * 0.81)
    x0 = int(bounds.get("x0", int(pw * 0.28))) if bounds.get("valid") else int(pw * 0.28)
    x1 = int(bounds.get("x1", int(pw * 0.72))) if bounds.get("valid") else int(pw * 0.72)
    x0 = _clamp_int(x0, 0, pw - 2)
    x1 = _clamp_int(x1, x0 + 2, pw)

    # Look below the ankle for remaining bright original pant fabric before shoes/floor.
    arr = np.asarray(person_image.convert("RGB"), dtype=np.float32)
    search_y1 = _clamp_int(ankle_y + int(ph * 0.18), ankle_y + 1, ph)
    detected_hem_y = None
    if search_y1 > ankle_y + 2:
        roi = arr[ankle_y:search_y1, x0:x1]
        if roi.size:
            lum = roi.mean(axis=2)
            # White / light pants stay bright; stop before dim shoe/floor rows.
            bright_frac = (lum > 155).mean(axis=1)
            good = np.where(bright_frac > 0.10)[0]
            if good.size:
                detected_hem_y = ankle_y + int(good.max())
                needed = (detected_hem_y - ankle_y + max(4, int(ph * 0.012))) / float(ph)
                hem_extend = max(hem_extend, float(needed))

    # Leave a little room above the image bottom so sneakers stay visible.
    max_hem = max(0.04, (ph - 4 - ankle_y) / float(ph) - 0.025)
    hem_extend = float(np.clip(hem_extend, 0.05, min(0.15, max_hem)))
    # Cover high-waist originals without entering the upper protect zone.
    waist_raise = float(np.clip(waist_raise, 0.05, 0.09))

    meta = {
        "waist_raise_ratio": round(waist_raise, 4),
        "hem_extend_ratio": round(hem_extend, 4),
        "ankle_y": int(ankle_y),
        "detected_hem_y": int(detected_hem_y) if detected_hem_y is not None else None,
        "box_x0": int(x0),
        "box_x1": int(x1),
    }
    return waist_raise, hem_extend, meta


def tryon_pants_warp(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.012,
    use_knee_split: bool = True,
    include_waistband: bool = False,
) -> tuple[Image.Image, WarpMetadata]:
    """Return (result_rgb, metadata).

    Uses MediaPipe Pose keypoints (hips/knees/ankles) when available for
    accurate waist and leg placement; falls back to gradient energy estimation.

    Two-stage warp for patterned pants:
      - Stage 1: waistband + upper legs (hip?knee) ? single taper
      - Stage 2: lower legs (knee?ankle) ? full taper
    This preserves knee-bend pattern symmetry vs. single-taper warp.
    """
    base = person_image.convert("RGBA")
    merged, meta = _build_pants_warp_layer(
        person_image=person_image,
        garment_image=garment_image,
        alpha_feather_ratio=alpha_feather_ratio,
        use_knee_split=use_knee_split,
        include_waistband=include_waistband,
        protect_upper_body=True,
    )
    out = Image.alpha_composite(base, merged).convert("RGB")
    return out, meta


def tryon_lower_warp_primary(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    drape_alpha: float = 0.18,
    debug_session_dir: str | None = None,
) -> tuple[Image.Image, dict]:
    """Lower-only try-on: continuous left/right leg warp + light body shading.

    Does NOT call CatVTON. Does NOT use knee-split (avoids 2x2 tile seams).
    Raises the waist target and extends hems past the ankle toward the shoe line.
    Preserves uploaded pants color/texture by compositing warped garment pixels.
    Upper try-on must not use this path.
    """
    try:
        denim_like = _is_denim_like_garment(garment_image)
        pattern_strength = _detect_pattern_strength(garment_image)
        waist_raise, hem_extend, box_ext_meta = _lower_warp_primary_box_extends(person_image)
        logger.info(
            "lower_warp_primary box extends: waist_raise=%.3f hem_extend=%.3f meta=%s",
            waist_raise,
            hem_extend,
            box_ext_meta,
        )
        layer, warp_meta = _build_pants_warp_layer(
            person_image=person_image,
            garment_image=garment_image,
            alpha_feather_ratio=0.006 if pattern_strength >= 0.55 else 0.009,
            # Continuous whole-leg warp — knee-split creates visible 2x2 tiles.
            use_knee_split=False,
            include_waistband=not denim_like,
            bottom_extend_ratio=hem_extend,
            waist_raise_ratio=waist_raise,
            # Body-curve trim would erase the raised high-waist coverage.
            skip_waistband_trim=True,
            protect_upper_body=True,
        )

        person_rgba = person_image.convert("RGBA")
        person_np = np.asarray(person_rgba, dtype=np.float32)
        layer_np = np.asarray(layer.convert("RGBA"), dtype=np.float32)
        alpha = np.clip(layer_np[:, :, 3:4] / 255.0, 0.0, 1.0)

        # Gentle body shading from the person photo (keeps dark browns dark).
        if float(drape_alpha) > 0 and float(alpha.mean()) > 0:
            person_y = person_np[:, :, :3].mean(axis=2, keepdims=True)
            gar_y = np.maximum(layer_np[:, :, :3].mean(axis=2, keepdims=True), 1.0)
            # Only modulate where garment is opaque.
            shade = np.clip(person_y / 180.0, 0.55, 1.15)
            strength = float(np.clip(drape_alpha, 0.0, 0.45))
            shaded_rgb = layer_np[:, :, :3] * ((1.0 - strength) + strength * shade)
            # Avoid washing out very dark garments.
            dark_keep = np.clip(gar_y / 80.0, 0.35, 1.0)
            shaded_rgb = layer_np[:, :, :3] * (1.0 - dark_keep) + shaded_rgb * dark_keep
            layer_np[:, :, :3] = np.clip(shaded_rgb, 0, 255)

        merged = Image.fromarray(layer_np.astype(np.uint8), mode="RGBA")
        out = Image.alpha_composite(person_rgba, merged).convert("RGB")

        meta = {
            "engine": "lower_warp_primary",
            "catvton_used": False,
            "use_knee_split": False,
            "include_waistband": not denim_like,
            "denim_like": bool(denim_like),
            "pattern_strength": round(float(pattern_strength), 4),
            "drape_alpha": float(drape_alpha),
            "waist_raise_ratio": round(float(waist_raise), 4),
            "hem_extend_ratio": round(float(hem_extend), 4),
            "box_extends": box_ext_meta,
            "waistband_box": list(warp_meta.waistband_box),
            "left_leg_box": list(warp_meta.left_leg_box),
            "right_leg_box": list(warp_meta.right_leg_box),
            "alpha_feather_px": int(warp_meta.alpha_feather_px),
            "alpha_coverage": round(float(alpha.mean()), 4),
        }
        if debug_session_dir:
            try:
                from app.services.tryon_debug_utils import save_debug_stage_image

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename="11_lower_warp_primary_layer.png",
                    image=merged,
                    metadata={"stage": "lower_warp_primary_layer", **meta},
                )
                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename="12_lower_warp_primary_result.jpg",
                    image=out,
                    metadata={"stage": "lower_warp_primary_result", **meta},
                )
            except Exception:
                pass
        return out, meta
    except Exception as e:
        logger.warning("tryon_lower_warp_primary failed: %s", e)
        # Last resort: continuous whole-leg paste (still no knee-split tiles).
        out, warp_meta = tryon_pants_warp(
            person_image,
            garment_image,
            use_knee_split=False,
            include_waistband=True,
        )
        return out, {
            "engine": "lower_warp_primary_fallback",
            "catvton_used": False,
            "use_knee_split": False,
            "error": str(e),
            "waistband_box": list(warp_meta.waistband_box),
            "left_leg_box": list(warp_meta.left_leg_box),
            "right_leg_box": list(warp_meta.right_leg_box),
        }


def tryon_lower_structure_preserve(
    person_image: Image.Image,
    garment_image: Image.Image,
    catvton_result: Image.Image,
    *,
    raw_mask_image: Image.Image | None = None,
    drape_alpha: float = 0.22,
    debug_session_dir: str | None = None,
) -> tuple[Image.Image, dict]:
    """Prioritize uploaded lower-garment structure over CatVTON hallucinated style.

    This is intentionally stricter than color fidelity: it composites only the
    actual pants warp alpha onto the person while reusing CatVTON luminance as a
    shading layer. It does not expand into CatVTON mask holes.
    """
    try:
        denim_like = _is_denim_like_garment(garment_image)
        pattern_strength = _detect_pattern_strength(garment_image)
        strong_pattern_lower = bool(pattern_strength >= 0.72)
        structured_pattern_lower = bool(strong_pattern_lower and not denim_like)
        mask_bbox = _raw_mask_bbox(raw_mask_image, person_image.size)
        extension_meta: dict = {"source": "default"}
        top_extend_ratio = 0.0
        bottom_extend_ratio = 0.0
        if denim_like:
            try:
                cutout = cutout_garment_rgba(garment_image)
                flare_ratio, _wide_leg = _estimate_pants_flare_ratio(cutout.cropped)
                waist_box, left_box, _right_box, _used_pose = _resolve_pants_target_boxes(
                    person_image,
                    flare_ratio=flare_ratio,
                )
                top_extend_ratio, bottom_extend_ratio, extension_meta = _denim_extension_from_mask(
                    mask_bbox=mask_bbox,
                    waist_box=waist_box,
                    left_leg_box=left_box,
                    image_h=person_image.size[1],
                )
            except Exception as ext_err:
                top_extend_ratio, bottom_extend_ratio = 0.045, 0.03
                extension_meta = {"source": "fallback", "reason": str(ext_err)}
        layer, warp_meta = _build_pants_warp_layer(
            person_image=person_image,
            garment_image=garment_image,
            alpha_feather_ratio=0.0045 if structured_pattern_lower else 0.0075,
            use_knee_split=True,
            include_waistband=not denim_like,
            top_extend_ratio=top_extend_ratio,
            bottom_extend_ratio=bottom_extend_ratio,
            protect_upper_body=False,
        )
        light_waistband_cutout_meta: dict | None = None
        if structured_pattern_lower:
            layer, light_waistband_cutout_meta = _restore_light_waistband_from_garment_cutout(
                layer,
                garment_image,
                warp_meta=warp_meta,
                structured_pattern_lower=structured_pattern_lower,
            )
        layer_np = np.asarray(layer.convert("RGBA"), dtype=np.float32)
        qc = _assess_lower_warp_layer_qc(layer_np, lower_warp_meta=warp_meta)
        qc_accepted = _accept_lower_structure_qc_for_texture(qc, denim_like=denim_like)
        structured_pattern_qc_override = bool(
            not qc_accepted
            and strong_pattern_lower
            and set(qc.get("reasons") or []) == {"waistband_texture_smear"}
            and float(qc.get("alpha_coverage", 1.0) or 1.0) <= 0.20
            and float(qc.get("hem_bright_leak_score", 1.0) or 0.0) < 0.35
            and int(qc.get("component_count", 99) or 0) <= 2
            and float(qc.get("largest_component_ratio", 0.0) or 0.0) >= 0.90
        )
        if structured_pattern_qc_override:
            qc_accepted = True
        denim_waistband_texture_override = (
            qc_accepted
            and denim_like
            and warp_meta.waistband_box != (0, 0, 0, 0)
            and not qc.get("passed", False)
            and set(qc.get("reasons") or []) == {"waistband_texture_smear"}
        )
        alpha = layer_np[:, :, 3] / 255.0
        if alpha.max() < 0.08:
            return catvton_result.convert("RGB").resize(person_image.size, Image.LANCZOS), {
                "engine": "lower_structure_preserve",
                "reason": "empty_warp_layer",
                "lower_warp_qc": qc,
                "lower_denim_like": denim_like,
                "lower_warp_qc_accepted": False,
            }
        if not qc_accepted:
            return catvton_result.convert("RGB").resize(person_image.size, Image.LANCZOS), {
                "engine": "lower_structure_preserve",
                "reason": "warp_layer_qc_failed",
                "fallback_recommended": "spatial",
                "lower_warp_qc": qc,
                "lower_denim_like": denim_like,
                "lower_warp_qc_accepted": False,
            }

        base = person_image.convert("RGBA")
        if layer.size != base.size:
            layer = layer.resize(base.size, Image.Resampling.LANCZOS)
            layer_np = np.asarray(layer.convert("RGBA"), dtype=np.float32)
        if denim_waistband_texture_override:
            wx0, wy0, wx1, wy1 = warp_meta.waistband_box
            lx0, ly0, lx1, ly1 = warp_meta.left_leg_box
            rx0, ry0, rx1, ry1 = warp_meta.right_leg_box
            y_pad = max(4, int(base.size[1] * 0.008))
            x_pad = max(16, int(base.size[0] * 0.025))
            sy0 = _clamp_int(wy0 - y_pad, 0, base.size[1])
            sy1 = _clamp_int(wy1 + y_pad, sy0 + 1, base.size[1])
            sx0 = _clamp_int(wx0 - x_pad, 0, base.size[0])
            sx1 = _clamp_int(wx1 + x_pad, sx0 + 1, base.size[0])
            src_x0 = _clamp_int(min(lx0, rx0), 0, base.size[0] - 1)
            src_x1 = _clamp_int(max(lx1, rx1), src_x0 + 1, base.size[0])
            leg_y0 = _clamp_int(min(ly0, ry0), 0, base.size[1] - 1)
            src_y0 = _clamp_int(leg_y0 + max(12, int(base.size[1] * 0.018)), 0, base.size[1] - 1)
            src_y1 = _clamp_int(
                src_y0 + max(sy1 - sy0, int(base.size[1] * 0.085)),
                src_y0 + 1,
                base.size[1],
            )
            source_patch = layer_np[src_y0:src_y1, src_x0:src_x1, :]
            if source_patch.size:
                patch = Image.fromarray(
                    np.clip(source_patch, 0, 255).astype(np.uint8),
                    mode="RGBA",
                ).resize((sx1 - sx0, sy1 - sy0), Image.Resampling.BILINEAR)
                patch_np = np.asarray(patch, dtype=np.uint8)
                patch_rgb = patch_np[:, :, :3]
                patch_alpha = patch_np[:, :, 3]
                missing = patch_alpha <= 20
                if missing.any() and missing.mean() < 0.65:
                    patch_rgb = cv2.inpaint(
                        patch_rgb,
                        missing.astype(np.uint8) * 255,
                        3,
                        cv2.INPAINT_TELEA,
                    )
                elif missing.any():
                    valid_rgb = patch_rgb[~missing]
                    fill_rgb = (
                        np.median(valid_rgb, axis=0).astype(np.uint8)
                        if valid_rgb.size
                        else np.array([80, 110, 145], dtype=np.uint8)
                    )
                    patch_rgb = patch_rgb.copy()
                    patch_rgb[missing] = fill_rgb
                target_alpha = layer_np[sy0:sy1, sx0:sx1, 3]
                target_mask = target_alpha > 20
                layer_np[sy0:sy1, sx0:sx1, :3] = np.where(
                    target_mask[:, :, np.newaxis],
                    patch_rgb.astype(np.float32),
                    layer_np[sy0:sy1, sx0:sx1, :3],
                )
            layer = Image.fromarray(np.clip(layer_np, 0, 255).astype(np.uint8), mode="RGBA")
        alpha = layer_np[:, :, 3] / 255.0

        guides = _estimate_lower_structure_guides(person_image)
        soft_mask, mask_meta = _build_lower_structure_blend_masks(
            person_image=person_image,
            layer_alpha=alpha,
            guides=guides,
            prefer_layer_extent=denim_like,
        )
        shaded_layer_np, shading_meta = _apply_lower_luminance_shading(
            layer_np=np.asarray(layer.convert("RGBA"), dtype=np.uint8),
            ai_rgb=np.asarray(
                catvton_result.convert("RGB").resize(base.size, Image.Resampling.BILINEAR),
                dtype=np.float32,
            ),
            blend_mask=soft_mask,
            shading_strength=0.18 if denim_like else (0.32 if structured_pattern_lower else 1.0),
        )
        color_unify_meta: dict | None = None
        if denim_like:
            shaded_layer_np, color_unify_meta = _normalize_lower_layer_to_source_color(
                shaded_layer_np,
                garment_image,
                soft_mask,
                strength=0.72,
            )
        light_waistband_mask: np.ndarray | None = None
        light_waistband_meta: dict | None = None
        if structured_pattern_lower:
            light_waistband_mask, light_waistband_meta = _detect_light_structured_lower_waistband(
                np.asarray(layer.convert("RGBA"), dtype=np.uint8),
                warp_meta=warp_meta,
            )
        light_waistband_protected = bool(
            (light_waistband_mask is not None)
            or (
                isinstance(light_waistband_cutout_meta, dict)
                and bool(light_waistband_cutout_meta.get("applied"))
            )
        )

        if structured_pattern_lower and warp_meta.waistband_box != (0, 0, 0, 0):
            wx0, wy0, wx1, wy1 = warp_meta.waistband_box
            y_pad = max(4, int(base.size[1] * 0.007))
            x_pad = max(10, int(base.size[0] * 0.018))
            sy0 = _clamp_int(wy0 - y_pad, 0, base.size[1])
            sy1 = _clamp_int(wy1 + y_pad, sy0 + 1, base.size[1])
            sx0 = _clamp_int(wx0 - x_pad, 0, base.size[0])
            sx1 = _clamp_int(wx1 + x_pad, sx0 + 1, base.size[0])
            raw_layer_np = np.asarray(layer.convert("RGBA"), dtype=np.uint8)
            shaded_layer_np[sy0:sy1, sx0:sx1, :3] = raw_layer_np[sy0:sy1, sx0:sx1, :3]

        shaded_layer_np = shaded_layer_np.astype(np.float32)
        if structured_pattern_lower:
            alpha_soft_gate = np.where(
                soft_mask > 0.26,
                1.0,
                np.clip((soft_mask - 0.08) / 0.12, 0.0, 1.0),
            ).astype(np.float32)
        else:
            alpha_soft_gate = np.where(
                soft_mask > 0.18,
                1.0,
                np.clip((soft_mask - 0.03) / 0.15, 0.0, 1.0),
            ).astype(np.float32)
        shaded_alpha = np.clip(alpha * alpha_soft_gate, 0.0, 1.0)
        top_haze_meta: dict | None = None
        if structured_pattern_lower and not light_waistband_protected:
            shaded_alpha, top_haze_meta = _suppress_structured_lower_top_haze(
                shaded_alpha,
                warp_meta=warp_meta,
                structured_pattern_lower=structured_pattern_lower,
            )
        elif structured_pattern_lower:
            top_haze_meta = {"applied": False, "reason": "light_waistband_protected"}
            raw_layer_np = np.asarray(layer.convert("RGBA"), dtype=np.uint8)
            if light_waistband_mask is not None:
                protect = np.clip(light_waistband_mask, 0.0, 1.0)
                shaded_layer_np[:, :, :3] = np.where(
                    protect[:, :, np.newaxis] > 0.04,
                    raw_layer_np[:, :, :3].astype(np.float32),
                    shaded_layer_np[:, :, :3],
                )
                shaded_alpha = np.maximum(shaded_alpha, alpha * protect)
        upper_shape_mask_meta: dict | None = None
        upper_shape_mask_img: Image.Image | None = None
        upper_shape_mask_np: np.ndarray | None = None
        if structured_pattern_lower and not light_waistband_protected:
            upper_shape_mask_np, upper_shape_mask_meta = _build_catvton_lower_upper_shape_mask(
                np.asarray(
                    person_image.convert("RGB").resize(base.size, Image.Resampling.BILINEAR),
                    dtype=np.float32,
                ),
                np.asarray(
                    catvton_result.convert("RGB").resize(base.size, Image.Resampling.BILINEAR),
                    dtype=np.float32,
                ),
                layer_alpha=shaded_alpha,
                warp_meta=warp_meta,
                structured_pattern_lower=structured_pattern_lower,
            )
            upper_shape_mask_img = Image.fromarray(
                np.clip(upper_shape_mask_np * 255.0, 0, 255).astype(np.uint8),
                mode="L",
            )
        elif structured_pattern_lower:
            upper_shape_mask_meta = {"applied": False, "reason": "light_waistband_protected"}
        bridge_fill_meta: dict | None = None
        if structured_pattern_lower and not light_waistband_protected:
            if (
                upper_shape_mask_np is not None
                and upper_shape_mask_meta
                and upper_shape_mask_meta.get("applied")
            ):
                bridge_rgb, shaded_alpha, bridge_fill_meta = (
                    _fill_structured_lower_upper_from_shape_mask(
                        shaded_layer_np,
                        shaded_alpha,
                        upper_shape_mask_np,
                        np.asarray(
                            catvton_result.convert("RGB").resize(
                                base.size, Image.Resampling.BILINEAR
                            ),
                            dtype=np.float32,
                        ),
                        warp_meta=warp_meta,
                        structured_pattern_lower=structured_pattern_lower,
                    )
                )
                shaded_layer_np[:, :, :3] = np.clip(bridge_rgb, 0.0, 255.0)
            else:
                bridge_fill_meta = {"applied": False, "reason": "shape_mask_unavailable"}
        elif structured_pattern_lower:
            bridge_fill_meta = {"applied": False, "reason": "light_waistband_protected"}
        shaded_layer_np[:, :, 3] = np.clip(shaded_alpha * 255.0, 0.0, 255.0)
        shaded_layer = Image.fromarray(shaded_layer_np.astype(np.uint8), mode="RGBA")

        warp_result = Image.alpha_composite(base, shaded_layer).convert("RGB")
        garment_mask_np, overlay_mask_meta = _refine_lower_structure_overlay_mask(
            shaded_alpha,
            warp_meta=warp_meta,
            structured_pattern_lower=structured_pattern_lower,
        )
        raw_shape_constraint_meta: dict | None = None
        if raw_mask_image is not None and not structured_pattern_lower:
            raw_shape_mask = np.asarray(
                raw_mask_image.convert("L").resize(base.size, Image.Resampling.NEAREST),
                dtype=np.uint8,
            )
            raw_shape_binary = (raw_shape_mask > 127).astype(np.uint8)
            if raw_shape_binary.any():
                raw_shape_binary = cv2.morphologyEx(
                    raw_shape_binary,
                    cv2.MORPH_CLOSE,
                    np.ones((5, 5), dtype=np.uint8),
                    iterations=1,
                )
                raw_shape_soft = cv2.GaussianBlur(
                    raw_shape_binary.astype(np.float32),
                    (9, 9),
                    0,
                )
                raw_shape_soft = np.clip(raw_shape_soft, 0.0, 1.0)
                garment_mask_np = np.minimum(garment_mask_np, raw_shape_soft)
                raw_shape_constraint_meta = {
                    "applied": True,
                    "raw_shape_coverage": round(float(raw_shape_binary.mean()), 4),
                    "constrained_coverage": round(float((garment_mask_np > 0.08).mean()), 4),
                }
            else:
                raw_shape_constraint_meta = {"applied": False, "reason": "empty_raw_shape_mask"}
        elif raw_mask_image is not None and structured_pattern_lower:
            raw_shape_constraint_meta = {
                "applied": False,
                "reason": "structured_pattern_preserve_source_outline",
            }
        garment_mask = (garment_mask_np > 0.08).astype(np.uint8) * 255
        result, blend_meta = overlay_draping_from_ai(
            warp_result=warp_result,
            ai_result=catvton_result,
            drape_alpha=(
                float(np.clip(drape_alpha, 0.0, 0.12))
                if structured_pattern_lower
                else float(np.clip(drape_alpha, 0.0, 0.18))
            ),
            garment_mask=Image.fromarray(garment_mask, mode="L"),
            shell_scale=0.20 if structured_pattern_lower else 1.0,
            debug_session_dir=debug_session_dir,
            debug_prefix="lower_structure",
        )
        waistband_color_restore_meta: dict | None = None
        if structured_pattern_lower:
            result, waistband_color_restore_meta = _restore_structured_lower_waistband_color(
                result,
                source_layer_rgba=layer,
                warp_meta=warp_meta,
                raw_mask_image=raw_mask_image,
            )

        if debug_session_dir:
            try:
                from app.services.tryon_debug_utils import save_debug_stage_image

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename="12s_lower_structure_warp_layer.png",
                    image=shaded_layer,
                    metadata={
                        "stage": "lower_structure_warp_layer",
                        "lower_warp_qc": qc,
                        "lower_denim_like": denim_like,
                        "lower_warp_qc_accepted": qc_accepted,
                        "denim_waistband_texture_override": denim_waistband_texture_override,
                        "structured_pattern_qc_override": structured_pattern_qc_override,
                        "denim_extension": extension_meta,
                        "pattern_strength": round(float(pattern_strength), 4),
                        "strong_pattern_lower": strong_pattern_lower,
                        "structured_pattern_lower": structured_pattern_lower,
                        "alpha_coverage": round(float((shaded_alpha > 0.08).mean()), 4),
                        "light_waistband_cutout_meta": light_waistband_cutout_meta,
                        "structure_mask": mask_meta,
                        "shading_meta": shading_meta,
                        "color_unify_meta": color_unify_meta,
                        "top_haze_meta": top_haze_meta,
                        "bridge_fill_meta": bridge_fill_meta,
                        "upper_shape_mask_meta": upper_shape_mask_meta,
                        "overlay_mask_meta": overlay_mask_meta,
                        "light_waistband_meta": light_waistband_meta,
                        "waistband_color_restore_meta": waistband_color_restore_meta,
                        "raw_shape_constraint_meta": raw_shape_constraint_meta,
                        "warp_meta": {
                            "engine": warp_meta.engine,
                            "waistband_box": list(warp_meta.waistband_box),
                            "left_leg_box": list(warp_meta.left_leg_box),
                            "right_leg_box": list(warp_meta.right_leg_box),
                            "alpha_feather_px": warp_meta.alpha_feather_px,
                        },
                    },
                )
                if upper_shape_mask_img is not None and upper_shape_mask_meta is not None:
                    save_debug_stage_image(
                        debug_session_dir=debug_session_dir,
                        filename="12u_lower_upper_shape_mask.png",
                        image=upper_shape_mask_img,
                        metadata={
                            "stage": "lower_upper_shape_mask",
                            **upper_shape_mask_meta,
                        },
                    )
            except Exception as debug_err:
                logger.debug("lower structure debug save failed: %s", debug_err)

        return result, {
            "engine": "lower_structure_preserve",
            "method": "pants_structure_warp_plus_catvton_luminance_shading",
            "lower_denim_like": denim_like,
            "lower_warp_qc": qc,
            "lower_warp_qc_accepted": qc_accepted,
            "denim_waistband_texture_override": denim_waistband_texture_override,
            "structured_pattern_qc_override": structured_pattern_qc_override,
            "denim_extension": extension_meta,
            "pattern_strength": float(pattern_strength),
            "strong_pattern_lower": strong_pattern_lower,
            "structured_pattern_lower": structured_pattern_lower,
            "lower_warp_engine": warp_meta.engine,
            "light_waistband_cutout_meta": light_waistband_cutout_meta,
            "lower_warp_boxes": {
                "waistband_box": list(warp_meta.waistband_box),
                "left_leg_box": list(warp_meta.left_leg_box),
                "right_leg_box": list(warp_meta.right_leg_box),
                "alpha_feather_px": warp_meta.alpha_feather_px,
            },
            "structure_mask_meta": mask_meta,
            "shading_meta": shading_meta,
            "color_unify_meta": color_unify_meta,
            "top_haze_meta": top_haze_meta,
            "bridge_fill_meta": bridge_fill_meta,
            "upper_shape_mask_meta": upper_shape_mask_meta,
            "overlay_mask_meta": overlay_mask_meta,
            "light_waistband_meta": light_waistband_meta,
            "waistband_color_restore_meta": waistband_color_restore_meta,
            "raw_shape_constraint_meta": raw_shape_constraint_meta,
            "drape_alpha": (
                float(np.clip(drape_alpha, 0.0, 0.12))
                if structured_pattern_lower
                else float(np.clip(drape_alpha, 0.0, 0.18))
            ),
            "blend_meta": blend_meta,
            "color_fidelity": "structure_preserve",
        }
    except Exception as e:
        import traceback

        logger.warning("tryon_lower_structure_preserve failed: %s\n%s", e, traceback.format_exc())
        return catvton_result.convert("RGB").resize(person_image.size, Image.LANCZOS), {
            "engine": "lower_structure_preserve",
            "reason": str(e),
        }


def tryon_top_warp(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.009,
) -> tuple[Image.Image, WarpMetadata]:
    """Warp upper garment onto person using MediaPipe keypoints when available.

    When MediaPipe keypoints are available, uses shoulder/hip landmarks for precise
    placement and applies a perspective trapezoid warp (shoulder-width at top,
    hip-width at bottom) to simulate the garment conforming to the body silhouette.
    Falls back to gradient energy estimation if keypoints are unavailable.
    """
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    g = cutout.cropped.convert("RGBA")
    gw, gh = g.size
    if gw < 16 or gh < 16:
        raise ValueError("garment too small for top warp")

    # ── SCHP 人体解析优先路径（更精确的衣物边界）──────────────────────────
    _used_pose = False
    _shoulder_w_px: int | None = None
    _hip_w_px: int | None = None
    _schp_result = None
    kpts = None

    try:
        from app.services.human_parsing import schp_parse

        _schp_result = schp_parse(person_image)
        if _schp_result and _schp_result.source != "heuristic_grabcut":
            # Use SCHP parsing for precise body bounds
            top_mask = _schp_result.top_region()
            # Find bounding box of upper body region
            rows = np.where(top_mask.max(axis=1) > 0.3)[0]
            cols = np.where(top_mask.max(axis=0) > 0.3)[0]
            if len(rows) > 10 and len(cols) > 10:
                x0 = int(cols[0])
                x1 = int(cols[-1])
                y_top = int(rows[0])
                y_bottom = int(rows[-1])
                neck_y = _clamp_int(
                    int(y_top + (y_bottom - y_top) * 0.15),
                    int(ph * 0.12),
                    int(ph * 0.32),
                )
                waist_y = _clamp_int(
                    int(y_top + (y_bottom - y_top) * 0.70),
                    int(ph * 0.45),
                    int(ph * 0.82),
                )
                _shoulder_w_px = max(2, x1 - x0)
                _hip_w_px = max(2, int(_shoulder_w_px * 0.85))
                _used_pose = True
                logger.info(
                    "[SCHP] Using SCHP body bounds: x0=%d, x1=%d, neck_y=%d, waist_y=%d",
                    x0,
                    x1,
                    neck_y,
                    waist_y,
                )
    except Exception as schp_err:
        logger.debug("[SCHP] SCHP parsing unavailable, falling back to MediaPipe: %s", schp_err)

    # ── MediaPipe fallback 路径 ──────────────────────────────────────────────
    if not _used_pose:
        kpts = detect_pose_keypoints(person_image)
        if kpts:
            bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "top")
            if bounds.get("valid"):
                x0 = bounds["x0"]
                x1 = bounds["x1"]
                neck_y = bounds["neck_y"]
                waist_y = bounds["waist_y"]
                _shoulder_w_px = max(2, int(bounds.get("shoulder_width", x1 - x0)))
                _hip_w_px = max(2, int(bounds.get("hip_width", (x1 - x0) * 0.85)))
                _used_pose = True

    if not _used_pose:
        # ── 梯度能量 fallback ────────────────────────────────────────────────
        gray = np.asarray(person_image.convert("L"), dtype=np.float32)
        fg = _person_foreground_mask(person_image)
        b = None
        if fg is not None:
            b = _bounds_from_mask(fg, y0=int(ph * 0.06), y1=int(ph * 0.74), col_q=0.72, row_q=0.55)
        if b is not None:
            x0, x1, y_top, y_bottom = b
            span = max(2, int(y_bottom - y_top))
            neck_y = _clamp_int(int(y_top + span * 0.18), int(ph * 0.12), int(ph * 0.32))
            waist_y = _clamp_int(int(y_top + span * 0.70), int(ph * 0.45), int(ph * 0.82))
        else:
            x0, x1, neck_y, waist_y = _estimate_upper_body_bounds(gray)
        # Stabilize horizontal center.
        mid = (x0 + x1) // 2
        center = pw // 2
        drift = int(mid - center)
        if abs(drift) > int(pw * 0.12):
            shift = int(-0.65 * drift)
            bw = x1 - x0
            x0 = _clamp_int(x0 + shift, 0, pw - 2)
            x1 = _clamp_int(x0 + bw, x0 + 2, pw)
        pad_x = int((x1 - x0) * 0.03)
        x0 = _clamp_int(x0 - pad_x, 0, pw - 2)
        x1 = _clamp_int(x1 + pad_x, x0 + 2, pw)

    # Force garment top below face/chin.
    y0 = _clamp_int(int(neck_y + ph * 0.02), int(ph * 0.12), int(ph * 0.42))
    y1 = _clamp_int(int(waist_y + ph * 0.03), y0 + 2, int(ph * 0.86))
    tw = max(2, x1 - x0)
    th = max(2, y1 - y0)

    # Scale garment to FIT the target area (preserve aspect ratio, no stretching).
    # Use shoulder width as primary constraint for realistic proportions.
    if _used_pose and _shoulder_w_px:
        # Scale based on shoulder width with small margin
        target_w = int(_shoulder_w_px * 1.05)
        scale = target_w / float(gw)
        # Ensure garment doesn't exceed target area height
        if int(gh * scale) > th * 1.2:
            scale = th * 1.2 / float(gh)
    else:
        # Fallback: FIT scaling (not COVER) to avoid stretching
        scale = min(tw / float(gw), th / float(gh))
    itw = max(2, int(gw * scale))
    ith = max(2, int(gh * scale))
    g = g.resize((itw, ith), Image.Resampling.LANCZOS)

    # ── TPS 变形（身体关键点驱动，模拟 3D 贴合感）──────────────────────
    if _used_pose and _shoulder_w_px and itw >= 16:
        try:
            from app.services.cloth_warp import TPSWarpEngine

            tps_engine = TPSWarpEngine()
            # Build keypoints dict for TPS from MediaPipe keypoints (normalized 0-1)
            tps_keypoints = {}
            if kpts:
                for name in (
                    "left_shoulder",
                    "right_shoulder",
                    "left_hip",
                    "right_hip",
                    "left_elbow",
                    "right_elbow",
                ):
                    if name in kpts:
                        tps_keypoints[name] = kpts[name]
            if len(tps_keypoints) >= 4:
                g_rgb = g.convert("RGB")
                g_warped = tps_engine.warp(g_rgb, tps_keypoints, (itw, ith), cloth_type="upper")
                g = g_warped.convert("RGBA")
                if g.mode != "RGBA":
                    # Restore alpha from original
                    g.putalpha(g.split()[3] if len(g.split()) > 3 else 255)
                logger.info("[TPS] Applied TPS warp with %d keypoints", len(tps_keypoints))
        except Exception as tps_err:
            logger.warning("[TPS] TPS warp failed, using fallback quad: %s", tps_err)
            # Fallback to PIL QUAD transform
            if _shoulder_w_px and _hip_w_px:
                top_half_w = _clamp_int(int(min(itw, _shoulder_w_px * scale)), 4, itw)
                bot_half_w = _clamp_int(int(min(itw, _hip_w_px * scale)), 4, itw)
                if abs(top_half_w - bot_half_w) > 4:
                    top_inset = (itw - top_half_w) // 2
                    bot_inset = (itw - bot_half_w) // 2
                    quad = (
                        top_inset,
                        0,
                        itw - top_inset,
                        0,
                        itw - bot_inset,
                        ith,
                        bot_inset,
                        ith,
                    )
                    g = _pil_quad_warp(g, (itw, ith), quad)

    # ── Center the scaled garment on the target box ──────────────────────────
    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ox = x0 + (tw - min(itw, tw)) // 2
    oy = y0 + (th - min(ith, th)) // 2
    g_crop = g.crop((0, 0, min(itw, tw), min(ith, th)))
    layer.paste(g_crop, (ox, oy), g_crop)

    # ── Feather edges for smoother boundary ────────────────────────────────
    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 8)
    layer = _feather_alpha(layer, radius_px=feather_px)

    # ── Protect face/neck area from being overwritten ───────────────────────
    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.18))
    r, gg, b, a = layer.split()
    a = ImageChops.multiply(a, protect)
    layer = Image.merge("RGBA", (r, gg, b, a))

    # ── Realism pass: LAB brightness transfer + fold lines + edge darkening ──
    # For patterns (checkered/striped), we skip the LAB transfer but still apply
    # fold lines + edge darkening since those are boundary-only effects (harmless).
    _pattern_strength = _detect_pattern_strength(g)
    _skip_lab_transfer = _pattern_strength > 0.35  # Raised threshold to preserve more colors
    _skip_fold_lines = _pattern_strength > 0.50  # Also skip fold lines for high-contrast patterns
    _skip_edge_darken = _pattern_strength > 0.45  # Skip edge darkening for patterns

    if not _skip_lab_transfer or not _skip_fold_lines or not _skip_edge_darken:
        try:
            layer_np = np.array(layer)

            # ── LAB brightness transfer (only for SOLID-COLOR garments) ───────────
            # PRESERVE WHITE GARMENTS: White clothes (L_mean > 220) must NOT undergo
            # LAB transfer. The human torso is 10-30x darker than white fabric, so
            # blending body brightness into white produces a dark gray/brown "shadow"
            # that looks completely wrong (white → gray → brown visually).
            #
            # Detection: garments with L_mean > 220 are essentially white / near-white.
            # Saturation check as secondary guard: low-saturation + high-brightness = white.
            # Pattern check as tertiary guard: already handled by _skip_lab_transfer.
            #
            # The pattern detector (_detect_pattern_strength) handles colorful patterns.
            # This fix handles the white garment case separately and more aggressively.
            if not _skip_lab_transfer:
                base_np = np.array(base)
                body_roi = base_np[y0:y1, x0:x1]
                gar_roi = layer_np[y0:y1, x0:x1, :3]
                fg_mask = layer_np[y0:y1, x0:x1, 3] > 200

                if body_roi.size > 0 and fg_mask.sum() > 0:
                    body_lab = cv2.cvtColor(body_roi.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(
                        np.float32
                    )
                    body_L_mean = body_lab[:, :, 0].mean()

                    gar_lab = cv2.cvtColor(gar_roi.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(
                        np.float32
                    )

                    gar_L_roi = gar_lab[:, :, 0][fg_mask]
                    if len(gar_L_roi) > 0:
                        gar_L_mean = float(gar_L_roi.mean())

                        # ── CRITICAL: skip LAB for white/near-white garments ──────────
                        # White fabric: L_mean ≈ 230-255. Body torso: L_mean ≈ 35-60.
                        # With blend_ratio=0.50, white gets darkened to ~L140 (brownish).
                        # Fix: detect white garments (L > 220) and skip entirely.
                        if gar_L_mean > 220:
                            # Pure white / near-white garment — no brightness transfer.
                            # White stays white; any body shadow comes from edge_darken.
                            pass
                        elif gar_L_mean > 2.0:
                            # Moderate-brightness garment — gentle LAB transfer.
                            blend_ratio = 0.20  # Much gentler: preserve 80% of original brightness
                            L_scale = (
                                body_L_mean * blend_ratio + (1 - blend_ratio) * gar_L_mean
                            ) / gar_L_mean
                            L_scale = np.clip(L_scale, 0.85, 1.15)
                            gar_lab[:, :, 0] = np.clip(gar_lab[:, :, 0] * L_scale, 0, 255)
                            gar_rgb = cv2.cvtColor(gar_lab.astype(np.uint8), cv2.COLOR_LAB2RGB)
                            roi_region = layer_np[y0:y1, x0:x1]
                            roi_region[fg_mask] = gar_rgb[fg_mask]
                            layer_np[y0:y1, x0:x1] = roi_region

            _is_white_garment = False
            if not _skip_lab_transfer and gar_roi.size > 0 and fg_mask.sum() > 0:
                gar_lab_check = cv2.cvtColor(gar_roi.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(
                    np.float32
                )
                gar_L_check = gar_lab_check[:, :, 0][fg_mask]
                if len(gar_L_check) > 0 and float(gar_L_check.mean()) > 220:
                    _is_white_garment = True

            # ── Fold lines: subtle vertical darkening for drape illusion ───────────
            # Only apply for solid-color garments, skip for patterns
            if not _skip_fold_lines and not _is_white_garment:
                fold_positions = [int(itw * 0.33), int(itw * 0.67)]
                fold_strength = 0.04  # Reduced from 0.06
                for fx in fold_positions:
                    abs_x = ox + min(fx, tw - 1)
                    if 0 < abs_x < pw - 1:
                        fade = max(0, 1.0 - abs(fx - itw / 2) / (itw * 0.25)) * fold_strength
                        if fade > 0.005:
                            region = layer_np[oy : oy + th, max(0, abs_x - 1) : abs_x + 1]
                            if region.size > 0:
                                alpha_aware = region[:, :, 3:4].astype(float) / 255.0
                                darken = (1.0 - fade) * alpha_aware
                                region[:, :, :3] = np.clip(
                                    region[:, :, :3].astype(float) * darken, 0, 255
                                ).astype(np.uint8)

            # ── Edge darkening: simulate cast shadow from garment onto body ────────
            # Only apply for solid-color garments
            if not _skip_edge_darken and not _is_white_garment:
                edge_px = max(2, int(feather_px * 1.5))
                for dx in range(-edge_px, edge_px + 1):
                    for dy in range(-edge_px, edge_px + 1):
                        abs_x = ox + dx
                        abs_y = oy + dy
                        if 0 <= abs_x < pw and 0 <= abs_y < ph:
                            alpha_at = layer_np[abs_y, abs_x, 3]
                            if 10 < alpha_at < 245:
                                edge_dist = max(abs(dx), abs(dy))
                                falloff = (
                                    max(0, 1.0 - edge_dist / float(edge_px)) * 0.08
                                )  # Reduced from 0.12
                                if falloff > 0.005:
                                    layer_np[abs_y, abs_x, :3] = np.clip(
                                        layer_np[abs_y, abs_x, :3].astype(float) * (1.0 - falloff),
                                        0,
                                        255,
                                    ).astype(np.uint8)

            layer = Image.fromarray(layer_np, mode="RGBA")
        except Exception:
            pass  # If realism pass fails, keep original layer intact

    out = Image.alpha_composite(base, layer).convert("RGB")
    engine_tag = "top_warp_v2_pose" if _used_pose else "top_warp_v1_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=(x0, y0, x1, y0 + max(2, int((y1 - y0) * 0.18))),
        left_leg_box=(x0, y0 + max(2, int((y1 - y0) * 0.18)), (x0 + x1) // 2, y1),
        right_leg_box=((x0 + x1) // 2, y0 + max(2, int((y1 - y0) * 0.18)), x1, y1),
        alpha_feather_px=feather_px,
    )
    return out, meta


def tryon_skirt_warp(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.012,
    warp_strength: float = 0.6,
) -> tuple[Image.Image, WarpMetadata]:
    """
    Warp skirt/dress onto person using MediaPipe keypoints when available.

    When MediaPipe keypoints are available, uses hip landmarks for precise
    skirt placement and applies a trapezoid warp (wider at hem, narrower at waist)
    to simulate the skirt conforming to the body silhouette.
    Falls back to gradient energy estimation if keypoints are unavailable.

    warp_strength (0.0-1.0): Controls trapezoid deformation intensity.
    - 0.0: No trapezoid warp (pure rectangular fit, minimal distortion)
    - 0.6: Moderate A-line effect (default, good for most skirts)
    - 1.0: Full trapezoid warp (strong A-line, may distort patterns)
    """
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    g = cutout.cropped.convert("RGBA")
    gw, gh = g.size
    if gw < 16 or gh < 16:
        raise ValueError("garment too small for skirt warp")

    # Clamp warp_strength to valid range
    warp_strength = float(max(0.0, min(1.0, warp_strength)))

    # ── MediaPipe 优先路径 ──────────────────────────────────────────────────
    kpts = detect_pose_keypoints(person_image)
    _used_pose = False

    if kpts:
        bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "bottom")
        if bounds.get("valid"):
            x0 = bounds["x0"]
            x1 = bounds["x1"]
            waist_y = bounds.get("waist_y", int(ph * 0.40))
            ankle_y = bounds.get("ankle_y", int(ph * 0.90))
            _ = bounds.get("hip_width", x1 - x0)  # available for future use
            _used_pose = True

    if not _used_pose:
        # ── 梯度能量 fallback ────────────────────────────────────────────────
        gray = np.asarray(person_image.convert("L"), dtype=np.float32)
        fg = _person_foreground_mask(person_image)
        b = None
        if fg is not None:
            b = _bounds_from_mask(fg, y0=int(ph * 0.28), y1=int(ph * 0.98), col_q=0.70, row_q=0.55)
        if b is not None:
            x0, x1, y_top, y_bottom = b
            waist_y = _clamp_int(
                int(y_top + (y_bottom - y_top) * 0.15), int(ph * 0.32), int(ph * 0.58)
            )
            ankle_y = _clamp_int(y_bottom, int(ph * 0.75), int(ph * 0.98))
        else:
            x0, x1, waist_y, ankle_y = _estimate_lower_body_bounds(gray)

        # Stabilize horizontal center
        mid = (x0 + x1) // 2
        center = pw // 2
        drift = int(mid - center)
        if abs(drift) > int(pw * 0.12):
            shift = int(-0.65 * drift)
            bw = x1 - x0
            x0 = _clamp_int(x0 + shift, 0, pw - 2)
            x1 = _clamp_int(x0 + bw, x0 + 2, pw)

    # Add horizontal padding for skirt width (skirts typically wider than pants)
    pad_x = int((x1 - x0) * 0.08)
    x0 = _clamp_int(x0 - pad_x, 0, pw - 2)
    x1 = _clamp_int(x1 + pad_x, x0 + 2, pw)

    y0 = _clamp_int(int(waist_y - ph * 0.06), int(ph * 0.22), int(ph * 0.70))
    y1 = _clamp_int(int(ankle_y), y0 + 2, ph)
    tw = max(2, x1 - x0)
    th = max(2, y1 - y0)

    # Scale garment: cover target box width, preserve aspect ratio (crop height if needed)
    # This prevents the "garment too small" issue that plagued v1.
    scale = tw / float(gw)
    ith = max(2, int(gh * scale))
    g_scaled = g.resize((tw, ith), Image.Resampling.LANCZOS)

    # Apply trapezoid warp for A-line skirt effect (narrower at waist, wider at hem)
    # warp_strength controls deformation intensity (0.0 = none, 1.0 = full)
    # With strength=0.6, we use 60% of the normal trapezoid difference.
    if tw >= 16 and th >= 16:
        # Base trapezoid: waist 42% of width, hem 50% of width
        base_waist_ratio = 0.42
        base_hem_ratio = 0.50
        waist_ratio = base_waist_ratio - (base_waist_ratio - 0.48) * warp_strength * 0.5
        hem_ratio = base_hem_ratio + (0.55 - base_hem_ratio) * warp_strength

        waist_half_w = _clamp_int(int(tw * waist_ratio), 4, tw // 2)
        hem_half_w = _clamp_int(int(tw * hem_ratio), waist_half_w + 2, tw // 2)

        if abs(hem_half_w - waist_half_w) > 4:
            top_inset = tw // 2 - waist_half_w
            bot_inset = tw // 2 - hem_half_w
            quad = (
                top_inset,
                0,
                tw - top_inset,
                0,
                tw - bot_inset,
                ith,
                bot_inset,
                ith,
            )
            g_scaled = _pil_quad_warp(g_scaled, (tw, ith), quad)
            logger.debug(
                f"[tryon_skirt_warp] trapezoid applied: waist={waist_half_w}px "
                f"hem={hem_half_w}px strength={warp_strength}"
            )

    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    # Center the scaled garment vertically in the target box
    oy = y0 + (th - min(ith, th)) // 2
    paste_y = max(y0, min(oy, y1 - 2))
    g_crop = g_scaled.crop((0, 0, min(tw, tw), min(ith, y1 - paste_y)))
    layer.paste(g_crop, (x0, paste_y), g_crop)

    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 12)
    layer = _feather_alpha(layer, radius_px=feather_px)

    # Protect upper body (skirt starts at waist, protect above hip level)
    protect = _upper_protect_mask((pw, ph), protect_until_y=int(waist_y - ph * 0.08))
    r, gg, b, a = layer.split()
    a = ImageChops.multiply(a, protect)
    layer = Image.merge("RGBA", (r, gg, b, a))

    out = Image.alpha_composite(base, layer).convert("RGB")
    engine_tag = "skirt_warp_v3_pose" if _used_pose else "skirt_warp_v3_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=(x0, y0, x1, y0 + max(2, int((y1 - y0) * 0.15))),
        left_leg_box=(x0, y0, (x0 + x1) // 2, y1),
        right_leg_box=((x0 + x1) // 2, y0, x1, y1),
        alpha_feather_px=feather_px,
    )
    return out, meta


def tryon_top_warp_preserve(
    person_image: Image.Image,
    garment_image: Image.Image,
) -> tuple[Image.Image, WarpMetadata]:
    """Warp upper garment onto person WITHOUT the realism pass (pure pixel-preserving).

    Use this when you need 100% garment pixel fidelity and will handle
    background realism separately (e.g. via overlay_draping_from_ai).

    Returns:
        (result_rgb, metadata)
    """
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    g = cutout.cropped.convert("RGBA")
    gw, gh = g.size
    if gw < 16 or gh < 16:
        raise ValueError("garment too small for top warp preserve")

    kpts = detect_pose_keypoints(person_image)
    _used_pose = False

    if kpts:
        bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "top")
        if bounds.get("valid"):
            x0 = bounds["x0"]
            x1 = bounds["x1"]
            neck_y = bounds["neck_y"]
            waist_y = bounds["waist_y"]
            _used_pose = True

    if not _used_pose:
        gray = np.asarray(person_image.convert("L"), dtype=np.float32)
        fg = _person_foreground_mask(person_image)
        b = None
        if fg is not None:
            b = _bounds_from_mask(fg, y0=int(ph * 0.06), y1=int(ph * 0.74), col_q=0.72, row_q=0.55)
        if b is not None:
            x0, x1, y_top, y_bottom = b
            span = max(2, int(y_bottom - y_top))
            neck_y = _clamp_int(int(y_top + span * 0.18), int(ph * 0.12), int(ph * 0.32))
            waist_y = _clamp_int(int(y_top + span * 0.70), int(ph * 0.45), int(ph * 0.82))
        else:
            x0, x1, neck_y, waist_y = _estimate_upper_body_bounds(gray)
        mid = (x0 + x1) // 2
        center = pw // 2
        drift = int(mid - center)
        if abs(drift) > int(pw * 0.12):
            shift = int(-0.65 * drift)
            bw = x1 - x0
            x0 = _clamp_int(x0 + shift, 0, pw - 2)
            x1 = _clamp_int(x0 + bw, x0 + 2, pw)
        pad_x = int((x1 - x0) * 0.03)
        x0 = _clamp_int(x0 - pad_x, 0, pw - 2)
        x1 = _clamp_int(x1 + pad_x, x0 + 2, pw)

    y0 = _clamp_int(int(neck_y + ph * 0.02), int(ph * 0.12), int(ph * 0.42))
    y1 = _clamp_int(int(waist_y + ph * 0.03), y0 + 2, int(ph * 0.86))
    tw = max(2, x1 - x0)
    th = max(2, y1 - y0)

    scale = max(tw / float(gw), th / float(gh))
    itw = max(2, int(gw * scale))
    ith = max(2, int(gh * scale))
    g = g.resize((itw, ith), Image.Resampling.LANCZOS)

    if _used_pose:
        from app.services.tryon_v2.pose_utils import get_body_bounds_from_keypoints as _gbk

        kpts2 = detect_pose_keypoints(person_image)
        if kpts2:
            bounds2 = _gbk(kpts2, pw, ph, "top")
            if bounds2.get("valid"):
                shoulder_w = max(2, int(bounds2.get("shoulder_width", tw)))
                hip_w = max(2, int(bounds2.get("hip_width", tw * 0.85)))
                if itw >= 16:
                    top_half_w = _clamp_int(int(min(itw, shoulder_w * scale)), 4, itw)
                    bot_half_w = _clamp_int(int(min(itw, hip_w * scale)), 4, itw)
                    if abs(top_half_w - bot_half_w) > 4:
                        top_inset = (itw - top_half_w) // 2
                        bot_inset = (itw - bot_half_w) // 2
                        quad = (
                            top_inset,
                            0,
                            itw - top_inset,
                            0,
                            itw - bot_inset,
                            ith,
                            bot_inset,
                            ith,
                        )
                        g = _pil_quad_warp(g, (itw, ith), quad)

    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ox = x0 + (tw - min(itw, tw)) // 2
    oy = y0 + (th - min(ith, th)) // 2
    g_crop = g.crop((0, 0, min(itw, tw), min(ith, th)))
    layer.paste(g_crop, (ox, oy), g_crop)

    feather_px = _clamp_int(int(max(pw, ph) * 0.009), 1, 8)
    layer = _feather_alpha(layer, radius_px=feather_px)

    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.18))
    r, gg, b, a = layer.split()
    a = ImageChops.multiply(a, protect)
    layer = Image.merge("RGBA", (r, gg, b, a))

    out = Image.alpha_composite(base, layer).convert("RGB")
    engine_tag = "top_warp_preserve_pose" if _used_pose else "top_warp_preserve_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=(x0, y0, x1, y0 + max(2, int((y1 - y0) * 0.18))),
        left_leg_box=(x0, y0 + max(2, int((y1 - y0) * 0.18)), (x0 + x1) // 2, y1),
        right_leg_box=((x0 + x1) // 2, y0 + max(2, int((y1 - y0) * 0.18)), x1, y1),
        alpha_feather_px=feather_px,
    )
    return out, meta


def overlay_draping_from_ai(
    warp_result: Image.Image,
    ai_result: Image.Image,
    *,
    drape_alpha: float = 0.60,
    garment_mask: Image.Image | np.ndarray | None = None,
    shell_scale: float = 1.0,
    debug_session_dir: str | None = None,
    debug_prefix: str = "hybrid",
) -> tuple[Image.Image, dict]:
    """Blend AI-generated drape/lighting onto a warp result, preserving exact garment pixels.

    Strategy:
    1. Detect garment region in warp_result via foreground mask.
    2. For the body/background area OUTSIDE the garment, transfer realistic lighting
       and texture from ai_result (e.g. shadow under garment, body form, ambient light).
    3. Inside garment region: garment pixels are 100% preserved from warp_result.
    4. Blend at garment boundary for smooth transitions.

    This gives you:
    - 100% garment pixel fidelity (colors, patterns, textures from original garment photo)
    - Realistic drape/shadow/lighting from the AI-generated result

    Args:
        warp_result: Warp output (garment faithfully pasted onto person).
        ai_result: AI-generated try-on result (realistic fit/shadow but garment may differ).
        drape_alpha: 0.0-1.0 how much AI realism to blend in (0.60 = 60% AI, 40% warp bg).

    Returns:
        (result_image, metadata_dict)
    """
    try:
        w, h = warp_result.size
        warp_rgb = np.array(warp_result.convert("RGB"), dtype=np.float32)
        # AI result may have different dimensions — resize to match warp result
        ai_resized = ai_result.convert("RGB").resize((w, h), Image.LANCZOS)
        ai_rgb = np.array(ai_resized, dtype=np.float32)

        if debug_session_dir:
            try:
                from app.services.tryon_debug_utils import save_debug_stage_image

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename=f"{debug_prefix}_12_ai_resized_to_warp.jpg",
                    image=ai_resized,
                    metadata={
                        "stage": "hybrid_ai_resized_to_warp",
                        "source_size": list(ai_result.size),
                        "target_size": [w, h],
                    },
                )
            except Exception as debug_err:
                logger.debug("overlay_draping debug save failed: %s", debug_err)

        # ── Step 1: Find garment-preserve region ──────────────────────────────────
        # Prefer the actual warped garment mask. Falling back to a person foreground
        # mask makes the whole body/background participate in blending, which reads
        # as a cut-and-paste overlay when CatVTON is weak for lower garments.
        if garment_mask is not None:
            if isinstance(garment_mask, Image.Image):
                mask_img = garment_mask.convert("L").resize((w, h), Image.NEAREST)
                fg_warp = np.asarray(mask_img, dtype=np.uint8) > 20
            else:
                fg_warp = np.asarray(garment_mask) > 0
                if fg_warp.shape[:2] != (h, w):
                    mask_img = Image.fromarray((fg_warp.astype(np.uint8) * 255), mode="L")
                    fg_warp = (
                        np.asarray(mask_img.resize((w, h), Image.NEAREST), dtype=np.uint8) > 20
                    )
        else:
            fg_warp = _person_foreground_mask(warp_result)

        if fg_warp is None:
            # Fallback: garment occupies center body area
            fg_warp = np.zeros((h, w), dtype=bool)
            fg_warp[int(h * 0.08) : int(h * 0.85), int(w * 0.18) : int(w * 0.82)] = True

        # Garment bounding box (from foreground)
        rows = np.any(fg_warp, axis=1)
        cols = np.any(fg_warp, axis=0)
        if not rows.any() or not cols.any():
            return warp_result, {"engine": "overlay_draping", "reason": "no_fg_mask"}

        g_y0 = int(np.where(rows)[0][0])
        g_y1 = int(np.where(rows)[0][-1])
        g_x0 = int(np.where(cols)[0][0])
        g_x1 = int(np.where(cols)[0][-1])

        # Expand region for smooth blending (used below)
        expand = max(4, int(min(w, h) * 0.015))

        # ── Step 2: Build garment mask ─────────────────────────────────────────────
        # Inside g_x0:g_x1, g_y0:g_y1 = garment pixels from warp
        # Outside = background/body (can be blended with AI)
        garment_mask = fg_warp.copy().astype(np.float32)

        # Feather garment edge so blending is smooth. Localize CatVTON blending to
        # a shell around the garment; do not globally repaint the person/background.
        try:
            kernel = np.ones((expand * 2 + 1, expand * 2 + 1), np.uint8)
            shell_scale_clipped = float(np.clip(shell_scale, 0.20, 1.0))
            if shell_scale_clipped < 0.50:
                shell_radius = max(3, int(min(w, h) * 0.010 * shell_scale_clipped * 3.0))
            else:
                shell_radius = max(
                    expand * 2,
                    int(min(w, h) * 0.045 * shell_scale_clipped),
                )
            shell_kernel = np.ones((shell_radius * 2 + 1, shell_radius * 2 + 1), np.uint8)
            gar_mask_u8 = (garment_mask * 255).astype(np.uint8)
            preserve_u8 = cv2.erode(gar_mask_u8, kernel, iterations=1)
            near_u8 = cv2.dilate(gar_mask_u8, shell_kernel, iterations=1)
            preserve_f = preserve_u8.astype(np.float32) / 255.0
            near_f = near_u8.astype(np.float32) / 255.0
            blend_weight = near_f * (1.0 - preserve_f) * drape_alpha
        except Exception:
            blend_weight = np.zeros((h, w), dtype=np.float32)

        # ── Step 3: Blend background/lighting from AI ───────────────────────────────
        # result = warp * (1 - blend_weight) + ai * blend_weight
        # But ONLY blend where AI is "more realistic" — body area, not garment interior
        result = np.zeros_like(warp_rgb)
        for c in range(3):
            result[:, :, c] = (
                warp_rgb[:, :, c] * (1.0 - blend_weight) + ai_rgb[:, :, c] * blend_weight
            )
        result = np.clip(result, 0, 255).astype(np.uint8)

        # ── Step 4: Restore garment pixels 100% from warp ──────────────────────────
        gar_region = fg_warp[g_y0:g_y1, g_x0:g_x1]
        result[g_y0:g_y1, g_x0:g_x1][gar_region] = warp_rgb[g_y0:g_y1, g_x0:g_x1][gar_region]

        out_img = Image.fromarray(result, mode="RGB")

        if debug_session_dir:
            try:
                from app.services.tryon_debug_utils import save_debug_stage_image

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename=f"{debug_prefix}_13_overlay_foreground_mask.png",
                    image=Image.fromarray((fg_warp.astype(np.uint8) * 255), mode="L"),
                    metadata={
                        "stage": "hybrid_overlay_foreground_mask",
                        "note": (
                            "White pixels are treated as garment-preserve area by "
                            "overlay_draping_from_ai."
                        ),
                        "garment_region": {
                            "x0": g_x0,
                            "y0": g_y0,
                            "x1": g_x1,
                            "y1": g_y1,
                        },
                        "coverage": round(float(fg_warp.mean()), 4),
                    },
                )
                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename=f"{debug_prefix}_14_overlay_blend_weight.png",
                    image=Image.fromarray(
                        np.clip(blend_weight * 255.0, 0, 255).astype(np.uint8),
                        mode="L",
                    ),
                    metadata={
                        "stage": "hybrid_overlay_blend_weight",
                        "drape_alpha": drape_alpha,
                        "shell_scale": shell_scale,
                        "max": round(float(blend_weight.max()), 4),
                        "mean": round(float(blend_weight.mean()), 4),
                    },
                )
                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename=f"{debug_prefix}_15_overlay_result.jpg",
                    image=out_img,
                    metadata={
                        "stage": "hybrid_overlay_result",
                        "drape_alpha": drape_alpha,
                    },
                )
            except Exception as debug_err:
                logger.debug("overlay_draping debug save failed: %s", debug_err)

        logger.info(
            "overlay_draping: warp=%dx%d ai=%dx%d region=[%d,%d,%d,%d] alpha=%.2f",
            w,
            h,
            ai_result.size[0],
            ai_result.size[1],
            g_x0,
            g_y0,
            g_x1,
            g_y1,
            drape_alpha,
        )
        return out_img, {
            "engine": "overlay_draping",
            "garment_region": {
                "x0": g_x0,
                "y0": g_y0,
                "x1": g_x1,
                "y1": g_y1,
            },
            "drape_alpha": drape_alpha,
            "shell_scale": shell_scale,
        }

    except Exception as e:
        import traceback

        logger.warning("overlay_draping_from_ai failed: %s\n%s", e, traceback.format_exc())
        return warp_result, {"engine": "overlay_draping", "reason": str(e)}


def _warp_changed_region_mask(
    person_image: Image.Image,
    warp_result: Image.Image,
    *,
    threshold: int = 18,
    restrict_boxes: list[tuple[int, int, int, int]] | None = None,
) -> Image.Image:
    """Return pixels introduced by the warp stage.

    Foreground segmentation on the warp result tends to return the whole person.
    For hybrid blending we need the actual pasted garment pixels, so derive them
    from the difference between the original person image and the warp output.
    """
    w, h = warp_result.size
    person_rgb = np.asarray(
        person_image.convert("RGB").resize((w, h), Image.BICUBIC), dtype=np.int16
    )
    warp_rgb = np.asarray(warp_result.convert("RGB"), dtype=np.int16)
    diff = np.max(np.abs(warp_rgb - person_rgb), axis=2).astype(np.uint8)
    mask_u8 = (diff > int(threshold)).astype(np.uint8) * 255

    if restrict_boxes:
        allowed = np.zeros((h, w), dtype=np.uint8)
        pad = max(4, int(min(w, h) * 0.01))
        for x0, y0, x1, y1 in restrict_boxes:
            bx0 = _clamp_int(int(x0) - pad, 0, w - 1)
            by0 = _clamp_int(int(y0) - pad, 0, h - 1)
            bx1 = _clamp_int(int(x1) + pad, bx0 + 1, w)
            by1 = _clamp_int(int(y1) + pad, by0 + 1, h)
            allowed[by0:by1, bx0:bx1] = 255
        mask_u8 = cv2.bitwise_and(mask_u8, allowed)

    try:
        kernel = np.ones((5, 5), np.uint8)
        mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel, iterations=1)
        mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask_u8 = cv2.dilate(mask_u8, kernel, iterations=1)
    except Exception:
        pass

    return Image.fromarray(mask_u8, mode="L")


def overlay_top_onto_ai_result(
    ai_result: Image.Image,
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    garment_alpha: float = 0.90,
) -> tuple[Image.Image, dict]:
    """Replace garment in AI try-on result with pixel-perfect original garment.

    Strategy (all in AI result's coordinate system):
    1. Detect pose on AI result to get accurate garment region coordinates.
    2. Scale original garment to cover region, preserving aspect ratio.
    3. Absolute alpha blend: garment * garment_alpha + ai * (1 - garment_alpha).
    4. Face/neck protected.

    Args:
        ai_result: AI-generated try-on result (realistic fit but garment may differ)
        person_image: Original person image (used for pose as fallback)
        garment_image: Original garment product photo
        garment_alpha: 0.0-1.0, how much original garment to use (0.90 = 90% original)

    Returns:
        (result_image, metadata_dict)
    """
    try:
        ai_w, ai_h = ai_result.size
        ai_rgb = np.array(ai_result.convert("RGB"), dtype=np.float32)

        # Try pose detection on AI result first (accurate garment location)
        kpts = None
        body_valid = False
        try:
            kpts = detect_pose_keypoints(ai_result)
        except Exception:
            pass

        if kpts:
            bounds = get_body_bounds_from_keypoints(kpts, ai_w, ai_h, "top")
            if bounds.get("valid"):
                bx0, bx1 = int(bounds["x0"]), int(bounds["x1"])
                neck_y = int(bounds["neck_y"])
                waist_y = int(bounds["waist_y"])
                body_valid = True

        # Fallback: foreground mask on AI result
        if not body_valid:
            fg = _person_foreground_mask(ai_result)
            if fg is not None:
                rows = np.any(fg, axis=1)
                cols = np.any(fg, axis=0)
                if rows.any() and cols.any():
                    y_top = int(np.where(rows)[0][0])
                    y_bot = int(np.where(rows)[0][-1])
                    x_lft = int(np.where(cols)[0][0])
                    x_rgt = int(np.where(cols)[0][-1])
                    bx0 = max(0, int(x_lft - ai_w * 0.03))
                    bx1 = min(ai_w, int(x_rgt + ai_w * 0.03))
                    body_span = y_bot - y_top
                    neck_y = y_top + int(body_span * 0.18)
                    waist_y = y_top + int(body_span * 0.52)
                    body_valid = True

        # Absolute fallback: fraction of AI result
        if not body_valid:
            bx0, bx1 = int(ai_w * 0.20), int(ai_w * 0.80)
            neck_y = int(ai_h * 0.15)
            waist_y = int(ai_h * 0.50)

        # Garment region: neck to waist on AI result
        y0 = max(0, min(int(neck_y - ai_h * 0.02), int(ai_h * 0.40)))
        y1 = max(y0 + 2, min(int(waist_y + ai_h * 0.06), int(ai_h * 0.72)))
        region_w = bx1 - bx0
        region_h = y1 - y0

        # Garment natural aspect ratio
        g_orig = cutout_garment_rgba(garment_image).cropped.convert("RGBA")
        gw, gh = g_orig.size
        if gw < 16 or gh < 16:
            return ai_result, {"engine": "ai_only", "reason": "garment too small"}

        logger.info(
            "overlay: ai_size=%dx%d garment=%dx%d region=[%d,%d,%d,%d] rw=%d rh=%d",
            ai_w,
            ai_h,
            gw,
            gh,
            bx0,
            y0,
            bx1,
            y1,
            region_w,
            region_h,
        )

        # ── Step 2: Scale garment to COVER region (preserve aspect ratio) ──────────
        # Scale so garment fully covers the region (may overflow edges — we crop it)
        scale = max(region_w / float(gw), region_h / float(gh))
        scaled_w = max(2, int(gw * scale))
        scaled_h = max(2, int(gh * scale))
        g_scaled = g_orig.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        # Center the scaled garment on the region
        paste_x = bx0 + (region_w - scaled_w) // 2
        paste_y = y0 + (region_h - scaled_h) // 2

        # Clamp so it stays on canvas
        paste_x = max(0, min(paste_x, ai_w - 2))
        paste_y = max(0, min(paste_y, ai_h - 2))
        fit_w = min(scaled_w, ai_w - paste_x)
        fit_h = min(scaled_h, ai_h - paste_y)
        if fit_w < 2 or fit_h < 2:
            return ai_result, {"engine": "ai_only", "reason": "garment doesn't fit"}

        g_fitted = g_scaled.crop((0, 0, fit_w, fit_h))

        # ── Step 3: Feathered alpha layer ─────────────────────────────────────────
        layer = Image.new("RGBA", (ai_w, ai_h), (0, 0, 0, 0))
        layer.paste(g_fitted, (paste_x, paste_y), g_fitted)
        feather_px = max(1, int(min(ai_w, ai_h) * 0.015))
        layer = _feather_alpha(layer, radius_px=feather_px)

        # Protect face/neck
        protect = _upper_protect_mask((ai_w, ai_h), protect_until_y=int(ai_h * 0.22))
        r_ch, g_ch, b_ch, a_ch = layer.split()
        a_ch = ImageChops.multiply(a_ch, protect)
        layer = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

        # Step 3b: detect near-zero alpha (rembg fails on solid-color test images)
        layer_alpha_check = np.array(a_ch, dtype=np.float32) / 255.0
        if layer_alpha_check.max() < 0.05:
            return ai_result, {
                "engine": "ai_only",
                "reason": "garment alpha too low after feathering",
            }

        # ── Step 4: Absolute alpha blend ─────────────────────────────────────────
        # result = garment * (alpha * garment_alpha) + ai * (1 - alpha * garment_alpha)
        layer_arr = np.array(layer, dtype=np.float32)
        layer_alpha = layer_arr[:, :, 3] / 255.0  # HxW
        strength = layer_alpha * garment_alpha  # HxW

        r = np.clip(
            layer_arr[:, :, 0] * strength + ai_rgb[:, :, 0] * (1.0 - strength),
            0,
            255,
        ).astype(np.uint8)
        g_out = np.clip(
            layer_arr[:, :, 1] * strength + ai_rgb[:, :, 1] * (1.0 - strength),
            0,
            255,
        ).astype(np.uint8)
        b_out = np.clip(
            layer_arr[:, :, 2] * strength + ai_rgb[:, :, 2] * (1.0 - strength),
            0,
            255,
        ).astype(np.uint8)

        result = Image.fromarray(np.stack([r, g_out, b_out], axis=2), mode="RGB")

        return result, {
            "engine": "ai_warp_hybrid",
            "overlay_region": {"x0": bx0, "y0": y0, "x1": bx1, "y1": y1},
            "garment_original_size": (gw, gh),
            "garment_scaled_size": (scaled_w, scaled_h),
            "garment_alpha": garment_alpha,
            "pose_detected": kpts is not None,
        }
    except Exception as e:
        import traceback

        logger.warning("overlay_top_onto_ai_result failed: %s\n%s", e, traceback.format_exc())
        return ai_result, {"engine": "ai_only", "reason": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# White-Background Garment Paste (simplified, no CatVTON)
# ─────────────────────────────────────────────────────────────────────────────


def tryon_top_garment_paste(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.008,
) -> tuple[Image.Image, WarpMetadata]:
    """Paste upper garment onto person using clean white-background product photos.

    This is a simplified, dedicated mode for standardized white-background product
    images (白底标准图). Unlike hybrid/tryon_top_warp_preserve, this function:

      1. Auto-detects garment orientation (flat-lay horizontal → rotates upright)
      2. Scales garment to match body proportions via MediaPipe/SCHP keypoints
      3. Applies a trapezoid body-shape warp (narrower at shoulders, wider at waist)
      4. Skips CatVTON entirely (avoids AI mangling product photos)

    Args:
        person_image: PIL RGB image of the person.
        garment_image: PIL RGB image of the garment (white-background product photo).
        alpha_feather_ratio: Edge feathering radius as ratio of image size.

    Returns:
        (result_rgb, metadata)
    """
    base = person_image.convert("RGBA")
    pw, ph = base.size

    # ── Step 1: Cut out garment from white background ────────────────────────
    cutout = cutout_garment_rgba(garment_image)
    g = cutout.cropped.convert("RGBA")
    gw, gh = g.size
    if gw < 16 or gh < 16:
        raise ValueError("garment too small for top paste")

    # ── Step 2: Auto-detect and correct garment orientation ───────────────────
    # Flat-lay product photos are often captured horizontally (garment laid flat).
    # For wearing, the garment must be upright (taller than wide for upper garments).
    g = _auto_rotate_garment(g)
    gw, gh = g.size  # Update dimensions after rotation

    # ── Step 3: Get body bounds from pose/SCHP ───────────────────────────────
    _used_pose = False

    # Priority 1: SCHP human parsing
    try:
        from app.services.human_parsing import schp_parse

        schp_result = schp_parse(person_image)
        if schp_result and schp_result.source != "heuristic_grabcut":
            top_mask = schp_result.top_region()
            rows = np.where(top_mask.max(axis=1) > 0.3)[0]
            cols = np.where(top_mask.max(axis=0) > 0.3)[0]
            if len(rows) > 10 and len(cols) > 10:
                x0 = int(cols[0])
                x1 = int(cols[-1])
                y_top = int(rows[0])
                y_bottom = int(rows[-1])
                neck_y = _clamp_int(
                    int(y_top + (y_bottom - y_top) * 0.15),
                    int(ph * 0.12),
                    int(ph * 0.32),
                )
                waist_y = _clamp_int(
                    int(y_top + (y_bottom - y_top) * 0.70),
                    int(ph * 0.45),
                    int(ph * 0.82),
                )
                _used_pose = True
                logger.info(
                    "[PASTE] SCHP body bounds: x0=%d, x1=%d, neck_y=%d, waist_y=%d",
                    x0,
                    x1,
                    neck_y,
                    waist_y,
                )
    except Exception as schp_err:
        logger.debug("[PASTE] SCHP unavailable: %s", schp_err)

    # Priority 2: MediaPipe keypoints
    if not _used_pose:
        kpts = detect_pose_keypoints(person_image)
        if kpts:
            bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "top")
            if bounds.get("valid"):
                x0 = bounds["x0"]
                x1 = bounds["x1"]
                neck_y = bounds["neck_y"]
                waist_y = bounds["waist_y"]
                _used_pose = True
                logger.info(
                    "[PASTE] MediaPipe body bounds: " "x0=%d, x1=%d, neck_y=%d, waist_y=%d",
                    x0,
                    x1,
                    neck_y,
                    waist_y,
                )

    # Priority 3: Gradient energy fallback
    if not _used_pose:
        gray = np.asarray(person_image.convert("L"), dtype=np.float32)
        fg = _person_foreground_mask(person_image)
        b = None
        if fg is not None:
            b = _bounds_from_mask(fg, y0=int(ph * 0.06), y1=int(ph * 0.74), col_q=0.72, row_q=0.55)
        if b is not None:
            x0, x1, y_top, y_bottom = b
            span = max(2, int(y_bottom - y_top))
            neck_y = _clamp_int(int(y_top + span * 0.18), int(ph * 0.12), int(ph * 0.32))
            waist_y = _clamp_int(int(y_top + span * 0.70), int(ph * 0.45), int(ph * 0.82))
        else:
            x0, x1, neck_y, waist_y = _estimate_upper_body_bounds(gray)
        mid = (x0 + x1) // 2
        center = pw // 2
        drift = int(mid - center)
        if abs(drift) > int(pw * 0.12):
            shift = int(-0.65 * drift)
            bw = x1 - x0
            x0 = _clamp_int(x0 + shift, 0, pw - 2)
            x1 = _clamp_int(x0 + bw, x0 + 2, pw)
        pad_x = int((x1 - x0) * 0.03)
        x0 = _clamp_int(x0 - pad_x, 0, pw - 2)
        x1 = _clamp_int(x1 + pad_x, x0 + 2, pw)

    # Force garment top below chin
    y0 = _clamp_int(int(neck_y + ph * 0.02), int(ph * 0.12), int(ph * 0.42))
    y1 = _clamp_int(int(waist_y + ph * 0.03), y0 + 2, int(ph * 0.86))
    body_w = max(2, x1 - x0)
    body_h = max(2, y1 - y0)
    body_center_x = (x0 + x1) // 2

    # ── Step 4: Scale garment to COVER the full body region ────────────────────
    # Key fix: use max() so garment FILLS the region (was min() = tiny garment).
    target_w = int(body_w * 1.10)  # 10% wider than body for natural overhang
    target_h = int(body_h * 1.02)

    scale_by_w = target_w / float(gw)
    scale_by_h = target_h / float(gh)
    scale = max(scale_by_w, scale_by_h)  # max = FILL, min = FIT (old bug)

    itw = max(2, int(gw * scale))
    ith = max(2, int(gh * scale))
    g_scaled = g.resize((itw, ith), Image.Resampling.LANCZOS)

    # ── Step 5: Trapezoid warp (body shape) ─────────────────────────────────
    # Warp source to match body proportions. Source is much larger than dest,
    # so the warp compresses/expands it to fill the body region naturally.
    dest_w = body_w
    dest_h = body_h
    top_inset = max(1, int(dest_w * 0.05))  # 5% shoulder taper
    bot_inset = max(1, int(dest_w * 0.00))  # no taper at waist

    quad = (
        top_inset,
        0,  # top-left
        dest_w - top_inset,
        0,  # top-right
        dest_w - bot_inset,
        dest_h,  # bottom-right
        bot_inset,
        dest_h,  # bottom-left
    )

    # Crop source to match destination aspect ratio before warping
    src_ar = itw / float(ith)
    dst_ar = dest_w / float(dest_h)
    if src_ar > dst_ar:
        src_crop_w = int(ith * dst_ar)
        src_crop_h = ith
        src_x0 = (itw - src_crop_w) // 2
        src_y0 = 0
    else:
        src_crop_w = itw
        src_crop_h = int(itw / dst_ar)
        src_x0 = 0
        src_y0 = (ith - src_crop_h) // 2

    g_cropped = g_scaled.crop((src_x0, src_y0, src_x0 + src_crop_w, src_y0 + src_crop_h))
    g_warped = _pil_quad_warp(g_cropped, (dest_w, dest_h), quad)
    logger.info("[PASTE] Warped: %dx%d -> %dx%d", src_crop_w, src_crop_h, dest_w, dest_h)

    # ── Step 6: Compose onto person ────────────────────────────────────────
    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    paste_x = body_center_x - dest_w // 2
    paste_y = y0

    # Remove alpha padding — paste only the non-transparent content
    warp_mask = np.asarray(g_warped.split()[3], dtype=np.uint8)
    valid_cols = np.where(warp_mask.max(axis=0) > 10)[0]
    valid_rows = np.where(warp_mask.max(axis=1) > 10)[0]
    if len(valid_cols) > 0 and len(valid_rows) > 0:
        crop_x0 = int(valid_cols[0])
        crop_x1 = int(valid_cols[-1]) + 1
        crop_y0 = int(valid_rows[0])
        crop_y1 = int(valid_rows[-1]) + 1
        g_final = g_warped.crop((crop_x0, crop_y0, crop_x1, crop_y1))
        paste_x += crop_x0
        paste_y += crop_y0
    else:
        g_final = g_warped

    layer.paste(g_final, (paste_x, paste_y), g_final)

    # Feather edges for smooth boundary
    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 8)
    layer = _feather_alpha(layer, radius_px=feather_px)

    # Protect face/neck (no overwrite above ~18% height)
    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.18))
    r_ch, g_ch, b_ch, a_ch = layer.split()
    a_ch = ImageChops.multiply(a_ch, protect)
    layer = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

    out = Image.alpha_composite(base, layer).convert("RGB")
    engine_tag = "top_garment_paste_pose" if _used_pose else "top_garment_paste_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=(x0, y0, x1, y0 + max(2, int((y1 - y0) * 0.18))),
        left_leg_box=(x0, y0 + max(2, int((y1 - y0) * 0.18)), (x0 + x1) // 2, y1),
        right_leg_box=((x0 + x1) // 2, y0 + max(2, int((y1 - y0) * 0.18)), x1, y1),
        alpha_feather_px=feather_px,
    )
    return out, meta


def _auto_rotate_garment(g: Image.Image) -> Image.Image:
    """Auto-detect and correct garment orientation for upper-body garments.

    Flat-lay product photos often have the garment laid horizontally (wider than tall).
    For wearing, the garment should be upright (taller than wide).

    Detection heuristic:
      - Compare alpha coverage after rotation to decide which orientation is "correct"
      - Garment laid flat: alpha spread is wide and short
      - Garment worn upright: alpha spread is narrow and tall (like a torso)
      - Also detect by checking if garment aspect ratio is extreme (very wide or very tall)

    Returns:
        PIL RGBA image, rotated if needed (0° or 90° counter-clockwise).
    """
    if g.mode != "RGBA":
        g = g.convert("RGBA")

    alpha = np.asarray(g.split()[3], dtype=np.uint8)
    fg_mask = alpha > 20

    ys, xs = np.where(fg_mask)
    if xs.size < 50:
        return g  # Can't determine orientation from tiny mask

    g_w, g_h = g.size
    g_aspect = g_w / float(g_h)

    # Calculate alpha bounding box dimensions
    alpha_h = ys.max() - ys.min() + 1
    alpha_w = xs.max() - xs.min() + 1
    alpha_aspect = alpha_w / float(alpha_h) if alpha_h > 0 else g_aspect

    # Heuristic: if the garment is very wide (flat-lay on white background),
    # it should be rotated 90° counter-clockwise to be upright
    #
    # Signatures of a flat-lay horizontal garment:
    #   - Aspect ratio is landscape (wide > tall)
    #   - Alpha bounding box is also landscape
    #   - The garment typically appears as a rectangular panel in product photos
    needs_rotate = (alpha_aspect > 1.4 and g_aspect > 1.2) or (  # Clearly landscape orientation
        g_aspect > 1.8  # Extremely wide (definitely flat-lay)
    )

    if needs_rotate:
        logger.info(
            "[PASTE] Rotating garment %dx%d -> upright (aspect=%.2f -> %.2f)",
            g_w,
            g_h,
            g_aspect,
            g_h / float(g_w),
        )
        return g.rotate(90, expand=True, fillcolor=(0, 0, 0, 0))

    return g


# ─────────────────────────────────────────────────────────────────────────────
# Warp + CatVTON Hybrid Try-On
# ─────────────────────────────────────────────────────────────────────────────


def tryon_hybrid_warp_catvton(
    person_image: Image.Image,
    garment_image: Image.Image,
    catvton_result: Image.Image,
    garment_category: str,
    *,
    drape_alpha: float = 0.55,
    warp_strength: float = 0.6,
    debug_session_dir: str | None = None,
) -> tuple[Image.Image, dict]:
    """
    Warp + CatVTON 两阶段混合试衣。

    策略：
      1. Stage 1 (Warp): tryon_top_warp_preserve / tryon_skirt_warp / tryon_pants_warp
         → 像素级保真的衣服贴在人物身上（保留原始颜色/图案）
      2. Stage 2 (Blend): overlay_draping_from_ai
         → 将 CatVTON 产生的真实光影/阴影/褶皱叠加到 Warp 结果上
         → 衣服像素 100% 保留（颜色/图案/纹理完全来自原始衣服图）

    Args:
        person_image: 人物全身图
        garment_image: 衣服商品图
        catvton_result: CatVTON 推理结果（从 tryon_v2.catvton_engine_client 获得）
        garment_category: 衣服类别 (top/bottom/skirt)
        drape_alpha: AI 光影叠加强度（0.55 = 55% AI realism，45% warp identity）
                     高彩色衣服建议用 0.45（更多身份保留）
                     低饱和衣服建议用 0.65（更多 AI 真实感）
        warp_strength: 梯形变形强度（0.0-1.0，仅对 skirt 有效）。默认值 0.6，
                       降低裙摆过度变形问题。

    Returns:
        (混合结果图, metadata_dict)
    """
    try:
        from app.core.config import settings

        legacy_overlay_enabled = bool(
            getattr(settings, "TRYON_V2_HYBRID_WARP_OVERLAY_ENABLED", False)
        )
    except Exception:
        legacy_overlay_enabled = False

    if not legacy_overlay_enabled:
        result = catvton_result.convert("RGB")
        if result.size != person_image.size:
            result = result.resize(person_image.size, Image.LANCZOS)
        logger.info(
            "[HYBRID] Direct CatVTON mode: warp overlay disabled; returning diffusion output"
        )
        if debug_session_dir:
            try:
                from app.services.tryon_debug_utils import save_debug_stage_image

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename="hybrid_11_direct_catvton.jpg",
                    image=result,
                    metadata={
                        "stage": "hybrid_direct_catvton",
                        "engine": "catvton",
                        "method": "catvton_diffusion_direct",
                        "hybrid_warp_overlay_applied": False,
                        "resized_to_person": list(result.size),
                    },
                )
            except Exception as debug_err:
                logger.debug("Failed to save direct CatVTON hybrid debug stage: %s", debug_err)
        return result, {
            "engine": "catvton",
            "model": "catvton_local",
            "method": "catvton_diffusion_direct",
            "stage1_engine": "catvton_direct",
            "hybrid_warp_overlay_applied": False,
            "drape_alpha": 0.0,
        }

    cat = (garment_category or "").strip().lower()
    if any(k in cat for k in ("top", "上装", "上衣")):
        warp_engine_name = "top_warp_preserve"
        warp_result, warp_meta = tryon_top_warp_preserve(
            person_image=person_image, garment_image=garment_image
        )
    elif any(k in cat for k in ("skirt", "dress", "裙", "连衣裙")):
        warp_engine_name = "skirt_warp"
        warp_result, warp_meta = tryon_skirt_warp(
            person_image=person_image,
            garment_image=garment_image,
            warp_strength=warp_strength,
        )
    else:
        warp_engine_name = "pants_warp"
        warp_result, warp_meta = tryon_pants_warp(
            person_image=person_image, garment_image=garment_image
        )

    logger.info(
        f"[HYBRID] Stage 1 Warp 完成: engine={warp_engine_name}, "
        f"garment={garment_category}, drape_alpha={drape_alpha}, "
        f"warp_strength={warp_strength}"
    )

    if debug_session_dir:
        try:
            from app.services.tryon_debug_utils import save_debug_stage_image

            save_debug_stage_image(
                debug_session_dir=debug_session_dir,
                filename="hybrid_11_stage1_warp.jpg",
                image=warp_result,
                metadata={
                    "stage": "hybrid_stage1_warp",
                    "engine": warp_engine_name,
                    "garment_category": garment_category,
                    "warp_meta": {
                        "engine": warp_meta.engine,
                        "waistband_box": warp_meta.waistband_box,
                        "left_leg_box": warp_meta.left_leg_box,
                        "right_leg_box": warp_meta.right_leg_box,
                        "alpha_feather_px": warp_meta.alpha_feather_px,
                    },
                },
            )
            save_debug_stage_image(
                debug_session_dir=debug_session_dir,
                filename="hybrid_11b_catvton_raw_input.jpg",
                image=catvton_result,
                metadata={
                    "stage": "hybrid_catvton_raw_input",
                    "source": "CatVTON subprocess result before hybrid overlay",
                    "size": list(catvton_result.size),
                },
            )
        except Exception as debug_err:
            logger.debug("hybrid debug save failed: %s", debug_err)

    restrict_boxes = [
        box
        for box in (
            warp_meta.waistband_box,
            warp_meta.left_leg_box,
            warp_meta.right_leg_box,
        )
        if box and (box[2] - box[0]) > 2 and (box[3] - box[1]) > 2
    ]
    garment_preserve_mask = _warp_changed_region_mask(
        person_image,
        warp_result,
        restrict_boxes=restrict_boxes,
    )

    # Stage 2: overlay_draping_from_ai
    # 核心：衣服区域 100% 保留 warp，颜色/图案完全来自原始衣服
    #         衣服区域外叠加 CatVTON 的光影/阴影
    result, blend_meta = overlay_draping_from_ai(
        warp_result=warp_result,
        ai_result=catvton_result,
        drape_alpha=drape_alpha,
        garment_mask=garment_preserve_mask,
        debug_session_dir=debug_session_dir,
        debug_prefix="hybrid",
    )

    logger.info(
        f"[HYBRID] Stage 2 Blend 完成: engine=overlay_draping_from_ai, "
        f"drape_alpha={drape_alpha}"
    )

    meta = {
        "engine": "warp_catvton_hybrid",
        "stage1_engine": warp_engine_name,
        "stage2_engine": "overlay_draping_from_ai",
        "warp_meta": {
            "engine": warp_meta.engine,
            "waistband_box": warp_meta.waistband_box,
            "left_leg_box": warp_meta.left_leg_box,
            "right_leg_box": warp_meta.right_leg_box,
            "alpha_feather_px": warp_meta.alpha_feather_px,
            "warp_strength": warp_strength,
        },
        "blend_meta": blend_meta,
        "drape_alpha": drape_alpha,
        "warp_strength": warp_strength,
        "garment_category": garment_category,
        "color_fidelity": "100% (warp pixels preserved)",
        "realism_source": "CatVTON diffusion result",
        "pipeline": "warp_preserve → overlay_draping_from_ai",
    }
    return result, meta


def _estimate_face_region_from_original_pose(
    original_person: Image.Image,
    catvton_w: int,
    catvton_h: int,
) -> tuple[int, int, int, int] | None:
    """Estimate face bounding box from original person pose keypoints.

    Uses MediaPipe pose detection on the ORIGINAL person image (clear, reliable),
    then scales the nose/eye keypoints to catvton_result coordinates.

    Returns (x, y, w, h) in catvton_result pixel coordinates, or None if pose fails.
    This is the LAST RESORT fallback when Haar cascade detection has failed.
    """
    try:
        from app.services.tryon_v2.pose_utils import detect_pose_keypoints

        kpts = detect_pose_keypoints(original_person)
        if not kpts:
            return None

        # Get nose position (most reliable face proxy)
        nose = kpts.get("nose")
        left_eye = kpts.get("left_eye")
        right_eye = kpts.get("right_eye")

        orig_arr = np.asarray(original_person.convert("RGB"))
        orig_h, orig_w = orig_arr.shape[:2]

        if nose is None:
            return None

        # Keypoints are normalized [0,1]. Convert to pixel coords first.
        nose_px_x = nose[0] * orig_w
        nose_px_y = nose[1] * orig_h

        # Face height estimate: distance from nose to bottom of face ≈ 12-18% of image height
        # Use eye midpoint if available, otherwise use fixed ratio
        if left_eye and right_eye:
            eye_mid_y_px = (left_eye[1] + right_eye[1]) / 2.0 * orig_h
            face_top_px = max(0.0, nose_px_y - orig_h * 0.06)
            face_bot_px = min(float(orig_h), eye_mid_y_px + orig_h * 0.10)
        else:
            face_top_px = max(0.0, nose_px_y - orig_h * 0.10)
            face_bot_px = min(float(orig_h), nose_px_y + orig_h * 0.08)

        # Face width estimate: based on interpupillary distance or fixed ratio
        if left_eye and right_eye:
            eye_px_x0 = left_eye[0] * orig_w
            eye_px_x1 = right_eye[0] * orig_w
            eye_dist_px = abs(eye_px_x1 - eye_px_x0)
            face_w_px = eye_dist_px * 2.8  # ~2.8x IPD = full face width
        else:
            face_w_px = float(orig_w) * 0.18

        face_cx_px = nose_px_x
        face_left_px = max(0.0, face_cx_px - face_w_px / 2)
        face_right_px = min(float(orig_w), face_cx_px + face_w_px / 2)

        # Scale to catvton coordinates
        scale_x = catvton_w / float(orig_w)
        scale_y = catvton_h / float(orig_h)
        fw = max(1, int((face_right_px - face_left_px) * scale_x))
        fh = max(1, int((face_bot_px - face_top_px) * scale_y))
        fx = _clamp_int(int(face_left_px * scale_x), 0, catvton_w - fw)
        fy = _clamp_int(int(face_top_px * scale_y), 0, catvton_h - fh)

        # Clamp fw/fh to valid ranges
        fw = _clamp_int(fw, 4, catvton_w)
        fh = _clamp_int(fh, 4, catvton_h)

        logger.info(
            "catvton_color_fidelity: pose-based face estimate from original person "
            "([%d,%d,%d,%d] at %dx%d) -> catvton([%d,%d,%d,%d] at %dx%d)",
            int(face_left_px),
            int(face_top_px),
            int(face_right_px - face_left_px),
            int(face_bot_px - face_top_px),
            orig_w,
            orig_h,
            fx,
            fy,
            fw,
            fh,
            catvton_w,
            catvton_h,
        )
        return (fx, fy, fw, fh)

    except Exception as e:
        logger.debug("catvton_color_fidelity: pose-based face estimation failed (%s)", e)
        return None


def catvton_color_fidelity_enhance(
    catvton_result: Image.Image,
    original_garment: Image.Image,
    person_image: Image.Image,
    garment_category: str,
    *,
    fidelity_strength: float = 0.75,
) -> tuple[Image.Image, dict]:
    """
    增强 CatVTON 生成结果的衣服颜色保真度。

    核心策略：
    1. 在 CatVTON 结果中检测衣服区域（使用 GrabCut 或前景掩码）
    2. 对原衣服进行分割和 warp 变换，使其与 CatVTON 结果中人物的身体位置对齐
    3. 在衣服区域应用 LAB 亮度保持的颜色转移 + alpha 混合
       → 保留 CatVTON 的光影/阴影，只修正衣服颜色/图案
    4. 边缘羽化融合，避免接缝痕迹

    与 overlay_top_onto_ai_result 的关键区别：
    - overlay_top_onto_ai_result：直接用原衣服覆盖 AI 结果 → 贴纸感
    - catvton_color_fidelity_enhance：亮度保持的颜色转移 → 保留 AI 光影

    Args:
        catvton_result: CatVTON 生成的试穿结果
        original_garment: 原始衣服商品图
        person_image: 原始人物图（用于对齐）
        garment_category: 衣服类别 (top/bottom/skirt/dress)
        fidelity_strength: 0.0-1.0，颜色保真强度。0.75 表示 75% 原始衣服颜色

    Returns:
        (增强后的结果图, metadata_dict)
    """
    try:
        cr = catvton_result.convert("RGB")
        og = original_garment.convert("RGB")

        cw, ch = cr.size
        gw, gh = og.size

        # ── Step 1: 检测人物身体关键点 ────────────────────────────────────────
        from app.services.tryon_v2.pose_utils import detect_pose_keypoints

        cat = (garment_category or "").strip().lower()
        _is_top = any(k in cat for k in ("top", "上装", "上衣"))
        _is_skirt = any(k in cat for k in ("skirt", "dress", "裙", "连衣裙"))
        _is_bottom = any(k in cat for k in ("bottom", "pants", "下装", "裤", "lower"))

        # ── Step 2: 估算衣服区域在 CatVTON 结果中的位置 ─────────────────────
        kpts = detect_pose_keypoints(catvton_result)
        ankle_y: int | None = None
        if kpts:
            bounds = get_body_bounds_from_keypoints(kpts, cw, ch, "top" if _is_top else "bottom")
            if bounds.get("valid"):
                bx0 = int(bounds["x0"])
                bx1 = int(bounds["x1"])
                neck_y = int(bounds.get("neck_y") or 0)
                waist_y = int(bounds["waist_y"])
                if bounds.get("ankle_y"):
                    ankle_y = int(bounds["ankle_y"])
                body_valid = True
            else:
                body_valid = False
        else:
            body_valid = False

        if not body_valid:
            fg = _person_foreground_mask(catvton_result)
            if fg is not None:
                rows = np.any(fg, axis=1)
                cols = np.any(fg, axis=0)
                if rows.any() and cols.any():
                    y_top = int(np.where(rows)[0][0])
                    y_bot = int(np.where(rows)[0][-1])
                    x_lft = int(np.where(cols)[0][0])
                    x_rgt = int(np.where(cols)[0][-1])
                    bx0 = max(0, int(x_lft - cw * 0.03))
                    bx1 = min(cw, int(x_rgt + cw * 0.03))
                    body_span = y_bot - y_top
                    neck_y = y_top + int(body_span * 0.18)
                    waist_y = y_top + int(body_span * 0.52)
                    ankle_y = y_bot
                    body_valid = True
                else:
                    body_valid = False
            else:
                body_valid = False

        if not body_valid:
            if _is_top:
                bx0, bx1 = int(cw * 0.15), int(cw * 0.85)
                neck_y, waist_y = int(ch * 0.15), int(ch * 0.50)
            elif _is_skirt:
                bx0, bx1 = int(cw * 0.18), int(cw * 0.82)
                neck_y, waist_y = int(ch * 0.40), int(ch * 0.85)
            else:
                bx0, bx1 = int(cw * 0.20), int(cw * 0.80)
                neck_y, waist_y = int(ch * 0.38), int(ch * 0.50)
                ankle_y = int(ch * 0.92)

        # ── Step 2b: 精确检测面部区域（Haar cascade）────────────────────
        # 仅上衣类需要此保护。Haar cascade 比 MediaPipe neck_y 精确得多，
        # 确保面部（含下巴到颈部过渡）不被子衣颜色覆盖。
        face_box = None
        if _is_top:
            face_box = _detect_face_box_from_result(
                catvton_result, cw, ch, original_person=person_image
            )

        # ── Step 3: 计算衣服区域 ─────────────────────────────────────────────
        if _is_top:
            gar_x0 = max(0, bx0 - int(cw * 0.02))
            gar_x1 = min(cw, bx1 + int(cw * 0.02))
            gar_y0 = max(0, min(int(neck_y - ch * 0.05), int(ch * 0.40)))
            gar_y1 = min(ch, max(gar_y0 + 2, int(waist_y + ch * 0.06)))
        elif _is_skirt:
            gar_x0 = max(0, bx0 - int(cw * 0.03))
            gar_x1 = min(cw, bx1 + int(cw * 0.03))
            gar_y0 = max(0, int(waist_y - ch * 0.04))
            gar_y1 = min(ch, int(ch * 0.92))
        elif _is_bottom:
            gar_x0 = max(0, bx0 - int(cw * 0.03))
            gar_x1 = min(cw, bx1 + int(cw * 0.03))
            gar_y0 = max(0, int(waist_y - ch * 0.02))
            gar_y1 = min(ch, int((ankle_y or int(ch * 0.92)) + ch * 0.03))
        else:
            gar_x0 = max(0, bx0 - int(cw * 0.03))
            gar_x1 = min(cw, bx1 + int(cw * 0.03))
            gar_y0 = max(0, int(waist_y - ch * 0.02))
            gar_y1 = min(ch, int(ch * 0.92))

        gar_w = gar_x1 - gar_x0
        gar_h = gar_y1 - gar_y0

        if gar_w < 16 or gar_h < 16:
            logger.warning(
                "catvton_color_fidelity: garment region too small (%dx%d), skipping",
                gar_w,
                gar_h,
            )
            return catvton_result, {
                "engine": "catvton_color_fidelity",
                "reason": "region_too_small",
            }

        # ── Step 4: 分割原始衣服 ─────────────────────────────────────────────
        cutout = cutout_garment_rgba(og)
        gar_src = cutout.cropped.convert("RGBA")
        sw, sh = gar_src.size
        if sw < 16 or sh < 16:
            return catvton_result, {
                "engine": "catvton_color_fidelity",
                "reason": "garment_too_small",
            }

        # ── Step 5: 将原衣服缩放并贴合到目标区域 ─────────────────────────────
        # 缩放衣服使其覆盖目标区域
        scale = max(gar_w / float(sw), gar_h / float(sh))
        s_w = max(2, int(sw * scale))
        s_h = max(2, int(sh * scale))
        gar_scaled = gar_src.resize((s_w, s_h), Image.Resampling.LANCZOS)

        # 居中粘贴
        paste_x = gar_x0 + (gar_w - s_w) // 2
        paste_y = gar_y0 + (gar_h - s_h) // 2
        paste_x = max(0, min(paste_x, cw - 2))
        paste_y = max(0, min(paste_y, ch - 2))

        fit_w = min(s_w, cw - paste_x)
        fit_h = min(s_h, ch - paste_y)
        if fit_w < 2 or fit_h < 2:
            return catvton_result, {
                "engine": "catvton_color_fidelity",
                "reason": "fit_too_small",
            }

        gar_fitted = gar_scaled.crop((0, 0, fit_w, fit_h))

        # 创建衣服层
        layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        layer.paste(gar_fitted, (paste_x, paste_y), gar_fitted)

        # ── Step 6: 羽化边缘 ───────────────────────────────────────────────
        feather_ratio = 0.0075 if _is_bottom else 0.012
        feather_px = max(2, int(min(cw, ch) * feather_ratio))
        layer = _feather_alpha(layer, radius_px=feather_px)

        # 保护面部/颈部
        # 使用 Haar cascade 精确定位面部区域（仅上衣类）
        def _make_en_face_protect_mask(
            cw: int, ch: int, face_box: tuple[int, int, int, int] | None, neck_y: int
        ) -> Image.Image:
            protect_mask = Image.new("L", (cw, ch), color=255)
            if face_box is not None:
                fx, fy, fw, fh = face_box
                extend_bottom = int(fh * 0.25)
                protect_y0 = max(0, fy)
                protect_y1 = min(ch, fy + fh + extend_bottom)
                protect_x0 = max(0, fx - int(fw * 0.05))
                protect_x1 = min(cw, fx + fw + int(fw * 0.05))
                protect_mask.paste(0, (protect_x0, protect_y0, protect_x1, protect_y1))
            else:
                # Cascade fallback: pose-based estimation -> coarse ratio
                pose_face = _estimate_face_region_from_original_pose(person_image, cw, ch)
                if pose_face is not None:
                    fx2, fy2, fw2, fh2 = pose_face
                    extend2 = int(fh2 * 0.30)
                    protect_mask.paste(0, (0, 0, cw, min(ch, fy2 + fh2 + extend2)))
                else:
                    protect_until_y = max(0, int(max(neck_y + ch * 0.02, ch * 0.22)))
                    protect_mask.paste(0, (0, 0, cw, protect_until_y))
            return protect_mask

        def _make_en_lower_body_protect_mask(
            cw: int, ch: int, waist_y: int, ankle_y: int | None
        ) -> Image.Image:
            """Build lower-body protect mask: 0=protected, 255=allow garment color modification."""
            protect_mask = Image.new("L", (cw, ch), color=255)
            protect_upper_y = max(0, waist_y - int(ch * 0.02))
            if protect_upper_y > 0:
                protect_mask.paste(0, (0, 0, cw, protect_upper_y))
            if ankle_y is not None:
                protect_lower_y = min(ch, ankle_y + int(ch * 0.06))
                if protect_lower_y < ch:
                    protect_mask.paste(0, (0, protect_lower_y, cw, ch))
            return protect_mask

        protect = _make_en_face_protect_mask(cw, ch, face_box, neck_y)

        # 下装保护：保护上半身和鞋子区域（_is_bottom 专享）
        if _is_bottom:
            lower_protect = _make_en_lower_body_protect_mask(cw, ch, waist_y, ankle_y)
            protect = ImageChops.multiply(protect, lower_protect)
            logger.info(
                "catvton_color_fidelity_enhance: applied lower-body protect mask "
                "(waist_y=%d, ankle_y=%s)",
                waist_y,
                ankle_y,
            )

        r_ch, g_ch, b_ch, a_ch = layer.split()
        a_ch = ImageChops.multiply(a_ch, protect)
        layer = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

        # ── Step 7: LAB 亮度保持的颜色转移 + alpha 混合 ─────────────────────
        layer_np = np.array(layer)
        catvton_np = np.array(cr)
        result_np = np.array(cr)

        layer_alpha = layer_np[:, :, 3].astype(np.float32) / 255.0  # HxW
        strength = layer_alpha * fidelity_strength  # HxW

        # 只在衣服区域内处理
        roi_layer = layer_np[gar_y0:gar_y1, gar_x0:gar_x1]
        roi_catvton = catvton_np[gar_y0:gar_y1, gar_x0:gar_x1]
        roi_alpha = layer_alpha[gar_y0:gar_y1, gar_x0:gar_x1]
        roi_strength = strength[gar_y0:gar_y1, gar_x0:gar_x1]

        # 有效的衣服像素 (alpha > 30)
        valid = roi_alpha > 0.12

        if valid.sum() > 100:
            roi_catvton_lab = cv2.cvtColor(roi_catvton.astype(np.uint8), cv2.COLOR_RGB2LAB)
            roi_layer_lab = cv2.cvtColor(roi_layer[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2LAB)

            # 对每个通道进行加权混合
            for c in range(3):
                roi_catvton_c = roi_catvton_lab[:, :, c].astype(np.float32)
                roi_layer_c = roi_layer_lab[:, :, c].astype(np.float32)

                # 颜色转移：原衣服 * strength + CatVTON * (1 - strength)
                blended = roi_layer_c * roi_strength + roi_catvton_c * (1.0 - roi_strength)
                blended = np.clip(blended, 0, 255).astype(np.uint8)

                # 只在有效区域更新 result
                result_np[gar_y0:gar_y1, gar_x0:gar_x1, c] = np.where(
                    valid,
                    blended,
                    catvton_np[gar_y0:gar_y1, gar_x0:gar_x1, c],
                )

        result_img = Image.fromarray(result_np, mode="RGB")

        logger.info(
            "catvton_color_fidelity: region=[%d,%d,%d,%d] strength=%.2f",
            gar_x0,
            gar_y0,
            gar_x1,
            gar_y1,
            fidelity_strength,
        )
        return result_img, {
            "engine": "catvton_color_fidelity",
            "garment_region": {"x0": gar_x0, "y0": gar_y0, "x1": gar_x1, "y1": gar_y1},
            "fidelity_strength": fidelity_strength,
            "body_valid": body_valid,
        }

    except Exception as e:
        import traceback

        logger.warning("catvton_color_fidelity_enhance failed: %s\n%s", e, traceback.format_exc())
        return catvton_result, {"engine": "catvton_color_fidelity", "reason": str(e)}


def catvton_lab_chroma_color_correct(
    catvton_result: Image.Image,
    original_garment: Image.Image,
    person_image: Image.Image,
    garment_category: str,
    *,
    raw_mask_image: Image.Image | None = None,
    fidelity_strength: float = 0.75,
) -> tuple[Image.Image, dict]:
    """Correct CatVTON garment color without pasting original garment pixels."""
    try:
        cr = catvton_result.convert("RGB")
        cw, ch = cr.size
        result_np = np.asarray(cr, dtype=np.uint8)

        cutout = cutout_garment_rgba(original_garment.convert("RGB"))
        source_rgba = np.asarray(cutout.cropped.convert("RGBA"), dtype=np.uint8)
        source_alpha = source_rgba[:, :, 3] > 30
        if int(source_alpha.sum()) < 100:
            return catvton_result, {
                "engine": "catvton_lab_chroma_color_correct",
                "reason": "source_alpha_too_small",
            }

        source_rgb = source_rgba[:, :, :3][source_alpha]
        source_lab = cv2.cvtColor(
            source_rgb.reshape(-1, 1, 3).astype(np.uint8),
            cv2.COLOR_RGB2LAB,
        ).reshape(-1, 3)
        source_mean = source_lab.mean(axis=0).astype(np.float32)

        mask_img = None
        if raw_mask_image is not None:
            mask_img = raw_mask_image.convert("L").resize((cw, ch), Image.Resampling.NEAREST)
        else:
            person_resized = person_image.convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
            diff = np.abs(result_np.astype(np.int16) - np.asarray(person_resized, dtype=np.int16))
            diff_gray = diff.mean(axis=2).astype(np.uint8)
            _, diff_mask = cv2.threshold(diff_gray, 16, 255, cv2.THRESH_BINARY)
            mask_img = Image.fromarray(diff_mask, mode="L")

        mask_np = np.asarray(mask_img, dtype=np.uint8)
        mask_np = cv2.morphologyEx(mask_np, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = mask_np > 127
        person_resized = person_image.convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
        diff_from_person = np.abs(
            result_np.astype(np.int16) - np.asarray(person_resized, dtype=np.int16)
        ).mean(axis=2)
        hsv_result = cv2.cvtColor(result_np, cv2.COLOR_RGB2HSV)
        value = hsv_result[:, :, 2]
        sat = hsv_result[:, :, 1]
        raw_garment_like = (value < 228) | ((diff_from_person > 12) & (value < 245)) | (sat > 18)
        mask &= raw_garment_like
        if int(mask.sum()) < 100:
            return catvton_result, {
                "engine": "catvton_lab_chroma_color_correct",
                "reason": "mask_too_small",
            }

        cat_lab = cv2.cvtColor(result_np, cv2.COLOR_RGB2LAB).astype(np.float32)
        raw_mean = cat_lab[mask].mean(axis=0).astype(np.float32)
        strength = float(np.clip(fidelity_strength, 0.0, 1.0))

        delta_l = float(np.clip(source_mean[0] - raw_mean[0], -36.0, 36.0)) * min(0.55, strength)
        delta_a = float(np.clip(source_mean[1] - raw_mean[1], -38.0, 38.0)) * strength
        delta_b = float(np.clip(source_mean[2] - raw_mean[2], -38.0, 38.0)) * strength

        corrected_lab = cat_lab.copy()
        corrected_lab[:, :, 0] = np.clip(corrected_lab[:, :, 0] + delta_l, 0, 255)
        corrected_lab[:, :, 1] = np.clip(corrected_lab[:, :, 1] + delta_a, 0, 255)
        corrected_lab[:, :, 2] = np.clip(corrected_lab[:, :, 2] + delta_b, 0, 255)
        corrected_rgb = cv2.cvtColor(corrected_lab.astype(np.uint8), cv2.COLOR_LAB2RGB).astype(
            np.float32
        )

        feather = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(2, int(min(cw, ch) * 0.01)))
        )
        alpha_np = np.asarray(feather, dtype=np.float32) / 255.0
        alpha_np *= mask.astype(np.float32)
        alpha = alpha_np[:, :, None]
        blended = result_np.astype(np.float32) * (1.0 - alpha) + corrected_rgb * alpha
        result_img = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")

        logger.info(
            "catvton_lab_chroma: delta_lab=[%.2f,%.2f,%.2f] " "strength=%.2f mask_coverage=%.3f",
            delta_l,
            delta_a,
            delta_b,
            strength,
            float(mask.mean()),
        )
        return result_img, {
            "engine": "catvton_lab_chroma_color_correct",
            "delta_lab": [round(delta_l, 3), round(delta_a, 3), round(delta_b, 3)],
            "source_lab_mean": [round(float(v), 3) for v in source_mean],
            "raw_lab_mean": [round(float(v), 3) for v in raw_mean],
            "mask_coverage": round(float(mask.mean()), 4),
            "fidelity_strength": strength,
        }

    except Exception as e:
        import traceback

        logger.warning("catvton_lab_chroma_color_correct failed: %s\n%s", e, traceback.format_exc())
        return catvton_result, {
            "engine": "catvton_lab_chroma_color_correct",
            "reason": str(e),
        }


def catvton_lower_color_rescue(
    catvton_result: Image.Image,
    original_garment: Image.Image,
    person_image: Image.Image,
    *,
    fidelity_strength: float = 0.78,
    debug_session_dir: str | None = None,
) -> tuple[Image.Image, dict]:
    """Recolor CatVTON lower-garment pixels without using a warped garment layer."""
    try:
        cr = catvton_result.convert("RGB")
        cw, ch = cr.size
        result_np = np.asarray(cr, dtype=np.float32)
        person_np = np.asarray(
            person_image.convert("RGB").resize((cw, ch), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )

        cutout = cutout_garment_rgba(original_garment.convert("RGB"))
        src_rgba = np.asarray(cutout.cropped.convert("RGBA"), dtype=np.uint8)
        src_alpha = src_rgba[:, :, 3] > 30
        if int(src_alpha.sum()) < 128:
            return catvton_result, {
                "engine": "catvton_lower_color_rescue",
                "reason": "source_alpha_too_small",
            }

        src_rgb = src_rgba[:, :, :3][src_alpha]
        src_lab = cv2.cvtColor(src_rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3)
        source_ab = np.median(src_lab[:, 1:3].astype(np.float32), axis=0)
        source_l = float(np.median(src_lab[:, 0].astype(np.float32)))

        kpts = detect_pose_keypoints(person_image) or {}
        bounds = get_body_bounds_from_keypoints(kpts, cw, ch, "bottom") if kpts else {}
        if bounds.get("valid"):
            bx0 = _clamp_int(int(bounds.get("x0", cw * 0.20)) - int(cw * 0.035), 0, cw - 1)
            bx1 = _clamp_int(int(bounds.get("x1", cw * 0.80)) + int(cw * 0.035), bx0 + 1, cw)
            waist_y = _clamp_int(
                int(bounds.get("waist_y", ch * 0.46)), int(ch * 0.30), int(ch * 0.62)
            )
            ankle_y = _clamp_int(int(bounds.get("ankle_y", ch * 0.90)), int(ch * 0.72), ch - 1)
        else:
            bx0, bx1 = int(cw * 0.20), int(cw * 0.80)
            waist_y, ankle_y = int(ch * 0.46), int(ch * 0.92)

        hsv_result = cv2.cvtColor(result_np.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv_person = cv2.cvtColor(person_np.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
        diff = np.abs(result_np - person_np).mean(axis=2)
        yy, xx = np.indices((ch, cw))

        r_person = person_np[:, :, 0]
        g_person = person_np[:, :, 1]
        b_person = person_np[:, :, 2]
        skin_like = (
            (r_person > 150)
            & (g_person > 95)
            & (b_person > 70)
            & (r_person > g_person + 10)
            & (g_person > b_person + 5)
        )
        near_white = (hsv_person[:, :, 2] > 235) & (hsv_person[:, :, 1] < 35)
        lower_zone = (
            (yy >= max(0, int(waist_y - ch * 0.012)))
            & (yy <= min(ch - 1, int(ankle_y + ch * 0.025)))
            & (xx >= bx0)
            & (xx <= bx1)
        )
        candidate = (
            lower_zone & (hsv_result[:, :, 2] < 205.0) & (diff > 7.0) & ~skin_like & ~near_white
        )
        candidate = cv2.morphologyEx(
            candidate.astype(np.uint8),
            cv2.MORPH_OPEN,
            np.ones((5, 5), dtype=np.uint8),
        ).astype(bool)
        candidate = cv2.morphologyEx(
            candidate.astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((25, 13), dtype=np.uint8),
        ).astype(bool)
        candidate = _keep_significant_mask_components(
            candidate,
            min_area_ratio=0.20,
            max_components=2,
        )
        candidate = _fill_mask_holes(candidate)
        candidate = cv2.morphologyEx(
            candidate.astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((19, 11), dtype=np.uint8),
        ).astype(bool)
        if int(candidate.sum()) < max(256, int(cw * ch * 0.012)):
            return catvton_result, {
                "engine": "catvton_lower_color_rescue",
                "reason": "mask_too_small",
                "mask_coverage": round(float(candidate.mean()), 4),
            }

        cat_lab = cv2.cvtColor(result_np.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
        corrected_lab = cat_lab.copy()
        strength = float(np.clip(fidelity_strength, 0.0, 1.0))
        corrected_lab[candidate, 1] = (
            corrected_lab[candidate, 1] * (1.0 - strength) + source_ab[0] * strength
        )
        corrected_lab[candidate, 2] = (
            corrected_lab[candidate, 2] * (1.0 - strength) + source_ab[1] * strength
        )
        target_l = cat_lab[candidate, 0] * 0.72 + source_l * 0.28
        dark_floor = source_l * 0.66
        target_l = np.maximum(target_l, dark_floor)
        corrected_lab[candidate, 0] = corrected_lab[candidate, 0] * 0.55 + target_l * 0.45
        corrected_rgb = cv2.cvtColor(
            np.clip(corrected_lab, 0, 255).astype(np.uint8),
            cv2.COLOR_LAB2RGB,
        ).astype(np.float32)

        alpha = cv2.GaussianBlur(candidate.astype(np.float32), (13, 13), 0)
        alpha = np.clip(alpha * 0.86, 0.0, 0.86)
        alpha[candidate] = np.maximum(alpha[candidate], 0.74)
        alpha_3 = alpha[:, :, np.newaxis]
        out_np = corrected_rgb * alpha_3 + result_np * (1.0 - alpha_3)
        out_img = Image.fromarray(np.clip(out_np, 0, 255).astype(np.uint8), mode="RGB")

        if debug_session_dir:
            try:
                from app.services.tryon_debug_utils import save_debug_stage_image

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename="12_lower_color_rescue_mask.png",
                    image=Image.fromarray((candidate.astype(np.uint8) * 255), mode="L"),
                    metadata={
                        "stage": "lower_color_rescue_mask",
                        "coverage": round(float(candidate.mean()), 4),
                        "waist_y": int(waist_y),
                        "ankle_y": int(ankle_y),
                        "body_x0": int(bx0),
                        "body_x1": int(bx1),
                    },
                )
            except Exception as dbg_err:
                logger.debug("lower color rescue debug save failed: %s", dbg_err)

        return out_img, {
            "engine": "catvton_lower_color_rescue",
            "mask_coverage": round(float(candidate.mean()), 4),
            "fidelity_strength": round(float(strength), 4),
            "source_lab_median": [
                round(float(source_l), 3),
                round(float(source_ab[0]), 3),
                round(float(source_ab[1]), 3),
            ],
            "body_valid": bool(bounds.get("valid")),
        }
    except Exception as e:
        import traceback

        logger.warning("catvton_lower_color_rescue failed: %s\n%s", e, traceback.format_exc())
        return catvton_result, {
            "engine": "catvton_lower_color_rescue",
            "reason": str(e),
        }


def catvton_color_fidelity_spatial(
    catvton_result: Image.Image,
    original_garment: Image.Image,
    person_image: Image.Image,
    garment_category: str,
    *,
    fidelity_strength: float = 0.75,
    lower_color_rescue: bool = False,
    debug_session_dir: str | None = None,
) -> tuple[Image.Image, dict]:
    """
    空间感知的衣服颜色保真增强——专为彩色格子/条纹/图案衣服设计。

    与 catvton_color_fidelity_enhance 的关键区别：
    - catvton_color_fidelity_enhance: LAB 空间均匀混合（单色衣服有效，图案衣服会变褐色）
    - catvton_color_fidelity_spatial: 直接像素级保真（保留原始颜色/图案空间分布）

    策略：
    1. 将原衣服 warp 到 CatVTON 结果中的人物身体位置（使用姿态关键点对齐）
    2. 在衣服区域内，用原衣服像素直接替换 CatVTON 生成的颜色
    3. 保留 CatVTON 的边缘光影和非衣服区域（身体/背景）
    4. 羽化边缘过渡

    这保证了蓝白格子、彩色条纹等图案 100% 保真，不会变成褐色。

    Args:
        catvton_result: CatVTON 生成的试穿结果
        original_garment: 原始衣服商品图
        person_image: 原始人物图（用于姿态检测）
        garment_category: 衣服类别 (top/bottom/skirt/dress)
        fidelity_strength: 0.0-1.0，保真强度。0.75 表示 75% 原始衣服 + 25% CatVTON

    Returns:
        (保真后的结果图, metadata_dict)
    """
    try:
        cr = catvton_result.convert("RGB")
        cw, ch = cr.size
        result_np = np.array(cr, dtype=np.float32)

        def _save_fidelity_debug(
            name: str, image: Image.Image, metadata: dict | None = None
        ) -> None:
            if not debug_session_dir:
                return
            try:
                from app.services.tryon_debug_utils import save_debug_stage_image

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename=name,
                    image=image,
                    metadata=metadata,
                )
            except Exception as dbg_err:
                logger.warning(
                    "catvton_color_fidelity_spatial: failed to save %s: %s", name, dbg_err
                )

        def _mask_debug_image(mask: np.ndarray, scale: float = 255.0) -> Image.Image:
            arr = np.clip(mask.astype(np.float32) * scale, 0, 255).astype(np.uint8)
            return Image.fromarray(arr, mode="L")

        def _load_debug_garment_mask() -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
            if not debug_session_dir:
                return None
            try:
                from app.services.tryon_debug_utils import resolve_debug_session_dir

                debug_dir = resolve_debug_session_dir(debug_session_dir)
                if debug_dir is None:
                    return None
                mask_path = debug_dir / "08_mask_resized.png"
                if not mask_path.exists():
                    return None
                mask_img = Image.open(mask_path).convert("L")
                if mask_img.size != (cw, ch):
                    mask_img = mask_img.resize((cw, ch), Image.Resampling.NEAREST)
                mask_u8 = np.array(mask_img, dtype=np.uint8)
                mask_bool = mask_u8 > 127
                if int(mask_bool.sum()) < 64:
                    return None
                mask_bool = cv2.morphologyEx(
                    mask_bool.astype(np.uint8),
                    cv2.MORPH_CLOSE,
                    np.ones((5, 5), dtype=np.uint8),
                ).astype(bool)
                ys, xs = np.where(mask_bool)
                if xs.size == 0 or ys.size == 0:
                    return None
                bbox = (int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1))
                mask_float = cv2.GaussianBlur(
                    mask_bool.astype(np.float32),
                    (7, 7),
                    0,
                )
                mask_float = np.clip(mask_float, 0.0, 1.0)
                return mask_float, bbox
            except Exception as mask_err:
                logger.warning(
                    "catvton_color_fidelity_spatial: failed to load CatVTON debug mask: %s",
                    mask_err,
                )
                return None

        cat = (garment_category or "").strip().lower()
        _is_top = any(k in cat for k in ("top", "上装", "上衣"))
        _is_skirt = any(k in cat for k in ("skirt", "dress", "裙", "连衣裙"))
        _is_bottom = any(k in cat for k in ("bottom", "pants", "下装", "裤", "lower"))

        # ── Step 1: 检测 CatVTON 结果中的人物身体位置 ─────────────────────
        from app.services.tryon_v2.pose_utils import (
            detect_pose_keypoints,
            get_body_bounds_from_keypoints,
        )

        kpts = detect_pose_keypoints(catvton_result)
        body_valid = False
        bounds: dict = {}
        ankle_y: int | None = None

        if kpts:
            bounds = get_body_bounds_from_keypoints(kpts, cw, ch, "top" if _is_top else "bottom")
            if bounds.get("valid"):
                bx0 = int(bounds["x0"])
                bx1 = int(bounds["x1"])
                neck_y = int(bounds.get("neck_y") or 0)
                waist_y = int(bounds["waist_y"])
                if bounds.get("ankle_y"):
                    ankle_y = int(bounds["ankle_y"])
                body_valid = True

        if not body_valid:
            fg = _person_foreground_mask(catvton_result)
            if fg is not None:
                rows = np.any(fg, axis=1)
                cols = np.any(fg, axis=0)
                if rows.any() and cols.any():
                    y_top = int(np.where(rows)[0][0])
                    y_bot = int(np.where(rows)[0][-1])
                    x_lft = int(np.where(cols)[0][0])
                    x_rgt = int(np.where(cols)[0][-1])
                    bx0 = max(0, int(x_lft - cw * 0.03))
                    bx1 = min(cw, int(x_rgt + cw * 0.03))
                    body_span = y_bot - y_top
                    neck_y = y_top + int(body_span * 0.18)
                    waist_y = y_top + int(body_span * 0.52)
                    ankle_y = y_bot
                    body_valid = True

        if not body_valid:
            bx0, bx1 = int(cw * 0.15), int(cw * 0.85)
            neck_y, waist_y = int(ch * 0.15), int(ch * 0.50)
            ankle_y = int(ch * 0.92)

        logger.info(
            "catvton_color_fidelity_spatial: cat=%r, _is_top=%s, _is_bottom=%s, "
            "body_valid=%s, waist_y=%s, ankle_y=%s",
            cat,
            _is_top,
            _is_bottom,
            body_valid,
            waist_y,
            ankle_y,
        )

        # ── Step 1b: 精确检测面部区域（Haar cascade）─────────────────────
        # neck_y 来自 MediaPipe 关键点，只能估算到下巴位置，精度不足。
        # 实际面部可延伸到下巴以下、颈部以上。用 Haar cascade 精确定位，
        # 确保面部区域绝不被子衣颜色覆盖（防止"脸部被清除"bug）。
        # 仅上衣类需要此保护（下装/裙子不覆盖面部）。
        face_box = None
        if _is_top:
            face_box = _detect_face_box_from_result(
                catvton_result, cw, ch, original_person=person_image
            )

        def _make_face_protect_mask(
            cw: int, ch: int, face_box: tuple[int, int, int, int] | None, neck_y: int
        ) -> Image.Image:
            """Build face/neck protect mask: 0=protected, 255=allow garment."""
            protect_mask = Image.new("L", (cw, ch), color=255)
            if face_box is not None:
                fx, fy, fw, fh = face_box
                # Extend face box downward by ~25% of face height to cover chin → neck transition
                extend_bottom = int(fh * 0.25)
                protect_y0 = max(0, fy)
                protect_y1 = min(ch, fy + fh + extend_bottom)
                protect_x0 = max(0, fx - int(fw * 0.05))
                protect_x1 = min(cw, fx + fw + int(fw * 0.05))
                protect_mask.paste(0, (protect_x0, protect_y0, protect_x1, protect_y1))
            else:
                # Cascade fallback: pose-based estimation -> coarse ratio
                pose_face = _estimate_face_region_from_original_pose(person_image, cw, ch)
                if pose_face is not None:
                    fx2, fy2, fw2, fh2 = pose_face
                    extend2 = int(fh2 * 0.30)
                    protect_mask.paste(0, (0, 0, cw, min(ch, fy2 + fh2 + extend2)))
                else:
                    protect_until_y = max(0, int(neck_y - ch * 0.06))
                    protect_mask.paste(0, (0, 0, cw, protect_until_y))
            return protect_mask

        def _make_lower_body_protect_mask(
            cw: int, ch: int, waist_y: int, ankle_y: int | None
        ) -> Image.Image:
            """Build lower-body protect mask: 0=protected, 255=allow garment color modification.

            Protects:
            - Upper body (above waist_y) — prevent upper garment contamination
            - Shoes/feet (below ankle_y + 10% margin) — prevent shoe contamination
            """
            protect_mask = Image.new("L", (cw, ch), color=255)
            # Protect upper body: everything above waist_y
            protect_upper_y = max(0, waist_y - int(ch * 0.02))
            if protect_upper_y > 0:
                protect_mask.paste(0, (0, 0, cw, protect_upper_y))
            # Protect shoes/feet: everything below ankle_y + margin
            if ankle_y is not None:
                protect_lower_y = min(ch, ankle_y + int(ch * 0.06))
                if protect_lower_y < ch:
                    protect_mask.paste(0, (0, protect_lower_y, cw, ch))
            return protect_mask

        # ── Step 1b: 计算正确的衣服目标区域 ───────────────────────────────
        # 核心原则：spatial fidelity 的目标区域必须与 CatVTON mask 区域几何一致。
        # CatVTON mask 生成时将衣服 alpha 等比缩放填充身体区域。
        # 这里也做等比缩放填充——衣服图案覆盖的区域 = CatVTON 生成的衣服区域。
        #
        # 修复 (Bug 修复):
        #   旧代码用 bx0/bx1（身体区域边界）直接作为 gar_x0/gar_x1，
        #   然后计算 gar_w=gar_x1-gar_x0 作为缩放基准。
        #   但 bx1-bx0 通常是 ~220px（从 get_body_bounds_from_keypoints），
        #   而原始衣服图是 768px 宽 → scale = 220/768 ≈ 0.29 → 衣服被缩小到 24%！
        #
        #   正确做法：以身体区域的【中心】为基准，用【衣服原始宽高比】计算目标尺寸。
        #   衣服图案完整填满身体区域（和 CatVTON mask 行为一致）。

        # 计算身体区域中心
        if body_valid:
            # body region x 范围 [bx0, bx1]，中心
            body_cx = (bx0 + bx1) // 2
            if _is_bottom and ankle_y is not None:
                # 下装：中心在 waist_y 和 ankle_y 之间
                body_cy = (waist_y + ankle_y) // 2
            else:
                # 上装/裙子：中心在 neck_y 和 waist_y 之间
                body_cy = (neck_y + waist_y) // 2
        else:
            # Fallback: 图像中央
            body_cx = cw // 2
            body_cy = ch // 2

        # 衣服区域高度（与 CatVTON mask 一致，按衣服类型计算）
        if _is_skirt or "dress" in cat:
            # 连衣裙/裙子：从 waist_y（臀部）到图像底部
            gar_target_h = ch - waist_y
            gar_y0_ref = waist_y
        elif any(k in cat for k in ("bottom", "pants", "下装", "裤", "lower")):
            # 下装：从 waist_y（臀部）到脚踝
            if body_valid and bounds.get("ankle_y"):
                gar_target_h = bounds["ankle_y"] - waist_y
            else:
                gar_target_h = int(ch * 0.50)  # fallback: 臀到脚踝约50%图高
            gar_y0_ref = waist_y
        else:
            # 上装：waist_y - neck_y
            gar_target_h = waist_y - neck_y
            gar_y0_ref = neck_y
        if gar_target_h < 32:
            gar_target_h = int(ch * 0.40)  # fallback

        # 衣服区域宽度：从 get_body_bounds_from_keypoints 的 x0/x1 提取
        gar_target_w = bx1 - bx0
        if gar_target_w < 32:
            gar_target_w = int(cw * 0.70)  # fallback

        gar_w = gar_target_w
        gar_h = gar_target_h

        if gar_w < 16 or gar_h < 16:
            logger.warning(
                "catvton_color_fidelity_spatial: body region too small (%dx%d)",
                gar_w,
                gar_h,
            )
            return catvton_result, {
                "engine": "catvton_color_fidelity_spatial",
                "reason": "region_too_small",
            }

        # 衣服目标区域的左上角（以身体区域中心为基准水平居中）
        gar_x0 = body_cx - gar_w // 2
        gar_y0 = gar_y0_ref
        gar_x1 = gar_x0 + gar_w
        gar_y1 = gar_y0 + gar_h

        catvton_mask_np: np.ndarray | None = None
        mask_region = _load_debug_garment_mask()
        if mask_region is not None:
            catvton_mask_np, mask_bbox = mask_region
            gar_x0, gar_y0, gar_x1, gar_y1 = mask_bbox
            # For lower garments, keep a small waist/hip band above waist_y so
            # uploaded waistband and connected crotch style can transfer. The
            # lower-body protect mask still prevents painting over the upper body.
            if _is_bottom:
                expanded_bbox = _expand_lower_mask_bbox(
                    (gar_x0, gar_y0, gar_x1, gar_y1),
                    image_w=cw,
                    image_h=ch,
                    waist_y=waist_y,
                    ankle_y=ankle_y,
                )
                if expanded_bbox != (gar_x0, gar_y0, gar_x1, gar_y1):
                    logger.info(
                        "catvton_color_fidelity_spatial: expanded lower mask region "
                        "[%d,%d,%d,%d] -> [%d,%d,%d,%d]",
                        gar_x0,
                        gar_y0,
                        gar_x1,
                        gar_y1,
                        expanded_bbox[0],
                        expanded_bbox[1],
                        expanded_bbox[2],
                        expanded_bbox[3],
                    )
                gar_x0, gar_y0, gar_x1, gar_y1 = expanded_bbox
            lower_y0_limit = max(0, int(waist_y - ch * 0.055))
            if _is_bottom and gar_y0 < lower_y0_limit:
                logger.info(
                    "catvton_color_fidelity_spatial: clamping lower mask gar_y0 %d -> %d "
                    "(waist_y=%d)",
                    gar_y0,
                    lower_y0_limit,
                    waist_y,
                )
                gar_y0 = lower_y0_limit
            gar_w = gar_x1 - gar_x0
            gar_h = gar_y1 - gar_y0
            logger.info(
                "catvton_color_fidelity_spatial: using CatVTON resized mask region=[%d,%d,%d,%d] "
                "(coverage=%.3f)",
                gar_x0,
                gar_y0,
                gar_x1,
                gar_y1,
                float((catvton_mask_np > 0.05).mean()),
            )
        else:
            change_region = estimate_catvton_garment_region_from_change(
                catvton_result=catvton_result,
                person_image=person_image,
                pose_region={"x0": bx0, "x1": bx1, "neck_y": neck_y, "waist_y": waist_y},
                garment_category=garment_category,
            )
            if change_region is not None:
                gar_x0, gar_y0, gar_x1, gar_y1 = change_region
                gar_w = gar_x1 - gar_x0
                gar_h = gar_y1 - gar_y0
                logger.info(
                    "catvton_color_fidelity_spatial: expanded garment region from CatVTON change "
                    "region=[%d,%d,%d,%d]",
                    gar_x0,
                    gar_y0,
                    gar_x1,
                    gar_y1,
                )

        # ── Step 2: 将原衣服等比缩放到目标区域（填满，不留空白）─────────
        cutout = cutout_garment_rgba(original_garment)
        gar_src = cutout.cropped.convert("RGBA")
        sw, sh = gar_src.size
        if sw < 16 or sh < 16:
            return catvton_result, {
                "engine": "catvton_color_fidelity_spatial",
                "reason": "garment_too_small",
            }

        gar_src_np = np.array(gar_src, dtype=np.float32)
        gar_src_alpha_mask = gar_src_np[:, :, 3] > 128
        if gar_src_alpha_mask.any():
            gar_src_rgb_mean = gar_src_np[gar_src_alpha_mask, :3].mean()
            gar_src_alpha_mean = gar_src_np[gar_src_alpha_mask, 3].mean()
        else:
            gar_src_rgb_mean = 0.0
            gar_src_alpha_mean = 0.0
        logger.info(
            "DEBUG [cutout]: RGB=%.2f, A=%.2f (non-transparent)",
            gar_src_rgb_mean,
            gar_src_alpha_mean,
        )

        warped_layer: Image.Image | None = None
        lower_warp_meta: WarpMetadata | None = None
        _pre_protection_rgb = 0.0

        if _is_bottom:
            warped_layer, lower_warp_meta = _build_pants_warp_layer(
                person_image=person_image,
                garment_image=original_garment,
                alpha_feather_ratio=0.0075,
                include_waistband=True,
                protect_upper_body=False,
            )
            if warped_layer.size != (cw, ch):
                src_w, src_h = warped_layer.size
                sx = cw / float(max(1, src_w))
                sy = ch / float(max(1, src_h))

                def _scale_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
                    x0, y0, x1, y1 = box
                    return (
                        _clamp_int(round(x0 * sx), 0, cw),
                        _clamp_int(round(y0 * sy), 0, ch),
                        _clamp_int(round(x1 * sx), 0, cw),
                        _clamp_int(round(y1 * sy), 0, ch),
                    )

                warped_layer = warped_layer.resize((cw, ch), Image.Resampling.LANCZOS)
                lower_warp_meta = WarpMetadata(
                    engine=lower_warp_meta.engine,
                    waistband_box=_scale_box(lower_warp_meta.waistband_box),
                    left_leg_box=_scale_box(lower_warp_meta.left_leg_box),
                    right_leg_box=_scale_box(lower_warp_meta.right_leg_box),
                    alpha_feather_px=max(
                        1,
                        int(round(lower_warp_meta.alpha_feather_px * (sx + sy) * 0.5)),
                    ),
                )
            warped_layer = _keep_significant_alpha_components(
                warped_layer,
                alpha_threshold=10,
                min_area_ratio=0.14,
                max_components=3,
            )
            lower_alpha = np.asarray(warped_layer, dtype=np.uint8)[:, :, 3]
            lower_bbox = _alpha_bbox(lower_alpha, threshold=10)
            if lower_bbox is None:
                logger.warning(
                    "catvton_color_fidelity_spatial: lower pants warp layer was empty; "
                    "falling back to resized garment"
                )
                warped_layer = None
            else:
                gar_x0, gar_y0, gar_x1, gar_y1 = lower_bbox
                gar_w = gar_x1 - gar_x0
                gar_h = gar_y1 - gar_y0
                logger.info(
                    "catvton_color_fidelity_spatial: lower branch reused pants warp layer "
                    "bbox=[%d,%d,%d,%d] engine=%s waist=%s left=%s right=%s",
                    gar_x0,
                    gar_y0,
                    gar_x1,
                    gar_y1,
                    lower_warp_meta.engine,
                    lower_warp_meta.waistband_box,
                    lower_warp_meta.left_leg_box,
                    lower_warp_meta.right_leg_box,
                )
                warped_layer_np = np.array(warped_layer, dtype=np.float32)
                warped_layer_alpha_mask = warped_layer_np[:, :, 3] > 128
                if warped_layer_alpha_mask.any():
                    warped_layer_rgb_mean = warped_layer_np[warped_layer_alpha_mask, :3].mean()
                    warped_layer_alpha_mean = warped_layer_np[warped_layer_alpha_mask, 3].mean()
                else:
                    warped_layer_rgb_mean = 0.0
                    warped_layer_alpha_mean = 0.0
                logger.info(
                    "DEBUG [lower warp layer]: RGB mean=%.2f, Alpha mean=%.2f "
                    "(in non-transparent regions)",
                    warped_layer_rgb_mean,
                    warped_layer_alpha_mean,
                )
                _pre_protection_rgb = warped_layer_rgb_mean

        if warped_layer is None:
            if _is_top or _is_skirt:
                if sw > sh * 1.3:
                    gar_src = gar_src.transpose(Image.Transpose.ROTATE_90)
                    sw, sh = gar_src.size
                    logger.info(
                        "catvton_color_fidelity_spatial: garment rotated 90? "
                        "(was wider than tall: %dx%d -> %dx%d)",
                        sh,
                        sw,
                        sw,
                        sh,
                    )

            scale_x = gar_w / float(sw)
            scale_y = gar_h / float(sh)
            scale = min(scale_x, scale_y) if catvton_mask_np is not None else max(scale_x, scale_y)
            s_w = max(2, int(sw * scale))
            s_h = max(2, int(sh * scale))

            r, g, b, a = gar_src.split()
            r_scaled = r.resize((s_w, s_h), Image.Resampling.LANCZOS)
            g_scaled = g.resize((s_w, s_h), Image.Resampling.LANCZOS)
            b_scaled = b.resize((s_w, s_h), Image.Resampling.LANCZOS)
            a_scaled = a.resize((s_w, s_h), Image.Resampling.NEAREST)
            gar_scaled = Image.merge("RGBA", (r_scaled, g_scaled, b_scaled, a_scaled))
            logger.info(
                "catvton_color_fidelity_spatial: proportional %s "
                "(target=%dx%d, garment=%dx%d, scale=%.3f -> scaled=%dx%d, "
                "body_center=(%d,%d), gar_region=[%d,%d,%d,%d])",
                "fit-to-mask" if catvton_mask_np is not None else "stretch-to-fill",
                gar_w,
                gar_h,
                sw,
                sh,
                scale,
                s_w,
                s_h,
                body_cx,
                body_cy,
                gar_x0,
                gar_y0,
                gar_x1,
                gar_y1,
            )

            gar_scaled_np = np.array(gar_scaled, dtype=np.float32)
            gar_scaled_alpha_mask = gar_scaled_np[:, :, 3] > 128
            if gar_scaled_alpha_mask.any():
                gar_scaled_rgb_mean = gar_scaled_np[gar_scaled_alpha_mask, :3].mean()
                gar_scaled_alpha_mean = gar_scaled_np[gar_scaled_alpha_mask, 3].mean()
            else:
                gar_scaled_rgb_mean = 0.0
                gar_scaled_alpha_mean = 0.0
            logger.info(
                "DEBUG [after scaling]: RGB=%.2f, A=%.2f (non-transparent)",
                gar_scaled_rgb_mean,
                gar_scaled_alpha_mean,
            )

            if kpts and s_w >= 16 and s_h >= 16:
                try:
                    from app.services.cloth_warp import TPSWarpEngine

                    tps_engine = TPSWarpEngine()
                    tps_keypoints = {}
                    _all_needed_kpts = {
                        "left_shoulder",
                        "right_shoulder",
                        "left_hip",
                        "right_hip",
                        "left_elbow",
                        "right_elbow",
                        "left_wrist",
                        "right_wrist",
                    }
                    for name in _all_needed_kpts:
                        if name in kpts:
                            tps_keypoints[name] = kpts[name]
                    _available = {
                        n: (round(v[0], 3), round(v[1], 3)) for n, v in tps_keypoints.items()
                    }
                    logger.info(
                        "DEBUG [TPS keypoints]: available=%d/%d, keys=%s, all_kpts=%s",
                        len(tps_keypoints),
                        len(_all_needed_kpts),
                        _available,
                        {n: (n in kpts) for n in _all_needed_kpts},
                    )
                    if len(tps_keypoints) >= 4:
                        gar_rgb = gar_scaled.convert("RGB")
                        original_alpha = gar_scaled.split()[3]

                        gar_before_np = np.array(gar_scaled, dtype=np.float32)
                        gar_before_alpha_mask = gar_before_np[:, :, 3] > 128
                        if gar_before_alpha_mask.any():
                            gar_before_rgb_mean = gar_before_np[gar_before_alpha_mask, :3].mean()
                            gar_before_alpha_mean = gar_before_np[gar_before_alpha_mask, 3].mean()
                            gar_before_alpha_std = gar_before_np[gar_before_alpha_mask, 3].std()
                        else:
                            gar_before_rgb_mean = 0.0
                            gar_before_alpha_mean = 0.0
                            gar_before_alpha_std = 0.0
                        logger.info(
                            "DEBUG [BEFORE TPS warp]: RGB=%.2f, Alpha mean=%.2f, Alpha std=%.2f, "
                            "Alpha min/max=[%.0f,%.0f], original_alpha mean=%.2f",
                            gar_before_rgb_mean,
                            gar_before_alpha_mean,
                            gar_before_alpha_std,
                            gar_before_np[:, :, 3].min(),
                            gar_before_np[:, :, 3].max(),
                            np.array(original_alpha, dtype=np.float32).mean(),
                        )

                        gar_warped = tps_engine.warp(
                            gar_rgb,
                            tps_keypoints,
                            (gar_w, gar_h),
                            cloth_type="upper" if _is_top else "bottom",
                        )

                        alpha_resized = original_alpha.resize(
                            (gar_w, gar_h), Image.Resampling.NEAREST
                        )
                        gar_scaled = Image.merge("RGBA", (gar_warped, alpha_resized))

                        alpha_resized_np = np.array(alpha_resized, dtype=np.float32)
                        logger.info(
                            "DEBUG [alpha_resized]: size=%dx%d, mean=%.2f, min/max=[%.0f,%.0f]",
                            gar_w,
                            gar_h,
                            alpha_resized_np.mean(),
                            alpha_resized_np.min(),
                            alpha_resized_np.max(),
                        )

                        logger.info(
                            "catvton_color_fidelity_spatial: TPS warp applied "
                            "with %d keypoints (output=%dx%d), alpha preserved from original",
                            len(tps_keypoints),
                            gar_w,
                            gar_h,
                        )

                        gar_warped_np = np.array(gar_scaled, dtype=np.float32)
                        gar_warped_alpha_mask = gar_warped_np[:, :, 3] > 128
                        if gar_warped_alpha_mask.any():
                            gar_warped_rgb_mean = gar_warped_np[gar_warped_alpha_mask, :3].mean()
                            gar_warped_alpha_mean = gar_warped_np[gar_warped_alpha_mask, 3].mean()
                            gar_warped_alpha_std = gar_warped_np[gar_warped_alpha_mask, 3].std()
                        else:
                            gar_warped_rgb_mean = 0.0
                            gar_warped_alpha_mean = 0.0
                            gar_warped_alpha_std = 0.0
                        logger.info(
                            "DEBUG [after TPS with alpha fix]: RGB=%.2f, Alpha mean=%.2f, "
                            "Alpha std=%.2f (non-transparent regions)",
                            gar_warped_rgb_mean,
                            gar_warped_alpha_mean,
                            gar_warped_alpha_std,
                        )
                except Exception as tps_err:
                    logger.debug(
                        "catvton_color_fidelity_spatial: TPS warp failed (%s), "
                        "using scaled garment",
                        tps_err,
                    )

            paste_x = max(0, min(gar_x0, cw - gar_w))
            paste_y = max(0, min(gar_y0, ch - gar_h))

            if paste_x + gar_w > cw:
                gar_w = cw - paste_x
            if paste_y + gar_h > ch:
                gar_h = ch - paste_y
            if gar_w < 2 or gar_h < 2:
                return catvton_result, {
                    "engine": "catvton_color_fidelity_spatial",
                    "reason": "fit_too_small",
                }

            gar_fitted = gar_scaled.crop((0, 0, gar_w, gar_h))
            warped_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            warped_layer.paste(gar_fitted, (paste_x, paste_y), gar_fitted)

            warped_layer_np = np.array(warped_layer, dtype=np.float32)
            warped_layer_alpha_mask = warped_layer_np[:, :, 3] > 128
            if warped_layer_alpha_mask.any():
                warped_layer_rgb_mean = warped_layer_np[warped_layer_alpha_mask, :3].mean()
                warped_layer_alpha_mean = warped_layer_np[warped_layer_alpha_mask, 3].mean()
            else:
                warped_layer_rgb_mean = 0.0
                warped_layer_alpha_mean = 0.0
            logger.info(
                "DEBUG [after paste]: RGB mean=%.2f, Alpha mean=%.2f (in non-transparent regions)",
                warped_layer_rgb_mean,
                warped_layer_alpha_mean,
            )

            _pre_protection_rgb = warped_layer_rgb_mean

            feather_px = max(2, int(min(cw, ch) * (0.0075 if _is_bottom else 0.012)))
            warped_layer = _feather_alpha(warped_layer, radius_px=feather_px)

            warped_layer_feathered_np = np.array(warped_layer, dtype=np.float32)
            warped_layer_feathered_alpha_mask = warped_layer_feathered_np[:, :, 3] > 128
            if warped_layer_feathered_alpha_mask.any():
                warped_layer_feathered_rgb_mean = warped_layer_feathered_np[
                    warped_layer_feathered_alpha_mask, :3
                ].mean()
                warped_layer_feathered_alpha_mean = warped_layer_feathered_np[
                    warped_layer_feathered_alpha_mask, 3
                ].mean()
            else:
                warped_layer_feathered_rgb_mean = 0.0
                warped_layer_feathered_alpha_mean = 0.0
            logger.info(
                "DEBUG [after feathering]: RGB mean=%.2f, Alpha mean=%.2f "
                "(in non-transparent regions)",
                warped_layer_feathered_rgb_mean,
                warped_layer_feathered_alpha_mean,
            )

        protect = _make_face_protect_mask(cw, ch, face_box, neck_y)

        # 下装保护：保护上半身和鞋子区域（_is_bottom 专享）
        if _is_bottom:
            lower_protect = _make_lower_body_protect_mask(cw, ch, waist_y, ankle_y)
            protect = ImageChops.multiply(protect, lower_protect)
            logger.info(
                "catvton_color_fidelity_spatial: applied lower-body protect mask "
                "(waist_y=%d, ankle_y=%s)",
                waist_y,
                ankle_y,
            )

        # 手部：用 wrist 关键点估算手部区域，防止衣物覆盖手部
        if kpts:
            for wrist_name in ("left_wrist", "right_wrist"):
                if wrist_name in kpts:
                    wx_n, wy_n = kpts[wrist_name]
                    wx_px = int(wx_n * cw)
                    wy_px = int(wy_n * ch)
                    # 手部保护半径：图像宽度的 10%
                    r = max(8, int(cw * 0.10))
                    protect.paste(
                        0,
                        (
                            max(0, wx_px - r),
                            max(0, wy_px - r),
                            min(cw, wx_px + r),
                            min(ch, wy_px + r),
                        ),
                    )

        r_ch, g_ch, b_ch, a_ch = warped_layer.split()
        # 正确：对 alpha 通道应用脸手保护
        # 注意：warped_layer 已经在 Step 3 中应用了边缘羽化，其 alpha 通道已包含羽化效果
        a_ch = ImageChops.multiply(a_ch, protect)
        warped_layer = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

        # DEBUG: Log RGB and alpha stats after face/hand protection
        warped_layer_protected_np = np.array(warped_layer, dtype=np.float32)
        warped_layer_protected_alpha_mask = warped_layer_protected_np[:, :, 3] > 128
        if warped_layer_protected_alpha_mask.any():
            warped_layer_protected_rgb_mean = warped_layer_protected_np[
                warped_layer_protected_alpha_mask, :3
            ].mean()
            warped_layer_protected_alpha_mean = warped_layer_protected_np[
                warped_layer_protected_alpha_mask, 3
            ].mean()
        else:
            warped_layer_protected_rgb_mean = 0.0
            warped_layer_protected_alpha_mean = 0.0
        logger.info(
            "DEBUG [after protection]: RGB=%.2f, A=%.2f " "(non-transparent)",
            warped_layer_protected_rgb_mean,
            warped_layer_protected_alpha_mean,
        )
        # Also log overall stats (including transparent regions)
        logger.info(
            "DEBUG [after face/hand protection - ALL pixels]: RGB mean=%.2f, Alpha mean=%.2f",
            warped_layer_protected_np[:, :, :3].mean(),
            warped_layer_protected_np[:, :, 3].mean(),
        )

        # ── Step 5: 颜色保真验证 ─────────────────────────────────────
        # 在混合前验证 warped_layer 的颜色质量
        layer_np = np.array(warped_layer, dtype=np.float32)

        # 修复：如果脸部保护导致 alpha 过低（衣服像素被过度清除），使用保护前的原始像素
        # 这确保颜色保真在脸部保护区域也能生效
        if _pre_protection_rgb > 100 and layer_np[:, :, 3].mean() < 50:
            logger.warning(
                "catvton_color_fidelity_spatial: face protection degraded alpha "
                "(before=%.2f, after=%.2f). Keeping protected layer.",
                _pre_protection_rgb,
                layer_np[:, :, 3].mean(),
            )

        spatial_pattern_score = _detect_pattern_strength(original_garment)
        lower_denim_like = bool(_is_bottom and _is_denim_like_garment(original_garment))
        lower_warp_qc = (
            _assess_lower_warp_layer_qc(layer_np, lower_warp_meta=lower_warp_meta)
            if _is_bottom
            else {"passed": True, "reasons": []}
        )
        lower_texture_qc_accepted = bool(
            _is_bottom
            and _accept_lower_structure_qc_for_texture(
                lower_warp_qc,
                denim_like=lower_denim_like,
            )
        )
        lower_conservative_color_only = bool(
            _is_bottom and (lower_denim_like or not lower_warp_qc.get("passed", False))
        )
        if lower_conservative_color_only:
            logger.info(
                "catvton_color_fidelity_spatial: lower spatial overlay downgraded "
                "to conservative color transfer (denim=%s, qc=%s)",
                lower_denim_like,
                lower_warp_qc,
            )
        catvton_roi = result_np[
            max(0, gar_y0) : min(result_np.shape[0], gar_y1),
            max(0, gar_x0) : min(result_np.shape[1], gar_x1),
        ]
        catvton_has_existing_motif = False
        if catvton_roi.size > 0:
            hsv_roi = cv2.cvtColor(catvton_roi.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(
                np.float32
            )
            sat_roi = hsv_roi[:, :, 1]
            val_roi = hsv_roi[:, :, 2]
            colorful_roi = (sat_roi > 38) & (val_roi > 35)
            catvton_has_existing_motif = float(colorful_roi.mean()) > 0.015

        layer_alpha = layer_np[:, :, 3] / 255.0
        motif_gate = np.ones_like(layer_alpha, dtype=np.float32)
        motif_source = layer_np[:, :, 3] > 64
        motif_pixels = layer_np[motif_source, :3]
        motif_coverage = 0.0
        light_pattern_base = False
        needs_light_base_rescue = False
        catvton_changed_value_mean = 0.0
        source_value_mean = 0.0
        source_sat_mean = 0.0
        dark_pattern_base = False
        motif_dilate_iterations = 1
        motif_detail_enhance_strength = 0.0
        base_rgb_for_enhance: np.ndarray | None = None
        pale_artifact_removed_ratio = 0.0
        if motif_pixels.size > 0:
            hsv_source = cv2.cvtColor(
                motif_pixels.reshape(-1, 1, 3).astype(np.uint8),
                cv2.COLOR_RGB2HSV,
            ).reshape(-1, 3)
            source_sat_mean = float(hsv_source[:, 1].mean())
            source_value_mean = float(hsv_source[:, 2].mean())
            light_pattern_base = (
                spatial_pattern_score > 0.40
                and source_value_mean > 165.0
                and source_sat_mean < 85.0
            )
            dark_pattern_base = (
                spatial_pattern_score > 0.40
                and source_value_mean < 115.0
                and source_sat_mean < 95.0
            )
            if light_pattern_base and catvton_roi.size > 0:
                try:
                    person_rescue = np.array(
                        person_image.convert("RGB").resize((cw, ch), Image.Resampling.BILINEAR),
                        dtype=np.float32,
                    )
                    diff_rescue = np.abs(result_np - person_rescue).mean(axis=2)
                    changed_rescue = diff_rescue > max(10.0, float(np.percentile(diff_rescue, 68)))
                    roi_changed = changed_rescue[
                        max(0, gar_y0) : min(result_np.shape[0], gar_y1),
                        max(0, gar_x0) : min(result_np.shape[1], gar_x1),
                    ]
                    changed_values = (
                        val_roi[roi_changed] if roi_changed.shape == val_roi.shape else []
                    )
                    if len(changed_values) > 0:
                        catvton_changed_value_mean = float(np.mean(changed_values))
                        needs_light_base_rescue = catvton_changed_value_mean < 200.0
                except Exception:
                    needs_light_base_rescue = False

            base_rgb = np.median(motif_pixels, axis=0)
            base_rgb_for_enhance = base_rgb.astype(np.float32)
            color_dist = np.linalg.norm(layer_np[:, :, :3] - base_rgb, axis=2)
            source_dist = color_dist[motif_source]
            adaptive_threshold = 28.0
            if source_dist.size and not catvton_has_existing_motif:
                adaptive_threshold = float(
                    np.clip(np.percentile(source_dist, 82) * 0.55, 10.0, 28.0)
                )
            motif_candidate = (color_dist > adaptive_threshold) & motif_source

            if not catvton_has_existing_motif and spatial_pattern_score <= 0.40:
                gray_layer = cv2.cvtColor(layer_np[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2GRAY)
                gy, gx = np.gradient(gray_layer.astype(np.float32))
                grad = np.sqrt(gx * gx + gy * gy)
                source_grad = grad[motif_source]
                if source_grad.size:
                    edge_threshold = float(
                        max(6.0, min(18.0, np.percentile(source_grad, 88) * 0.45))
                    )
                    motif_candidate |= (grad > edge_threshold) & motif_source

            motif_candidate = cv2.morphologyEx(
                motif_candidate.astype(np.uint8),
                cv2.MORPH_OPEN,
                np.ones((3, 3), dtype=np.uint8),
            ).astype(bool)
            motif_candidate, pale_artifact_removed_ratio = (
                _suppress_light_fidelity_artifact_candidates(
                    motif_candidate,
                    layer_np[:, :, :3],
                    motif_source,
                    gar_x0=gar_x0,
                    gar_y0=gar_y0,
                    gar_x1=gar_x1,
                    gar_y1=gar_y1,
                    body_cx=body_cx,
                    light_pattern_base=light_pattern_base,
                )
            )
            if pale_artifact_removed_ratio > 0.0:
                logger.info(
                    "catvton_color_fidelity_spatial: suppressed off-center pale blocks "
                    "(coverage=%.4f)",
                    pale_artifact_removed_ratio,
                )
            motif_coverage = (
                float(motif_candidate[motif_source].mean()) if motif_source.any() else 0.0
            )
            if (
                spatial_pattern_score > 0.40
                and catvton_mask_np is None
                and not needs_light_base_rescue
                and (
                    motif_coverage > 0.18
                    or (spatial_pattern_score > 0.70 and motif_coverage > 0.10)
                )
            ):
                grid_y, grid_x = np.indices(motif_candidate.shape)
                torso_center_x = (gar_x0 + gar_x1) / 2.0
                central_half_w = max(36.0, (gar_x1 - gar_x0) * 0.30)
                torso_y0 = gar_y0 + (gar_y1 - gar_y0) * 0.10
                torso_y1 = gar_y0 + (gar_y1 - gar_y0) * 0.95
                central_torso_band = (
                    (np.abs(grid_x - torso_center_x) <= central_half_w)
                    & (grid_y >= torso_y0)
                    & (grid_y <= torso_y1)
                )

                labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
                    motif_candidate.astype(np.uint8), 8
                )
                filtered_candidate = motif_candidate & central_torso_band
                if labels_count > 1:
                    component_filtered = np.zeros_like(motif_candidate, dtype=bool)
                    for label_idx in range(1, labels_count):
                        area = int(stats[label_idx, cv2.CC_STAT_AREA])
                        if area <= 0:
                            continue
                        component = labels == label_idx
                        central_overlap = float((component & central_torso_band).sum()) / float(
                            area
                        )
                        if central_overlap >= 0.25:
                            component_filtered |= component & central_torso_band

                    if component_filtered.any():
                        filtered_candidate = component_filtered

                if filtered_candidate.any():
                    logger.info(
                        "catvton_color_fidelity_spatial: constrained high-coverage motif "
                        "to central torso band (coverage %.3f -> %.3f, existing_motif=%s)",
                        motif_coverage,
                        (
                            float(filtered_candidate[motif_source].mean())
                            if motif_source.any()
                            else 0.0
                        ),
                        catvton_has_existing_motif,
                    )
                    motif_candidate = filtered_candidate
                    motif_coverage = (
                        float(motif_candidate[motif_source].mean()) if motif_source.any() else 0.0
                    )
            if catvton_mask_np is not None and spatial_pattern_score > 0.45:
                motif_dilate_iterations = 1 if _is_bottom else 2
            if 0.002 <= motif_coverage <= 0.45:
                motif_candidate = cv2.dilate(
                    motif_candidate.astype(np.uint8),
                    np.ones((3, 3), dtype=np.uint8),
                    iterations=motif_dilate_iterations,
                ).astype(bool)
                motif_candidate, pale_artifact_removed_after_dilate = (
                    _suppress_light_fidelity_artifact_candidates(
                        motif_candidate,
                        layer_np[:, :, :3],
                        motif_source,
                        gar_x0=gar_x0,
                        gar_y0=gar_y0,
                        gar_x1=gar_x1,
                        gar_y1=gar_y1,
                        body_cx=body_cx,
                        light_pattern_base=light_pattern_base,
                    )
                )
                pale_artifact_removed_ratio += pale_artifact_removed_after_dilate
                motif_gate = motif_candidate.astype(np.float32)
                logger.info(
                    "catvton_color_fidelity_spatial: using motif-only fidelity "
                    "(coverage=%.3f, dilate=%d)",
                    motif_coverage,
                    motif_dilate_iterations,
                )

        strong_dark_lower_pattern = bool(
            _is_bottom
            and dark_pattern_base
            and spatial_pattern_score > 0.70
            and source_value_mean < 90.0
        )
        if (
            motif_pixels.size > 0
            and motif_gate.max() > 0.0
            and (light_pattern_base or dark_pattern_base)
            and spatial_pattern_score > 0.45
        ):
            if light_pattern_base:
                motif_detail_enhance_strength = 0.30
            elif strong_dark_lower_pattern:
                motif_detail_enhance_strength = 0.36
            else:
                motif_detail_enhance_strength = 0.24
            rgb_layer = layer_np[:, :, :3].astype(np.float32)
            blur_layer = cv2.GaussianBlur(rgb_layer, (0, 0), 0.85)
            sharpened_layer = np.clip(
                rgb_layer + (rgb_layer - blur_layer) * 0.65,
                0,
                255,
            )
            if base_rgb_for_enhance is not None:
                contrast_layer = np.clip(
                    base_rgb_for_enhance + (sharpened_layer - base_rgb_for_enhance) * 1.22,
                    0,
                    255,
                )
            else:
                contrast_layer = sharpened_layer

            hsv_layer = cv2.cvtColor(
                contrast_layer.astype(np.uint8),
                cv2.COLOR_RGB2HSV,
            ).astype(np.float32)
            sat_gain = 1.12 if light_pattern_base else 1.08
            hsv_layer[:, :, 1] = np.clip(hsv_layer[:, :, 1] * sat_gain, 0, 255)
            enhanced_layer = cv2.cvtColor(
                hsv_layer.astype(np.uint8),
                cv2.COLOR_HSV2RGB,
            ).astype(np.float32)
            detail_gate = np.clip(motif_gate, 0.0, 1.0) * (layer_alpha > 0.12).astype(np.float32)
            if catvton_mask_np is not None:
                detail_gate *= catvton_mask_np
            detail_gate = (detail_gate * motif_detail_enhance_strength)[:, :, np.newaxis]
            layer_np[:, :, :3] = enhanced_layer * detail_gate + layer_np[:, :, :3] * (
                1.0 - detail_gate
            )
            warped_layer = Image.fromarray(np.clip(layer_np, 0, 255).astype(np.uint8), mode="RGBA")
            logger.info(
                "catvton_color_fidelity_spatial: motif detail enhancement applied "
                "(strength=%.2f, light=%s, dark=%s)",
                motif_detail_enhance_strength,
                light_pattern_base,
                dark_pattern_base,
            )

        _nt_mask = layer_np[:, :, 3] > 128
        if _nt_mask.any():
            _nt_rgb_mean = layer_np[_nt_mask, :3].mean()
        else:
            _nt_rgb_mean = 0.0

        logger.info(
            "catvton_color_fidelity_spatial: warped_layer stats - "
            "R mean=%.2f, G mean=%.2f, B mean=%.2f, A mean=%.2f, "
            "R min/max=[%.0f,%.0f], G min/max=[%.0f,%.0f], "
            "B min/max=[%.0f,%.0f]",
            layer_np[:, :, 0].mean(),
            layer_np[:, :, 1].mean(),
            layer_np[:, :, 2].mean(),
            layer_np[:, :, 3].mean(),
            layer_np[:, :, 0].min(),
            layer_np[:, :, 0].max(),
            layer_np[:, :, 1].min(),
            layer_np[:, :, 1].max(),
            layer_np[:, :, 2].min(),
            layer_np[:, :, 2].max(),
        )

        if _nt_rgb_mean < 20.0 and _nt_mask.any():
            logger.warning(
                "catvton_color_fidelity_spatial: warped_layer RGB "
                "mean=%.2f < 20 in non-transparent regions. "
                "Color fidelity may be compromised.",
                _nt_rgb_mean,
            )
        elif not _nt_mask.any():
            logger.warning(
                "catvton_color_fidelity_spatial: warped_layer has "
                "no non-transparent pixels. Skipping blend."
            )
            return catvton_result, {
                "engine": "catvton_color_fidelity_spatial",
                "reason": "empty_warped_layer",
            }

        # ── Step 5b: 直接像素级保真混合 ─────────────────────────────
        # 核心：用原衣服像素替换 CatVTON 生成的颜色，保留空间分布

        person_for_mask = np.array(
            person_image.convert("RGB").resize((cw, ch), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        catvton_for_mask = np.array(cr, dtype=np.float32)
        diff_for_mask = np.abs(catvton_for_mask - person_for_mask).mean(axis=2)
        wear_shape_np: np.ndarray | None = None

        hsv_person = cv2.cvtColor(person_for_mask.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(
            np.float32
        )
        sat_person = hsv_person[:, :, 1]
        val_person = hsv_person[:, :, 2]
        near_white_bg = (val_person > 235) & (sat_person < 35)

        r_person = person_for_mask[:, :, 0]
        g_person = person_for_mask[:, :, 1]
        b_person = person_for_mask[:, :, 2]
        skin_like = (
            (r_person > 150)
            & (g_person > 95)
            & (b_person > 70)
            & (r_person > g_person + 10)
            & (g_person > b_person + 5)
        )
        protected_by_mask = np.array(protect, dtype=np.uint8) < 200
        protected_until_y = 0
        if _is_top:
            protected_until_y = max(0, int(max(neck_y + ch * 0.02, ch * 0.22)))
            if catvton_mask_np is not None and face_box is not None:
                _fx, fy, _fw, fh = face_box
                face_guard_bottom = int(fy + fh + fh * 0.25)
                protected_until_y = min(protected_until_y, max(0, face_guard_bottom))
            protected_by_mask[:protected_until_y, :] = True

        changed_garment = diff_for_mask > max(10.0, float(np.percentile(diff_for_mask, 68)))
        lower_layer_gap_fill_ratio = 0.0
        lower_texture_support_ratio = 0.0
        lower_filled_texture_support: np.ndarray | None = None
        lower_original_layer_alpha = layer_alpha.copy()
        if _is_bottom and catvton_mask_np is not None:
            grid_y, grid_x = np.indices(layer_alpha.shape)
            lower_bbox_mask = (
                (grid_x >= gar_x0) & (grid_x < gar_x1) & (grid_y >= gar_y0) & (grid_y < gar_y1)
            )
            lower_mask_core = _keep_largest_mask_component(catvton_mask_np > 0.08)
            if not lower_mask_core.any():
                lower_mask_core = catvton_mask_np > 0.08
            lower_fill_mask = (
                lower_mask_core | (lower_bbox_mask & changed_garment)
            ) & ~protected_by_mask
            layer_np, lower_layer_gap_fill_ratio = _fill_lower_layer_gaps_from_fabric(
                layer_np,
                lower_fill_mask,
                min_source_alpha=0.12,
            )
            if lower_layer_gap_fill_ratio > 0.0:
                lower_filled_texture_support = lower_fill_mask.copy()
                warped_layer = Image.fromarray(
                    np.clip(layer_np, 0, 255).astype(np.uint8),
                    mode="RGBA",
                )
                layer_alpha = layer_np[:, :, 3] / 255.0
        if catvton_mask_np is not None and _is_top:
            try:
                hsv_catvton = cv2.cvtColor(
                    catvton_for_mask.astype(np.uint8),
                    cv2.COLOR_RGB2HSV,
                ).astype(np.float32)
                sat_catvton = hsv_catvton[:, :, 1]
                val_catvton = hsv_catvton[:, :, 2]
                mask_core = catvton_mask_np > 0.08
                mask_diffs = diff_for_mask[mask_core]
                if mask_diffs.size:
                    diff_gate = float(max(7.0, min(18.0, np.percentile(mask_diffs, 45) * 0.65)))
                else:
                    diff_gate = 10.0
                raw_background_like = (
                    (val_catvton > 238) & (sat_catvton < 36) & (diff_for_mask < diff_gate * 1.6)
                )
                raw_garment_like = (
                    mask_core & ~raw_background_like & ~skin_like & ~protected_by_mask
                )
                raw_garment_like |= (
                    mask_core & (diff_for_mask > diff_gate) & ~skin_like & ~protected_by_mask
                )
                wear_u8 = raw_garment_like.astype(np.uint8)
                wear_u8 = cv2.morphologyEx(
                    wear_u8,
                    cv2.MORPH_OPEN,
                    np.ones((3, 3), dtype=np.uint8),
                )
                wear_u8 = cv2.morphologyEx(
                    wear_u8,
                    cv2.MORPH_CLOSE,
                    np.ones((9, 9), dtype=np.uint8),
                )
                labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
                    wear_u8,
                    8,
                )
                if labels_count > 1:
                    areas = stats[1:, cv2.CC_STAT_AREA]
                    keep = int(np.argmax(areas) + 1)
                    min_keep_area = max(32, int(areas.max() * 0.18))
                    kept = labels == keep
                    for label_idx in range(1, labels_count):
                        if int(stats[label_idx, cv2.CC_STAT_AREA]) >= min_keep_area:
                            kept |= labels == label_idx
                    wear_u8 = kept.astype(np.uint8)
                if int(wear_u8.sum()) >= 256:
                    wear_shape_np = cv2.GaussianBlur(wear_u8.astype(np.float32), (9, 9), 0)
                    wear_shape_np = np.clip(wear_shape_np, 0.0, 1.0)
                    logger.info(
                        "catvton_color_fidelity_spatial: extracted raw-result wear shape "
                        "(coverage=%.3f, diff_gate=%.2f)",
                        float((wear_shape_np > 0.08).mean()),
                        diff_gate,
                    )
            except Exception as wear_err:
                logger.debug(
                    "catvton_color_fidelity_spatial: raw-result wear shape failed (%s)",
                    wear_err,
                )

        # The raw-result wear shape is useful for diagnostics, but it is not reliable
        # enough as a clipping mask: on wide product tees it still includes the
        # product sleeves/shoulders. Keep the saved debug image, but do not let it
        # participate in blending.
        wear_shape_for_debug = wear_shape_np
        wear_shape_np = None

        grid_y, grid_x = np.indices(layer_alpha.shape)
        torso_y0 = max(protected_until_y, int(gar_y0 + gar_h * 0.10))
        torso_y1 = min(ch, int(gar_y1 - gar_h * 0.02))
        torso_h = max(1, torso_y1 - torso_y0)
        torso_rel_y = np.clip((grid_y - torso_y0) / float(torso_h), 0.0, 1.0)
        torso_center_x = float(body_cx)
        top_half_w = max(28.0, gar_w * 0.31)
        bottom_half_w = max(top_half_w, gar_w * 0.38)
        torso_half_w = top_half_w * (1.0 - torso_rel_y) + bottom_half_w * torso_rel_y
        torso_fit_bool = (
            (grid_y >= torso_y0)
            & (grid_y <= torso_y1)
            & (np.abs(grid_x - torso_center_x) <= torso_half_w)
        )
        torso_fit_mask = cv2.GaussianBlur(
            torso_fit_bool.astype(np.float32),
            (9, 9),
            0,
        )
        torso_fit_mask = np.clip(torso_fit_mask, 0.0, 1.0)
        if catvton_mask_np is not None:
            torso_fit_mask *= catvton_mask_np
        if _is_top and spatial_pattern_score > 0.40:
            motif_gate *= torso_fit_mask

        garment_layer_present = layer_alpha > 0.12
        fidelity_clip_mask = catvton_mask_np
        if _is_bottom:
            fidelity_clip_mask = _build_lower_fidelity_clip_mask(
                catvton_mask_np=catvton_mask_np,
                changed_garment=changed_garment,
                garment_layer_present=garment_layer_present,
                protected_by_mask=protected_by_mask,
                layer_alpha=layer_alpha,
                left_leg_box=(
                    lower_warp_meta.left_leg_box if lower_warp_meta is not None else None
                ),
                right_leg_box=(
                    lower_warp_meta.right_leg_box if lower_warp_meta is not None else None
                ),
            )
        mask_guided_light_pattern = (
            catvton_mask_np is not None
            and light_pattern_base
            and spatial_pattern_score > 0.55
            and motif_coverage >= 0.06
        )
        light_base_repaint = light_pattern_base and (
            needs_light_base_rescue or not catvton_has_existing_motif or mask_guided_light_pattern
        )
        dark_base_repaint = dark_pattern_base and spatial_pattern_score > 0.45
        lower_body_repaint = (
            _is_bottom and spatial_pattern_score > 0.45 and not lower_conservative_color_only
        )
        # Original-person white areas include studio walls and white pants, but an upper
        # garment can legitimately cover part of that area in the generated result
        # (sleeves/upper chest). Keep protecting true background, while allowing pixels
        # that both CatVTON changed and the warped garment layer covers.
        allow_generated_on_white = (
            changed_garment
            & garment_layer_present
            & ((not catvton_has_existing_motif) or needs_light_base_rescue)
        )
        protected_subject = (
            skin_like | protected_by_mask | (near_white_bg & ~allow_generated_on_white)
        )
        motif_allowed = (changed_garment | garment_layer_present) & ~protected_subject
        base_allowed = np.zeros_like(motif_allowed, dtype=bool)
        if light_base_repaint:
            # Light patterned shirts need a base-color pass as well as the motif pass.
            # CatVTON often turns pale printed tees into flat gray, so allow the
            # warped shirt layer itself to softly recolor the generated garment,
            # but only on the front torso. Product-image sleeves/shoulders must not
            # become a second translucent shirt layer.
            light_base_allowed = garment_layer_present & ~skin_like & ~protected_by_mask
            light_base_allowed &= torso_fit_mask > 0.08
            if not needs_light_base_rescue:
                light_base_allowed &= changed_garment | ~near_white_bg
            base_allowed |= light_base_allowed
        if dark_base_repaint:
            # Dark patterned shirts need a subtle fabric pass so tiny chest prints
            # are not the only surviving pixels. The CatVTON mask still clips this.
            dark_base_allowed = garment_layer_present & ~skin_like & ~protected_by_mask
            dark_base_allowed &= torso_fit_mask > 0.08
            base_allowed |= dark_base_allowed
        if lower_body_repaint:
            # Lower garments still need some fabric/detail recovery, but only
            # inside the real warped-layer coverage. Do not fabricate side panels
            # outside the true warp silhouette, or plaid/stripe products produce
            # translucent ghosting on both sides.
            lower_base_allowed = garment_layer_present & ~skin_like & ~protected_by_mask
            if fidelity_clip_mask is not None:
                lower_base_allowed &= fidelity_clip_mask > 0.08
            if catvton_mask_np is not None:
                lower_base_shape = cv2.dilate(
                    (catvton_mask_np > 0.08).astype(np.uint8),
                    np.ones((5, 9), dtype=np.uint8),
                    iterations=1,
                ).astype(bool)
                lower_base_allowed &= lower_base_shape
            else:
                lower_base_allowed &= garment_layer_present
            base_allowed |= lower_base_allowed
        fallback_base_repaint = (
            motif_pixels.size > 0
            and not catvton_has_existing_motif
            and spatial_pattern_score <= 0.40
        )
        if fallback_base_repaint:
            fallback_base_allowed = garment_layer_present & ~skin_like & ~protected_by_mask
            fallback_base_allowed &= changed_garment | ~near_white_bg
            base_allowed |= fallback_base_allowed
        motif_allowed = cv2.morphologyEx(
            motif_allowed.astype(np.uint8),
            cv2.MORPH_OPEN,
            np.ones((3, 3), dtype=np.uint8),
        ).astype(bool)
        if base_allowed.any():
            base_allowed = cv2.morphologyEx(
                base_allowed.astype(np.uint8),
                cv2.MORPH_OPEN,
                np.ones((5, 5), dtype=np.uint8),
            ).astype(bool)
            base_allowed = cv2.morphologyEx(
                base_allowed.astype(np.uint8),
                cv2.MORPH_CLOSE,
                np.ones((11, 11), dtype=np.uint8),
            ).astype(bool)
        if fidelity_clip_mask is not None:
            motif_allowed &= fidelity_clip_mask > 0.08
            base_allowed &= fidelity_clip_mask > 0.08
        if lower_conservative_color_only:
            if lower_texture_qc_accepted:
                # Keep a narrow motif-only pass for denim false positives so the
                # lower garment does not lose all texture fidelity.
                motif_allowed &= garment_layer_present
                base_allowed &= False
            else:
                motif_allowed &= False
                base_allowed &= False
        fidelity_allowed = motif_allowed | base_allowed
        base_fidelity_strength = 0.0
        if light_base_repaint:
            if needs_light_base_rescue:
                base_fidelity_strength = 0.16
            elif mask_guided_light_pattern and catvton_has_existing_motif:
                base_fidelity_strength = 0.12
            else:
                base_fidelity_strength = 0.14
        elif lower_body_repaint:
            if source_value_mean > 120.0:
                base_fidelity_strength = 0.82
            else:
                if strong_dark_lower_pattern:
                    base_fidelity_strength = 0.62
                else:
                    base_fidelity_strength = 0.48 if dark_pattern_base else 0.42
        elif dark_base_repaint:
            base_fidelity_strength = 0.12
        elif (
            motif_pixels.size > 0
            and not catvton_has_existing_motif
            and spatial_pattern_score <= 0.40
        ):
            hsv_motif = cv2.cvtColor(
                motif_pixels.reshape(-1, 1, 3).astype(np.uint8),
                cv2.COLOR_RGB2HSV,
            ).reshape(-1, 3)
            value_mean = float(hsv_motif[:, 2].mean())
            sat_mean = float(hsv_motif[:, 1].mean())
            if value_mean < 115:
                base_fidelity_strength = 0.35
            elif value_mean > 190 and sat_mean < 65:
                base_fidelity_strength = 0.12
            else:
                base_fidelity_strength = 0.22

        base_repaint_gate = (
            cv2.GaussianBlur(torso_fit_mask.astype(np.float32), (31, 31), 0)
            if light_base_repaint or dark_base_repaint
            else (
                np.ones_like(torso_fit_mask, dtype=np.float32)
                if base_allowed.any()
                else np.zeros_like(torso_fit_mask, dtype=np.float32)
            )
        )
        base_repaint_gate = np.clip(base_repaint_gate, 0.0, 1.0)
        if fidelity_clip_mask is not None:
            base_repaint_gate *= fidelity_clip_mask
        if lower_body_repaint:
            base_repaint_gate *= np.clip(1.0 - motif_gate * 0.20, 0.72, 1.0)
        else:
            base_repaint_gate *= np.clip(1.0 - motif_gate * 0.75, 0.18, 1.0)
        if light_base_repaint:
            target_blend_strength = 0.78 if needs_light_base_rescue else 0.74
            blend_fidelity_strength = max(float(fidelity_strength), target_blend_strength)
        elif lower_body_repaint:
            blend_fidelity_strength = max(0.72, min(float(fidelity_strength), 0.82))
        elif lower_conservative_color_only:
            blend_fidelity_strength = min(float(fidelity_strength), 0.28)
        else:
            blend_fidelity_strength = float(fidelity_strength)
        motif_blend_strength = (
            max(float(fidelity_strength), 0.92) if light_pattern_base else blend_fidelity_strength
        )
        effective_gate = motif_gate
        motif_strength = (
            layer_alpha * motif_blend_strength * motif_allowed.astype(np.float32) * effective_gate
        )
        base_strength = (
            layer_alpha
            * blend_fidelity_strength
            * base_allowed.astype(np.float32)
            * base_fidelity_strength
            * base_repaint_gate
        )
        if fidelity_clip_mask is not None:
            motif_strength *= fidelity_clip_mask
            base_strength *= fidelity_clip_mask
        strength = np.maximum(motif_strength, base_strength)
        if debug_session_dir:
            _save_fidelity_debug(
                "12a_motif_gate.png",
                _mask_debug_image(motif_gate),
                {
                    "stage": "motif_gate",
                    "motif_coverage": round(float(motif_coverage), 4),
                    "light_pattern_base": bool(light_pattern_base),
                    "light_base_repaint": bool(light_base_repaint),
                    "mask_guided_light_pattern": bool(mask_guided_light_pattern),
                    "dark_pattern_base": bool(dark_pattern_base),
                    "dark_base_repaint": bool(dark_base_repaint),
                    "lower_body_repaint": bool(lower_body_repaint),
                    "lower_denim_like": bool(lower_denim_like),
                    "lower_conservative_color_only": bool(lower_conservative_color_only),
                    "lower_texture_qc_accepted": bool(lower_texture_qc_accepted),
                    "lower_warp_qc_passed": bool(lower_warp_qc.get("passed", False)),
                    "lower_warp_qc_reasons": list(lower_warp_qc.get("reasons", [])),
                    "needs_light_base_rescue": bool(needs_light_base_rescue),
                    "motif_dilate_iterations": int(motif_dilate_iterations),
                    "motif_detail_enhance_strength": round(
                        float(motif_detail_enhance_strength),
                        4,
                    ),
                    "pale_artifact_removed_ratio": round(
                        float(pale_artifact_removed_ratio),
                        4,
                    ),
                    "protected_until_y": int(protected_until_y),
                    "torso_fit_coverage": round(float((torso_fit_mask > 0.08).mean()), 4),
                },
            )
            _save_fidelity_debug(
                "12b_fidelity_allowed.png",
                _mask_debug_image(fidelity_allowed.astype(np.float32)),
                {
                    "stage": "fidelity_allowed",
                    "coverage": round(float(fidelity_allowed.mean()), 4),
                    "changed_garment_coverage": round(float(changed_garment.mean()), 4),
                    "wear_shape_applied": False,
                    "wear_shape_coverage": (
                        round(float((wear_shape_for_debug > 0.08).mean()), 4)
                        if wear_shape_for_debug is not None
                        else None
                    ),
                    "torso_fit_coverage": round(float((torso_fit_mask > 0.08).mean()), 4),
                    "fidelity_clip_coverage": (
                        round(float((fidelity_clip_mask > 0.08).mean()), 4)
                        if fidelity_clip_mask is not None
                        else None
                    ),
                    "lower_texture_qc_accepted": bool(lower_texture_qc_accepted),
                },
            )
            _save_fidelity_debug(
                "12c_strength.png",
                _mask_debug_image(strength),
                {
                    "stage": "strength",
                    "mean": round(float(strength.mean()), 4),
                    "max": round(float(strength.max()), 4),
                    "base_fidelity_strength": round(float(base_fidelity_strength), 4),
                    "blend_fidelity_strength": round(float(blend_fidelity_strength), 4),
                    "motif_blend_strength": round(float(motif_blend_strength), 4),
                    "base_mean": round(float(base_strength.mean()), 4),
                    "base_max": round(float(base_strength.max()), 4),
                    "motif_mean": round(float(motif_strength.mean()), 4),
                    "motif_max": round(float(motif_strength.max()), 4),
                    "catvton_mask_applied": catvton_mask_np is not None,
                    "catvton_mask_coverage": (
                        round(float((catvton_mask_np > 0.08).mean()), 4)
                        if catvton_mask_np is not None
                        else None
                    ),
                    "fidelity_clip_coverage": (
                        round(float((fidelity_clip_mask > 0.08).mean()), 4)
                        if fidelity_clip_mask is not None
                        else None
                    ),
                    "wear_shape_applied": False,
                    "wear_shape_coverage": (
                        round(float((wear_shape_for_debug > 0.08).mean()), 4)
                        if wear_shape_for_debug is not None
                        else None
                    ),
                    "torso_fit_coverage": round(float((torso_fit_mask > 0.08).mean()), 4),
                    "lower_texture_qc_accepted": bool(lower_texture_qc_accepted),
                },
            )
            _save_fidelity_debug(
                "12c_base_strength.png",
                _mask_debug_image(base_strength),
                {
                    "stage": "base_strength",
                    "mean": round(float(base_strength.mean()), 4),
                    "max": round(float(base_strength.max()), 4),
                },
            )
            _save_fidelity_debug(
                "12c_motif_strength.png",
                _mask_debug_image(motif_strength),
                {
                    "stage": "motif_strength",
                    "mean": round(float(motif_strength.mean()), 4),
                    "max": round(float(motif_strength.max()), 4),
                },
            )
            _save_fidelity_debug(
                "12e_torso_fit_mask.png",
                _mask_debug_image(torso_fit_mask),
                {
                    "stage": "torso_fit_mask",
                    "coverage": round(float((torso_fit_mask > 0.08).mean()), 4),
                    "torso_y0": int(torso_y0),
                    "torso_y1": int(torso_y1),
                    "top_half_w": round(float(top_half_w), 2),
                    "bottom_half_w": round(float(bottom_half_w), 2),
                },
            )
            if wear_shape_for_debug is not None:
                _save_fidelity_debug(
                    "12f_wear_shape_rejected.png",
                    _mask_debug_image(wear_shape_for_debug),
                    {
                        "stage": "wear_shape_rejected",
                        "coverage": round(float((wear_shape_for_debug > 0.08).mean()), 4),
                    },
                )
            _save_fidelity_debug(
                "12d_warped_layer.png",
                warped_layer,
                {
                    "stage": "warped_layer",
                    "alpha_mean": round(float(layer_np[:, :, 3].mean()), 4),
                    "alpha_nonzero_coverage": round(float((layer_np[:, :, 3] > 0).mean()), 4),
                    "lower_layer_gap_fill_ratio": round(float(lower_layer_gap_fill_ratio), 4),
                    "lower_denim_like": bool(lower_denim_like),
                    "lower_conservative_color_only": bool(lower_conservative_color_only),
                    "lower_texture_qc_accepted": bool(lower_texture_qc_accepted),
                    "lower_warp_qc": lower_warp_qc,
                },
            )

        for c in range(3):
            result_np[:, :, c] = layer_np[:, :, c] * strength + result_np[:, :, c] * (
                1.0 - strength
            )
        lower_restore_ratio = 0.0
        if _is_bottom and catvton_mask_np is not None:
            lower_bbox_mask = (
                (grid_x >= gar_x0) & (grid_x < gar_x1) & (grid_y >= gar_y0) & (grid_y < gar_y1)
            )
            lower_final_support = _build_lower_texture_support_mask(
                lower_original_layer_alpha,
                protected_by_mask,
                min_alpha=0.20,
                x_pad=5,
                y_pad=6,
                row_fill_min_coverage=0.14 if strong_dark_lower_pattern else 0.18,
            )
            restore_mask = (
                ((catvton_mask_np > 0.08) | lower_bbox_mask)
                & ~lower_final_support
                & ~protected_by_mask
            )
            if restore_mask.any():
                lower_restore_ratio = float(restore_mask.sum()) / float(max(1, restore_mask.size))
                catvton_restore = catvton_for_mask.astype(np.float32)
                result_np[restore_mask, :3] = catvton_restore[restore_mask, :3]
                restore_soft = cv2.GaussianBlur(
                    restore_mask.astype(np.float32),
                    (9, 9),
                    0,
                )
                restore_soft = np.clip(restore_soft * 0.65, 0.0, 0.65)
                restore_soft[restore_mask] = 0.0
                restore_soft = restore_soft[:, :, np.newaxis]
                result_np[:, :, :3] = catvton_restore * restore_soft + result_np[:, :, :3] * (
                    1.0 - restore_soft
                )
        lower_deterministic_overlay_ratio = 0.0
        lower_unsupported_color_fill_ratio = 0.0
        lower_color_transfer_ratio = 0.0
        lower_texture_preserve_ratio = 0.0
        if _is_bottom:
            grid_y, grid_x = np.indices(layer_alpha.shape)
            lower_overlay_mask = (
                (grid_x >= gar_x0)
                & (grid_x < gar_x1)
                & (grid_y >= gar_y0)
                & (grid_y < gar_y1)
                & ~protected_by_mask
            )
            if catvton_mask_np is not None:
                lower_overlay_mask |= (catvton_mask_np > 0.08) & ~protected_by_mask
            lower_texture_support = np.zeros_like(lower_overlay_mask, dtype=bool)
            if lower_overlay_mask.any():
                catvton_restore = catvton_for_mask.astype(np.float32)
                garment_alpha = cv2.GaussianBlur(layer_alpha.astype(np.float32), (5, 5), 0)
                garment_alpha = np.clip(garment_alpha * 1.08, 0.0, 1.0)
                garment_alpha = np.where(garment_alpha > 0.16, garment_alpha, 0.0)
                lower_bbox_core = (
                    (grid_x >= gar_x0) & (grid_x < gar_x1) & (grid_y >= gar_y0) & (grid_y < gar_y1)
                )
                lower_texture_support = _build_lower_texture_support_mask(
                    lower_original_layer_alpha,
                    protected_by_mask,
                    min_alpha=0.16,
                    x_pad=5,
                    y_pad=6,
                    row_fill_min_coverage=0.14 if strong_dark_lower_pattern else 0.18,
                )
                if lower_filled_texture_support is not None:
                    lower_texture_support |= lower_filled_texture_support & ~protected_by_mask
                if strong_dark_lower_pattern and lower_texture_support.any():
                    strong_pattern_surface = (
                        cv2.dilate(
                            lower_texture_support.astype(np.uint8),
                            np.ones((23, 11), dtype=np.uint8),
                            iterations=1,
                        ).astype(bool)
                        & lower_bbox_core
                    )
                    if lower_filled_texture_support is not None:
                        strong_pattern_surface |= cv2.dilate(
                            (lower_filled_texture_support & lower_bbox_core).astype(np.uint8),
                            np.ones((17, 9), dtype=np.uint8),
                            iterations=1,
                        ).astype(bool)
                    lower_overlay_mask = strong_pattern_surface & ~protected_by_mask
                if source_value_mean > 90.0:
                    layer_value = cv2.cvtColor(
                        np.clip(layer_np[:, :, :3], 0, 255).astype(np.uint8),
                        cv2.COLOR_RGB2HSV,
                    )[:, :, 2].astype(np.float32)
                    lower_texture_support &= layer_value > max(35.0, source_value_mean * 0.35)
                lower_texture_support_ratio = float(lower_texture_support.mean())
                garment_alpha *= lower_texture_support.astype(np.float32)
                if lower_conservative_color_only:
                    garment_alpha *= 0.0
                elif lower_filled_texture_support is not None:
                    filled_support = lower_filled_texture_support & lower_texture_support
                    garment_alpha = np.where(
                        filled_support,
                        np.maximum(garment_alpha, 0.96),
                        garment_alpha,
                    )
                if strong_dark_lower_pattern:
                    garment_alpha = np.where(
                        lower_texture_support,
                        np.maximum(garment_alpha, 0.82),
                        garment_alpha,
                    )
                if not lower_conservative_color_only:
                    garment_alpha_3 = garment_alpha[:, :, np.newaxis]
                    deterministic = layer_np[:, :, :3] * garment_alpha_3 + catvton_restore * (
                        1.0 - garment_alpha_3
                    )
                    result_np[lower_overlay_mask, :3] = deterministic[lower_overlay_mask, :3]
                    unsupported_mask = lower_overlay_mask & (garment_alpha < 0.20)
                    if unsupported_mask.any() and lower_texture_support.any():
                        source_pixels = layer_np[:, :, :3][lower_texture_support].astype(np.float32)
                        source_rgb = np.median(source_pixels, axis=0)
                        hsv_current = cv2.cvtColor(
                            np.clip(result_np[:, :, :3], 0, 255).astype(np.uint8),
                            cv2.COLOR_RGB2HSV,
                        ).astype(np.float32)
                        low_color = (
                            unsupported_mask
                            & (hsv_current[:, :, 1] < 58.0)
                            & (hsv_current[:, :, 2] < 190.0)
                            & (hsv_current[:, :, 2] > 24.0)
                        )
                        if low_color.any():
                            fill_alpha = 0.58
                            result_np[low_color, :3] = source_rgb * fill_alpha + result_np[
                                low_color, :3
                            ] * (1.0 - fill_alpha)
                            lower_unsupported_color_fill_ratio = float(low_color.mean())
                    lower_deterministic_overlay_ratio = float(lower_overlay_mask.mean())
            if catvton_mask_np is not None:
                catvton_value_for_transfer = cv2.cvtColor(
                    np.clip(catvton_for_mask, 0, 255).astype(np.uint8),
                    cv2.COLOR_RGB2HSV,
                )[:, :, 2].astype(np.float32)
                lower_mask_near = cv2.dilate(
                    (catvton_mask_np > 0.08).astype(np.uint8),
                    np.ones((25, 17), dtype=np.uint8),
                    iterations=1,
                ).astype(bool)
                lower_transfer_mask = (
                    (catvton_mask_np > 0.08)
                    | (lower_overlay_mask & lower_mask_near & (catvton_value_for_transfer < 170.0))
                ) & ~protected_by_mask
            else:
                lower_bbox_mask = (
                    (grid_x >= gar_x0) & (grid_x < gar_x1) & (grid_y >= gar_y0) & (grid_y < gar_y1)
                )
                if lower_conservative_color_only:
                    support_near = cv2.dilate(
                        lower_texture_support.astype(np.uint8),
                        np.ones((21, 13), dtype=np.uint8),
                        iterations=1,
                    ).astype(bool)
                    if lower_color_rescue:
                        hsv_catvton_lower = cv2.cvtColor(
                            np.clip(catvton_for_mask, 0, 255).astype(np.uint8),
                            cv2.COLOR_RGB2HSV,
                        ).astype(np.float32)
                        catvton_lower_surface = (
                            lower_bbox_mask
                            & (grid_y >= max(0, int(waist_y - ch * 0.015)))
                            & (hsv_catvton_lower[:, :, 2] < 205.0)
                            & ~skin_like
                            & ~near_white_bg
                        )
                        catvton_lower_surface = cv2.morphologyEx(
                            catvton_lower_surface.astype(np.uint8),
                            cv2.MORPH_OPEN,
                            np.ones((5, 5), dtype=np.uint8),
                        ).astype(bool)
                        catvton_lower_surface = cv2.morphologyEx(
                            catvton_lower_surface.astype(np.uint8),
                            cv2.MORPH_CLOSE,
                            np.ones((31, 17), dtype=np.uint8),
                        ).astype(bool)
                        catvton_lower_surface = _keep_significant_mask_components(
                            catvton_lower_surface,
                            min_area_ratio=0.18,
                            max_components=2,
                        )
                        labels_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
                            catvton_lower_surface.astype(np.uint8),
                            8,
                        )
                        row_filled = np.zeros_like(catvton_lower_surface, dtype=bool)
                        for label_idx in range(1, labels_count):
                            if int(stats[label_idx, cv2.CC_STAT_AREA]) < 128:
                                continue
                            component = labels == label_idx
                            ys_comp = np.where(component.any(axis=1))[0]
                            for yy_comp in ys_comp:
                                xs_comp = np.where(component[yy_comp, :])[0]
                                if xs_comp.size >= 8:
                                    row_filled[yy_comp, int(xs_comp[0]) : int(xs_comp[-1]) + 1] = (
                                        True
                                    )
                        if row_filled.any():
                            catvton_lower_surface = row_filled & lower_bbox_mask
                    else:
                        catvton_lower_surface = lower_bbox_mask
                    if lower_color_rescue:
                        lower_transfer_mask = (
                            catvton_lower_surface & lower_overlay_mask & ~protected_by_mask
                        )
                    else:
                        lower_transfer_mask = (
                            ((changed_garment & lower_bbox_mask) | support_near)
                            & catvton_lower_surface
                            & lower_overlay_mask
                            & ~protected_by_mask
                        )
                else:
                    lower_transfer_mask = lower_overlay_mask & ~protected_by_mask
            lower_texture_preserve_mask = np.zeros_like(lower_overlay_mask, dtype=bool)
            if strong_dark_lower_pattern and lower_texture_support.any():
                preserve_min_y = (
                    max(
                        int(min(lower_warp_meta.left_leg_box[1], lower_warp_meta.right_leg_box[1]))
                        - 8,
                        gar_y0,
                    )
                    if lower_warp_meta is not None
                    else int(gar_y0 + max(24, ch * 0.05))
                )
                lower_texture_preserve_mask = cv2.dilate(
                    lower_texture_support.astype(np.uint8),
                    np.ones((9, 5), dtype=np.uint8),
                    iterations=1,
                ).astype(bool)
                lower_texture_preserve_mask &= (
                    lower_overlay_mask & (layer_alpha > 0.12) & (grid_y >= preserve_min_y)
                )
                if lower_texture_preserve_mask.any():
                    lower_transfer_mask &= ~lower_texture_preserve_mask
                    lower_texture_preserve_ratio = float(lower_texture_preserve_mask.mean())
            overlay_reject_mask = lower_overlay_mask & ~lower_transfer_mask
            if overlay_reject_mask.any():
                result_np[overlay_reject_mask, :3] = catvton_for_mask[overlay_reject_mask, :3]
            source_available = bool(
                lower_texture_support.any()
                or (lower_color_rescue and _is_bottom and gar_src_alpha_mask.any())
            )
            if lower_transfer_mask.any() and source_available:
                if lower_color_rescue and _is_bottom and gar_src_alpha_mask.any():
                    source_pixels = gar_src_np[:, :, :3][gar_src_alpha_mask].astype(np.uint8)
                else:
                    source_pixels = layer_np[:, :, :3][lower_texture_support].astype(np.uint8)
                if source_pixels.size:
                    source_lab = (
                        cv2.cvtColor(
                            source_pixels.reshape(-1, 1, 3),
                            cv2.COLOR_RGB2LAB,
                        )
                        .reshape(-1, 3)
                        .astype(np.float32)
                    )
                    source_ab = np.median(source_lab[:, 1:3], axis=0)
                    source_l = float(np.median(source_lab[:, 0]))
                    catvton_base = catvton_for_mask.astype(np.uint8)
                    catvton_lab = cv2.cvtColor(catvton_base, cv2.COLOR_RGB2LAB).astype(np.float32)
                    result_lab = catvton_lab.copy()
                    if lower_conservative_color_only:
                        transfer_strength = 0.78 if lower_color_rescue else 0.32
                    else:
                        transfer_strength = 0.86
                    result_lab[lower_transfer_mask, 1] = (
                        result_lab[lower_transfer_mask, 1] * (1.0 - transfer_strength)
                        + source_ab[0] * transfer_strength
                    )
                    result_lab[lower_transfer_mask, 2] = (
                        result_lab[lower_transfer_mask, 2] * (1.0 - transfer_strength)
                        + source_ab[1] * transfer_strength
                    )
                    light_target = catvton_lab[lower_transfer_mask, 0] * 0.45 + source_l * 0.55
                    if lower_conservative_color_only:
                        if lower_color_rescue:
                            light_target = (
                                catvton_lab[lower_transfer_mask, 0] * 0.58 + source_l * 0.42
                            )
                        else:
                            light_target = (
                                catvton_lab[lower_transfer_mask, 0] * 0.82 + source_l * 0.18
                            )
                    result_lab[lower_transfer_mask, 0] = result_lab[lower_transfer_mask, 0] * (
                        0.36
                        if (lower_conservative_color_only and lower_color_rescue)
                        else (0.62 if lower_conservative_color_only else 0.16)
                    ) + light_target * (
                        0.64
                        if (lower_conservative_color_only and lower_color_rescue)
                        else (0.38 if lower_conservative_color_only else 0.84)
                    )
                    transferred_rgb = cv2.cvtColor(
                        np.clip(result_lab, 0, 255).astype(np.uint8),
                        cv2.COLOR_LAB2RGB,
                    ).astype(np.float32)
                    if lower_color_rescue and lower_conservative_color_only:
                        transfer_alpha = cv2.GaussianBlur(
                            lower_transfer_mask.astype(np.float32),
                            (11, 11),
                            0,
                        )
                        transfer_alpha = np.clip(transfer_alpha * 0.88, 0.0, 0.88)
                        transfer_alpha[lower_transfer_mask] = np.maximum(
                            transfer_alpha[lower_transfer_mask],
                            0.78,
                        )
                        transfer_alpha = transfer_alpha[:, :, np.newaxis]
                        result_np[:, :, :3] = transferred_rgb * transfer_alpha + result_np[
                            :, :, :3
                        ] * (1.0 - transfer_alpha)
                    else:
                        result_np[lower_transfer_mask, :3] = transferred_rgb[
                            lower_transfer_mask, :3
                        ]
                    lower_color_transfer_ratio = float(lower_transfer_mask.mean())
            if lower_texture_preserve_mask.any() and not lower_conservative_color_only:
                preserve_source_alpha = np.clip(
                    layer_alpha, 0.0, 1.0
                ) * lower_texture_preserve_mask.astype(np.float32)
                preserve_alpha = cv2.GaussianBlur(
                    preserve_source_alpha,
                    (7, 7),
                    0,
                )
                preserve_alpha = np.clip(preserve_alpha * 1.08, 0.0, 0.94)
                preserve_alpha[lower_texture_preserve_mask] = np.maximum(
                    preserve_alpha[lower_texture_preserve_mask],
                    np.minimum(layer_alpha[lower_texture_preserve_mask], 0.92),
                )
                preserve_alpha = preserve_alpha[:, :, np.newaxis]
                result_np[:, :, :3] = layer_np[:, :, :3].astype(
                    np.float32
                ) * preserve_alpha + result_np[:, :, :3] * (1.0 - preserve_alpha)
        if _is_top:
            result_np[protected_by_mask] = catvton_for_mask[protected_by_mask]

        light_block_repair_ratio = 0.0
        if _is_top and light_pattern_base:
            garment_repair_mask = (
                (catvton_mask_np > 0.08)
                if catvton_mask_np is not None
                else ((torso_fit_mask > 0.08) & garment_layer_present)
            )
            result_np, light_block_repair_ratio = _repair_light_garment_block_artifacts(
                result_np,
                garment_repair_mask,
                motif_gate,
                gar_x0=gar_x0,
                gar_y0=gar_y0,
                gar_x1=gar_x1,
                gar_y1=gar_y1,
                body_cx=body_cx,
                light_pattern_base=light_pattern_base,
            )
            if light_block_repair_ratio > 0.0:
                logger.info(
                    "catvton_color_fidelity_spatial: repaired light garment blocks "
                    "(coverage=%.4f)",
                    light_block_repair_ratio,
                )
                result_np[protected_by_mask] = catvton_for_mask[protected_by_mask]

        # ── Step 5b: 褶皱暗化 + 边缘投影 ─────────────────────────────
        # 参考 tryon_top_warp 的 realism pass，增加立体感
        # 图案衣服跳过，避免破坏图案
        _pattern_score = spatial_pattern_score
        _skip_realism = _pattern_score > 0.40

        if not _skip_realism:
            # 褶皱暗化：在衣物区域 33% 和 67% 宽度处添加垂直暗线
            fold_positions = [int(gar_w * 0.33), int(gar_w * 0.67)]
            fold_strength = 0.04
            for fx in fold_positions:
                abs_x = paste_x + min(fx, gar_w - 1)
                if 0 < abs_x < cw - 1:
                    fade = max(0, 1.0 - abs(fx - gar_w / 2) / (gar_w * 0.25)) * fold_strength
                    if fade > 0.005:
                        region = result_np[paste_y : paste_y + gar_h, max(0, abs_x - 1) : abs_x + 1]
                        if region.size > 0:
                            region_alpha = layer_alpha[
                                paste_y : paste_y + gar_h, max(0, abs_x - 1) : abs_x + 1
                            ]
                            darken = (1.0 - fade) * np.clip(region_alpha, 0, 1)[..., np.newaxis]
                            region[:] = np.clip(region.astype(np.float32) * darken, 0, 255)

            # 边缘投影暗化：衣物边缘附近添加暗化（模拟衣物投射到身体上的阴影）
            edge_px = max(2, int(feather_px * 1.5))
            for dx in range(-edge_px, edge_px + 1):
                for dy in range(-edge_px, edge_px + 1):
                    abs_x = paste_x + dx
                    abs_y = paste_y + dy
                    if 0 <= abs_x < cw and 0 <= abs_y < ch:
                        alpha_at = (
                            layer_np[abs_y, abs_x, 3]
                            if abs_y < layer_np.shape[0] and abs_x < layer_np.shape[1]
                            else 0
                        )
                        if 10 < alpha_at < 245:
                            edge_dist = max(abs(dx), abs(dy))
                            falloff = max(0, 1.0 - edge_dist / float(edge_px)) * 0.06
                            if falloff > 0.005:
                                result_np[abs_y, abs_x, :3] = np.clip(
                                    result_np[abs_y, abs_x, :3].astype(float) * (1.0 - falloff),
                                    0,
                                    255,
                                ).astype(np.uint8)

            logger.info(
                "catvton_color_fidelity_spatial: realism pass applied "
                "(pattern_score=%.3f, fold+shadow)",
                _pattern_score,
            )
        else:
            logger.info(
                "catvton_color_fidelity_spatial: realism pass skipped "
                "(pattern_score=%.3f > 0.40)",
                _pattern_score,
            )

        if _is_top:
            result_np[protected_by_mask] = catvton_for_mask[protected_by_mask]
        result_np = np.clip(result_np, 0, 255).astype(np.uint8)
        result_img = Image.fromarray(result_np, mode="RGB")

        logger.info(
            "catvton_color_fidelity_spatial: region=[%d,%d,%d,%d] "
            "strength=%.2f garment=%dx%d "
            "(body_center=%d,%d, light_base=%s, rescue=%s)",
            gar_x0,
            gar_y0,
            gar_x1,
            gar_y1,
            blend_fidelity_strength,
            sw,
            sh,
            body_cx,
            body_cy,
            light_pattern_base,
            needs_light_base_rescue,
        )
        return result_img, {
            "engine": "catvton_color_fidelity_spatial",
            "garment_region": {"x0": gar_x0, "y0": gar_y0, "x1": gar_x1, "y1": gar_y1},
            "fidelity_strength": blend_fidelity_strength,
            "body_valid": body_valid,
            "method": "spatial_pixel_replace",
            "lower_warp_reused": lower_warp_meta is not None,
            "lower_warp_engine": lower_warp_meta.engine if lower_warp_meta is not None else None,
            "lower_warp_boxes": (
                {
                    "waistband_box": list(lower_warp_meta.waistband_box),
                    "left_leg_box": list(lower_warp_meta.left_leg_box),
                    "right_leg_box": list(lower_warp_meta.right_leg_box),
                    "alpha_feather_px": lower_warp_meta.alpha_feather_px,
                }
                if lower_warp_meta is not None
                else None
            ),
            "light_pattern_base": light_pattern_base,
            "light_base_repaint": light_base_repaint,
            "dark_pattern_base": dark_pattern_base,
            "dark_base_repaint": dark_base_repaint,
            "lower_denim_like": lower_denim_like,
            "lower_conservative_color_only": lower_conservative_color_only,
            "lower_texture_qc_accepted": lower_texture_qc_accepted,
            "lower_color_rescue": bool(lower_color_rescue),
            "lower_warp_qc": lower_warp_qc,
            "needs_light_base_rescue": needs_light_base_rescue,
            "catvton_mask_applied": catvton_mask_np is not None,
            "wear_shape_applied": wear_shape_np is not None,
            "base_fidelity_strength": base_fidelity_strength,
            "motif_detail_enhance_strength": motif_detail_enhance_strength,
            "lower_layer_gap_fill_ratio": lower_layer_gap_fill_ratio,
            "lower_texture_qc_accepted": lower_texture_qc_accepted,
            "lower_restore_ratio": lower_restore_ratio,
            "lower_deterministic_overlay_ratio": lower_deterministic_overlay_ratio,
            "lower_texture_support_ratio": lower_texture_support_ratio,
            "lower_texture_preserve_ratio": lower_texture_preserve_ratio,
            "lower_unsupported_color_fill_ratio": lower_unsupported_color_fill_ratio,
            "lower_color_transfer_ratio": lower_color_transfer_ratio,
            "pale_artifact_removed_ratio": pale_artifact_removed_ratio,
            "light_block_repair_ratio": light_block_repair_ratio,
            "catvton_changed_value_mean": catvton_changed_value_mean,
            "source_value_mean": source_value_mean,
            "source_sat_mean": source_sat_mean,
        }

    except Exception as e:
        import traceback

        logger.warning("catvton_color_fidelity_spatial failed: %s\n%s", e, traceback.format_exc())
        return catvton_result, {
            "engine": "catvton_color_fidelity_spatial",
            "reason": str(e),
        }
