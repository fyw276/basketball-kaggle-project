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

    waist_h = _clamp_int(int(ph * 0.11), 24, int(ph * 0.18))
    wy0 = _clamp_int(waist_y - waist_h // 2, 0, ph - 2)
    wy1 = _clamp_int(waist_y + waist_h // 2, wy0 + 2, ph)
    waistband_box = (x0, wy0, x1, wy1)

    leg_y0 = _clamp_int(int(wy1 + ph * 0.01), 0, ph - 2)
    leg_y1 = _clamp_int(ankle_y, leg_y0 + 2, ph)
    mid = _clamp_int(mid, x0 + 2, x1 - 2)

    left_leg_box = (x0, leg_y0, mid, leg_y1)
    right_leg_box = (mid, leg_y0, x1, leg_y1)
    return waistband_box, left_leg_box, right_leg_box


def tryon_pants_warp(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.012,
) -> tuple[Image.Image, WarpMetadata]:
    """Return (result_rgb, metadata).

    Uses MediaPipe Pose keypoints (hips/knees/ankles) when available for
    accurate waist and leg placement; falls back to gradient energy estimation.

    Two-stage warp for patterned pants:
      - Stage 1: waistband + upper legs (hip→knee) — single taper
      - Stage 2: lower legs (knee→ankle) — full taper
    This preserves knee-bend pattern symmetry vs. single-taper warp.
    """
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)

    # ── Extract MediaPipe knee keypoints for knee-aware leg warp ──────────────
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
        # knee_garment_ratio: knee position within leg portion (0=at waist, 1=at ankle)
        # The leg portion starts after waistband (~20% of cropped pants).
        # Use average of both legs for robustness.
        ratios = []
        if _left_knee_y and _left_ankle_y:
            ratios.append((_left_knee_y - 0.20) / (_left_ankle_y - 0.20))
        if _right_knee_y and _right_ankle_y:
            ratios.append((_right_knee_y - 0.20) / (_right_ankle_y - 0.20))
        if ratios:
            avg = sum(ratios) / len(ratios)
            _knee_garment_ratio = max(0.30, min(0.65, avg))
            parts = split_pants_parts(cutout.cropped, knee_garment_ratio=_knee_garment_ratio)
        else:
            parts = split_pants_parts(cutout.cropped)
    else:
        parts = split_pants_parts(cutout.cropped)

    # ── MediaPipe 优先路径 ──────────────────────────────────────────────────
    kpts = detect_pose_keypoints(person_image)
    if kpts:
        bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "bottom")
        if bounds.get("valid"):
            x0 = bounds["x0"]
            x1 = bounds["x1"]
            waist_y = bounds["waist_y"]
            ankle_y = bounds["ankle_y"]
            body_w = max(2, x1 - x0)
            mid = x0 + body_w // 2

            waist_h = _clamp_int(int(ph * 0.11), 24, int(ph * 0.18))
            wy0 = _clamp_int(waist_y - waist_h // 2, 0, ph - 2)
            wy1 = _clamp_int(waist_y + waist_h // 2, wy0 + 2, ph)
            waistband_box: tuple[int, int, int, int] = (x0, wy0, x1, wy1)

            leg_y0 = _clamp_int(wy1 + max(1, int(ph * 0.01)), 0, ph - 2)
            leg_y1 = _clamp_int(ankle_y, leg_y0 + 2, ph)
            mid = _clamp_int(mid, x0 + 2, x1 - 2)
            left_leg_box: tuple[int, int, int, int] = (x0, leg_y0, mid, leg_y1)
            right_leg_box: tuple[int, int, int, int] = (mid, leg_y0, x1, leg_y1)
            _used_pose = True
        else:
            waistband_box, left_leg_box, right_leg_box = _compute_target_boxes(person_image)
            _used_pose = False
    else:
        waistband_box, left_leg_box, right_leg_box = _compute_target_boxes(person_image)
        _used_pose = False

    def _warp_into_box(src: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
        x0, y0, x1, y1 = box
        tw = max(2, x1 - x0)
        th = max(2, y1 - y0)
        # Use QUAD with a mild taper to mimic leg narrowing.
        # Stronger taper improves leg fit for straight-standing photos.
        inset = int(tw * 0.10)
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
            # Taper top slightly for leg fit.
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

    layer_waist = _warp_into_box(parts.waistband, waistband_box)

    # ── Two-stage knee-aware warp for patterned pants ─────────────────────────
    # Stage 1: warp upper leg (hip→knee) — mild taper
    # Stage 2: warp lower leg (knee→ankle) — full taper
    # This preserves pattern alignment at knee vs. single-taper warp which distorts patterns.
    def _warp_two_stage(
        src_upper: Image.Image,
        src_lower: Image.Image,
        leg_box: tuple[int, int, int, int],
        knee_person_y: float | None = None,
    ) -> Image.Image:
        """Two-stage leg warp: upper (mild taper) then lower (full taper).

        Args:
            leg_box: (x0, y0, x1, y1) of the full leg (hip→ankle)
            knee_person_y: Optional knee y-coordinate in person-image pixel space.
                If provided, splits leg_box at knee for two separate warps.
                If None, performs single warp for the whole leg.
        """
        if knee_person_y is None:
            return _warp_into_box(src_upper, leg_box)

        x0, y0_full, x1, y1_full = leg_box
        # Split full leg at knee position
        knee_y_clamped = _clamp_int(int(knee_person_y), y0_full + 2, y1_full - 2)
        upper_box = (x0, y0_full, x1, knee_y_clamped)
        lower_box = (x0, knee_y_clamped, x1, y1_full)

        canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        # Stage 1: upper leg (hip→knee) — mild taper
        upper_layer = _warp_into_box(src_upper, upper_box)
        canvas = Image.alpha_composite(canvas, upper_layer)
        # Stage 2: lower leg (knee→ankle) — full taper (15%)
        lower_layer = _warp_into_box(src_lower, lower_box)
        canvas = Image.alpha_composite(canvas, lower_layer)
        return canvas

    # Two-stage warp if knee keypoints and split parts are available
    if (
        parts.left_upper is not None
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
        # Fallback: single-stage warp
        layer_left = _warp_into_box(parts.left_leg, left_leg_box)
        layer_right = _warp_into_box(parts.right_leg, right_leg_box)

    merged = Image.alpha_composite(Image.alpha_composite(layer_left, layer_right), layer_waist)

    # Feather alpha edges for smoother boundary.
    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 12)
    merged = _feather_alpha(merged, radius_px=feather_px)

    # Protect upper body: do not overwrite above ~30% height.
    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.30))
    if merged.mode != "RGBA":
        merged = merged.convert("RGBA")
    r, g, b, a = merged.split()
    a = ImageChops.multiply(a, protect)
    merged = Image.merge("RGBA", (r, g, b, a))

    out = Image.alpha_composite(base, merged).convert("RGB")
    engine_tag = "pants_warp_v2_pose" if _used_pose else "pants_warp_v1_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=waistband_box,
        left_leg_box=left_leg_box,
        right_leg_box=right_leg_box,
        alpha_feather_px=feather_px,
    )
    return out, meta


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

        # ── Step 1: Find garment foreground region in warp result ──────────────────
        # Use foreground mask to locate where the garment is pasted
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

        # Feather garment edge so blending is smooth
        try:
            kernel = np.ones((expand * 2 + 1, expand * 2 + 1), np.uint8)
            gar_mask_u8 = (garment_mask * 255).astype(np.uint8)
            gar_mask_u8 = cv2.erode(gar_mask_u8, kernel, iterations=1)
            gar_mask_f = gar_mask_u8.astype(np.float32) / 255.0
            # Background blend weight: high far from garment, low near garment
            blend_weight = (1.0 - gar_mask_f) * drape_alpha
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
        }

    except Exception as e:
        import traceback

        logger.warning("overlay_draping_from_ai failed: %s\n%s", e, traceback.format_exc())
        return warp_result, {"engine": "overlay_draping", "reason": str(e)}


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

    # Stage 2: overlay_draping_from_ai
    # 核心：衣服区域 100% 保留 warp，颜色/图案完全来自原始衣服
    #         衣服区域外叠加 CatVTON 的光影/阴影
    result, blend_meta = overlay_draping_from_ai(
        warp_result=warp_result,
        ai_result=catvton_result,
        drape_alpha=drape_alpha,
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

        # ── Step 2: 估算衣服区域在 CatVTON 结果中的位置 ─────────────────────
        kpts = detect_pose_keypoints(catvton_result)
        if kpts:
            bounds = get_body_bounds_from_keypoints(kpts, cw, ch, "top" if _is_top else "bottom")
            if bounds.get("valid"):
                bx0 = int(bounds["x0"])
                bx1 = int(bounds["x1"])
                neck_y = int(bounds["neck_y"])
                waist_y = int(bounds["waist_y"])
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
                neck_y, waist_y = int(ch * 0.38), int(ch * 0.90)

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
        feather_px = max(2, int(min(cw, ch) * 0.012))
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

        protect = _make_en_face_protect_mask(cw, ch, face_box, neck_y)
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


def catvton_color_fidelity_spatial(
    catvton_result: Image.Image,
    original_garment: Image.Image,
    person_image: Image.Image,
    garment_category: str,
    *,
    fidelity_strength: float = 0.75,
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

        # ── Step 1: 检测 CatVTON 结果中的人物身体位置 ─────────────────────
        from app.services.tryon_v2.pose_utils import (
            detect_pose_keypoints,
            get_body_bounds_from_keypoints,
        )

        kpts = detect_pose_keypoints(catvton_result)
        body_valid = False

        if kpts:
            bounds = get_body_bounds_from_keypoints(kpts, cw, ch, "top" if _is_top else "bottom")
            if bounds.get("valid"):
                bx0 = int(bounds["x0"])
                bx1 = int(bounds["x1"])
                neck_y = int(bounds["neck_y"])
                waist_y = int(bounds["waist_y"])
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
                    body_valid = True

        if not body_valid:
            bx0, bx1 = int(cw * 0.15), int(cw * 0.85)
            neck_y, waist_y = int(ch * 0.15), int(ch * 0.50)

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

        # DEBUG: Log RGB and alpha stats after cutout_garment_rgba
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

        # ── Constraint: 方向校正（处理横向衣服图）────────────────────
        # 如果衣服图是横向的（宽 > 高），说明可能是平铺图，需要旋转
        if _is_top or _is_skirt:
            if sw > sh * 1.3:
                gar_src = gar_src.transpose(Image.Transpose.ROTATE_90)
                sw, sh = gar_src.size
                logger.info(
                    "catvton_color_fidelity_spatial: garment rotated 90° "
                    "(was wider than tall: %dx%d → %dx%d)",
                    sh,
                    sw,
                    sw,
                    sh,
                )

        # ── 缩放：等比缩放填满目标区域 ─────────────────────────────────
        # 衣服图案完整填满 gar_w × gar_h，与 CatVTON mask 行为一致
        scale_x = gar_w / float(sw)
        scale_y = gar_h / float(sh)
        # 用更小的 scale 确保填满（可能稍微裁剪边缘）
        scale = min(scale_x, scale_y) if catvton_mask_np is not None else max(scale_x, scale_y)
        s_w = max(2, int(sw * scale))
        s_h = max(2, int(sh * scale))

        # Fix: Separate RGB and alpha channels before scaling to prevent alpha premultiplication
        # LANCZOS interpolation can cause premultiplied alpha effects on RGBA images
        r, g, b, a = gar_src.split()
        r_scaled = r.resize((s_w, s_h), Image.Resampling.LANCZOS)
        g_scaled = g.resize((s_w, s_h), Image.Resampling.LANCZOS)
        b_scaled = b.resize((s_w, s_h), Image.Resampling.LANCZOS)
        # Use NEAREST for alpha to preserve binary mask edges (LANCZOS smooths them)
        a_scaled = a.resize((s_w, s_h), Image.Resampling.NEAREST)
        gar_scaled = Image.merge("RGBA", (r_scaled, g_scaled, b_scaled, a_scaled))
        logger.info(
            "catvton_color_fidelity_spatial: proportional %s "
            "(target=%dx%d, garment=%dx%d, scale=%.3f → scaled=%dx%d, "
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

        # DEBUG: Log RGB and alpha stats after scaling
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

        # TPS 变形：只对缩放后的衣服做 TPS 变形，让图案贴合身体曲线
        # 注意：TPS 的目标尺寸 = (gar_w, gar_h)（目标区域像素尺寸）
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
                # DEBUG: 记录哪些关键点可用
                _available = {n: (round(v[0], 3), round(v[1], 3)) for n, v in tps_keypoints.items()}
                logger.info(
                    "DEBUG [TPS keypoints]: available=%d/%d, keys=%s, all_kpts=%s",
                    len(tps_keypoints),
                    len(_all_needed_kpts),
                    _available,
                    {n: (n in kpts) for n in _all_needed_kpts},
                )
                if len(tps_keypoints) >= 4:
                    # 保存原始 alpha 通道（用于修复 TPS warp 丢失 alpha 的问题）
                    gar_rgb = gar_scaled.convert("RGB")
                    original_alpha = gar_scaled.split()[3]

                    # DEBUG: 记录 TPS warp 前的状态
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

                    # TPS 输出尺寸 = gar_w × gar_h（目标区域大小）
                    gar_warped = tps_engine.warp(
                        gar_rgb,
                        tps_keypoints,
                        (gar_w, gar_h),
                        cloth_type="upper" if _is_top else "bottom",
                    )

                    # 修复：将原始 alpha 缩放到目标尺寸，与 warped RGB 合并
                    alpha_resized = original_alpha.resize((gar_w, gar_h), Image.Resampling.NEAREST)
                    gar_scaled = Image.merge("RGBA", (gar_warped, alpha_resized))

                    # DEBUG: 记录 alpha 缩放后的状态
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

                    # DEBUG: Log RGB and alpha stats after TPS warp with alpha fix
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
                    "catvton_color_fidelity_spatial: TPS warp failed (%s), " "using scaled garment",
                    tps_err,
                )

        # ── 粘贴：图案完整覆盖身体区域（gar_scaled = gar_w × gar_h）─────────
        # 粘贴位置：gar_x0, gar_y0（身体区域左上角，与 CatVTON mask 区域完全一致）
        paste_x = max(0, min(gar_x0, cw - gar_w))
        paste_y = max(0, min(gar_y0, ch - gar_h))

        # gar_scaled 已经是 gar_w × gar_h，直接粘贴
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

        # 创建 warp 层
        warped_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        warped_layer.paste(gar_fitted, (paste_x, paste_y), gar_fitted)

        # DEBUG: Log RGB and alpha stats after paste
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

        # 保存 paste 后的衣服像素用于 fallback（如果脸部保护导致 alpha 过低）
        _pre_protection_rgb = warped_layer_rgb_mean

        # ── Step 3: 羽化边缘 ─────────────────────────────────────────
        feather_px = max(2, int(min(cw, ch) * 0.012))
        # _feather_alpha returns a feathered RGBA layer (alpha = GaussianBlur of original alpha)
        # warped_layer = the full RGBA image with softened edges
        warped_layer = _feather_alpha(warped_layer, radius_px=feather_px)

        # DEBUG: Log RGB and alpha stats after feathering
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
            "DEBUG [after feathering]: RGB mean=%.2f, Alpha mean=%.2f (in non-transparent regions)",
            warped_layer_feathered_rgb_mean,
            warped_layer_feathered_alpha_mean,
        )

        # ── Step 4: 保护面部和手部 ─────────────────────────────────────
        # 面部：Haar cascade 精确检测（_is_top 专享）
        protect = _make_face_protect_mask(cw, ch, face_box, neck_y)

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
                motif_dilate_iterations = 2
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

        if (
            motif_pixels.size > 0
            and motif_gate.max() > 0.0
            and (light_pattern_base or dark_pattern_base)
            and spatial_pattern_score > 0.45
        ):
            motif_detail_enhance_strength = 0.30 if light_pattern_base else 0.24
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
        if catvton_mask_np is not None:
            motif_allowed &= catvton_mask_np > 0.08
            base_allowed &= catvton_mask_np > 0.08
        fidelity_allowed = motif_allowed | base_allowed
        base_fidelity_strength = 0.0
        if light_base_repaint:
            if needs_light_base_rescue:
                base_fidelity_strength = 0.16
            elif mask_guided_light_pattern and catvton_has_existing_motif:
                base_fidelity_strength = 0.12
            else:
                base_fidelity_strength = 0.14
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
        if catvton_mask_np is not None:
            base_repaint_gate *= catvton_mask_np
        base_repaint_gate *= np.clip(1.0 - motif_gate * 0.75, 0.18, 1.0)
        if light_base_repaint:
            target_blend_strength = 0.78 if needs_light_base_rescue else 0.74
            blend_fidelity_strength = max(float(fidelity_strength), target_blend_strength)
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
        if catvton_mask_np is not None:
            motif_strength *= catvton_mask_np
            base_strength *= catvton_mask_np
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
                    "wear_shape_applied": False,
                    "wear_shape_coverage": (
                        round(float((wear_shape_for_debug > 0.08).mean()), 4)
                        if wear_shape_for_debug is not None
                        else None
                    ),
                    "torso_fit_coverage": round(float((torso_fit_mask > 0.08).mean()), 4),
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
                },
            )

        for c in range(3):
            result_np[:, :, c] = layer_np[:, :, c] * strength + result_np[:, :, c] * (
                1.0 - strength
            )
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
            "light_pattern_base": light_pattern_base,
            "light_base_repaint": light_base_repaint,
            "dark_pattern_base": dark_pattern_base,
            "dark_base_repaint": dark_base_repaint,
            "needs_light_base_rescue": needs_light_base_rescue,
            "catvton_mask_applied": catvton_mask_np is not None,
            "wear_shape_applied": wear_shape_np is not None,
            "base_fidelity_strength": base_fidelity_strength,
            "motif_detail_enhance_strength": motif_detail_enhance_strength,
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
