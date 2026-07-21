from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from app.services.tryon_pattern_utils import detect_pattern_strength


@dataclass
class InputAnomalyScore:
    mirror_ghost_score: float
    jpeg_artifact_score: float
    passed: bool


@dataclass
class CutoutAlphaQC:
    alpha_coverage: float
    alpha_component_count: int
    largest_component_ratio: float
    bbox_fill_ratio: float
    edge_touch_ratio: float
    background_leak_ratio: float
    passed: bool
    reason: str


@dataclass
class EngineDecisionFeatures:
    sat_mean: float
    sat_max: float
    bright_mean: float
    is_white_garment: bool
    has_color: bool
    pattern_score: float
    pattern_confidence: float


@dataclass
class ArtifactReport:
    blockiness_score: float
    outlier_ratio: float
    failed: bool
    horizontal_hard_edge_score: float = 0.0
    luminance_mismatch_score: float = 0.0
    rectangular_overlay_score: float = 0.0


@dataclass
class RawCatVTONQuality:
    color_passed: bool
    pattern_passed: bool
    artifact_passed: bool
    decision: str
    reason: str
    source_value_mean: float
    raw_value_mean: float
    color_delta: float
    source_pattern_score: float
    raw_pattern_signal: float
    artifact_score: float
    garment_coverage: float
    source_hue_entropy: float = 0.0
    raw_hue_entropy: float = 0.0


def should_force_lower_structured_pattern_recovery(
    *,
    garment_category: str,
    raw_quality: RawCatVTONQuality,
) -> bool:
    """Catch lower-body raw passes that still lost strong structured patterns."""
    cat = (garment_category or "").strip().lower()
    is_lower = any(
        k in cat for k in ("bottom", "pants", "lower", "下装", "裤", "裤装", "短裤", "长裤")
    )
    if not is_lower:
        return False
    if raw_quality.decision not in {"raw", "pattern_only"}:
        return False
    if raw_quality.source_pattern_score < 0.75:
        return False
    if raw_quality.raw_pattern_signal > max(0.47, raw_quality.source_pattern_score * 0.49):
        return False
    if raw_quality.garment_coverage < 0.10:
        return False
    return True


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _normalize_optional_mask(
    mask_image: Image.Image | None, size: tuple[int, int]
) -> np.ndarray | None:
    if mask_image is None:
        return None
    mask = np.asarray(mask_image.convert("L").resize(size, Image.Resampling.NEAREST))
    mask = mask > 127
    if int(mask.sum()) < max(128, int(mask.size * 0.01)):
        return None
    return mask


def _foreground_mask_from_rgb(arr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    return (val >= 15) & ~((val > 220) & (sat < 30))


def _estimate_raw_garment_mask(
    *,
    raw_result: Image.Image,
    person_image: Image.Image,
    garment_category: str,
) -> np.ndarray:
    raw = np.asarray(raw_result.convert("RGB"), dtype=np.float32)
    person = np.asarray(
        person_image.convert("RGB").resize(raw_result.size, Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    h, w = raw.shape[:2]
    diff = np.abs(raw - person).mean(axis=2)
    threshold = max(7.0, min(22.0, float(np.percentile(diff, 78)) * 0.70))
    changed = diff > threshold

    cat = (garment_category or "").strip().lower()
    yy, xx = np.indices((h, w))
    if any(k in cat for k in ("top", "upper", "上衣", "上装")):
        region = (
            (yy >= int(h * 0.16))
            & (yy <= int(h * 0.56))
            & (xx >= int(w * 0.12))
            & (xx <= int(w * 0.88))
        )
    elif any(k in cat for k in ("bottom", "pants", "lower", "裤", "下装")):
        region = (
            (yy >= int(h * 0.40))
            & (yy <= int(h * 0.90))
            & (xx >= int(w * 0.15))
            & (xx <= int(w * 0.85))
        )
    else:
        region = (
            (yy >= int(h * 0.15))
            & (yy <= int(h * 0.90))
            & (xx >= int(w * 0.10))
            & (xx <= int(w * 0.90))
        )

    mask = (changed & region).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), dtype=np.uint8))
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n_labels > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = int(np.argmax(areas) + 1)
        mask = (labels == keep).astype(np.uint8)

    if int(mask.sum()) < max(128, int(h * w * 0.015)):
        mask = region.astype(np.uint8)
    return mask.astype(bool)


def _pattern_signal(arr: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    rgb = arr.astype(np.uint8)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    colorful = ((sat > 42) & (val > 35) & mask).sum() / float(max(1, mask.sum()))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    lap_score = float(np.percentile(np.abs(lap[mask]), 88)) / 48.0 if mask.any() else 0.0
    return float(min(1.0, colorful * 8.0 + lap_score * 0.35))


def _hue_entropy(hsv_pixels: np.ndarray) -> float:
    if hsv_pixels.size == 0:
        return 0.0
    pixels = hsv_pixels.reshape(-1, 3)
    selected = pixels[(pixels[:, 1] > 30) & (pixels[:, 2] > 40)]
    if selected.shape[0] < max(24, int(pixels.shape[0] * 0.015)):
        return 0.0
    hue_bins = np.clip((selected[:, 0] // 10).astype(np.int32), 0, 17)
    hist = np.bincount(hue_bins, minlength=18).astype(np.float32)
    total = float(hist.sum())
    if total <= 0:
        return 0.0
    prob = hist / total
    prob = prob[prob > 0]
    return float(-(prob * np.log2(prob)).sum())


def _fabric_texture_score(arr: np.ndarray, mask: np.ndarray) -> float:
    """Laplacian-based fabric fold/texture score in [0, 1]."""
    if not mask.any():
        return 0.0
    gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    return float(min(1.0, float(np.percentile(lap[mask], 88)) / 48.0))


def _lower_result_is_solid_leg_blob(arr: np.ndarray, mask: np.ndarray) -> bool:
    """True when lower edit region has no crotch gap and looks like one flat panel."""
    ys, xs = np.where(mask)
    if xs.size < 200:
        return False
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    h = max(1, y1 - y0)
    w = max(1, x1 - x0)
    mid_y0 = y0 + int(0.38 * h)
    mid_y1 = y0 + int(0.82 * h)
    mid_x = (x0 + x1) // 2
    cw = max(2, int(0.07 * w))
    center = mask[mid_y0:mid_y1, max(0, mid_x - cw) : mid_x + cw]
    left = mask[mid_y0:mid_y1, x0 + int(0.12 * w) : x0 + int(0.32 * w)]
    right = mask[mid_y0:mid_y1, x0 + int(0.68 * w) : x0 + int(0.88 * w)]
    if center.size < 30 or left.size < 30 or right.size < 30:
        return False
    # Real pants usually leave some empty pixels between thighs in the mask or
    # at least a darker / different center strip after generation.
    center_fill = float(center.mean())
    if center_fill < 0.80:
        return False

    tex = _fabric_texture_score(arr, mask)
    # No crotch gap + weak fabric folds ⇒ skirt/panel blob (CatVTON solid fill).
    if tex <= 0.14:
        return True

    def _mean_rgb(region_mask: np.ndarray, y_a: int, y_b: int, x_a: int, x_b: int) -> np.ndarray:
        patch = arr[y_a:y_b, x_a:x_b]
        m = region_mask
        if m.shape != patch.shape[:2]:
            return np.zeros(3, dtype=np.float32)
        pix = patch[m]
        if pix.size == 0:
            return np.zeros(3, dtype=np.float32)
        return pix.mean(axis=0)

    c_rgb = _mean_rgb(center, mid_y0, mid_y1, max(0, mid_x - cw), mid_x + cw)
    l_rgb = _mean_rgb(left, mid_y0, mid_y1, x0 + int(0.12 * w), x0 + int(0.32 * w))
    r_rgb = _mean_rgb(right, mid_y0, mid_y1, x0 + int(0.68 * w), x0 + int(0.88 * w))
    dist_l = float(np.linalg.norm(c_rgb - l_rgb))
    dist_r = float(np.linalg.norm(c_rgb - r_rgb))
    return dist_l < 28.0 and dist_r < 28.0


def _region_artifact_score(arr: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any():
        return 1.0
    rgb = arr.astype(np.uint8)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    low = cv2.GaussianBlur(gray, (11, 11), 0)
    resid = np.abs(gray - low)
    blockiness = float(np.percentile(resid[mask], 92)) / 55.0
    # A white/light garment base is not itself an artifact. Only count pale regions
    # that also stand out from local fabric texture.
    pale_patch = ((val > 232) & (sat < 32) & (resid > 8) & mask).sum() / float(max(1, mask.sum()))
    very_dark_patch = ((val < 12) & mask).sum() / float(max(1, mask.sum()))
    return float(min(1.0, blockiness * 0.75 + pale_patch * 1.8 + very_dark_patch * 0.6))


def evaluate_raw_catvton_quality(
    *,
    raw_result: Image.Image,
    original_garment: Image.Image,
    person_image: Image.Image,
    garment_category: str,
    features: EngineDecisionFeatures,
    raw_mask_image: Image.Image | None = None,
) -> RawCatVTONQuality:
    """Decide whether CatVTON raw output already preserves color/pattern well enough."""
    raw_arr = np.asarray(raw_result.convert("RGB"), dtype=np.float32)
    garment_arr = np.asarray(original_garment.convert("RGB"), dtype=np.float32)
    source_mask = _foreground_mask_from_rgb(garment_arr.astype(np.uint8))
    raw_mask = _normalize_optional_mask(raw_mask_image, raw_result.size)
    if raw_mask is None:
        raw_mask = _estimate_raw_garment_mask(
            raw_result=raw_result,
            person_image=person_image,
            garment_category=garment_category,
        )

    source_pixels = garment_arr[source_mask] if source_mask.any() else garment_arr.reshape(-1, 3)
    raw_pixels = raw_arr[raw_mask] if raw_mask.any() else raw_arr.reshape(-1, 3)
    source_rgb = np.median(source_pixels, axis=0).astype(np.float32)
    raw_rgb = np.median(raw_pixels, axis=0).astype(np.float32)

    source_lab = cv2.cvtColor(
        np.uint8([[np.clip(source_rgb, 0, 255)]]),
        cv2.COLOR_RGB2LAB,
    ).astype(
        np.float32
    )[0, 0]
    raw_lab = cv2.cvtColor(
        np.uint8([[np.clip(raw_rgb, 0, 255)]]),
        cv2.COLOR_RGB2LAB,
    ).astype(
        np.float32
    )[0, 0]
    color_delta = float(np.linalg.norm(source_lab - raw_lab))

    hsv_source = cv2.cvtColor(
        source_pixels.reshape(-1, 1, 3).astype(np.uint8),
        cv2.COLOR_RGB2HSV,
    ).reshape(-1, 3)
    hsv_raw = cv2.cvtColor(
        raw_pixels.reshape(-1, 1, 3).astype(np.uint8),
        cv2.COLOR_RGB2HSV,
    ).reshape(-1, 3)
    source_value_mean = float(hsv_source[:, 2].mean()) / 255.0
    source_sat_median = float(np.median(hsv_source[:, 1])) / 255.0
    raw_value_mean = float(hsv_raw[:, 2].mean()) / 255.0
    source_hue_entropy = _hue_entropy(hsv_source)
    raw_hue_entropy = _hue_entropy(hsv_raw)

    dark_or_neutral = source_value_mean < 0.28 or features.sat_mean < 0.075
    color_threshold = 34.0 if dark_or_neutral else 28.0
    value_delta = abs(source_value_mean - raw_value_mean)
    color_passed = color_delta <= color_threshold and value_delta <= (
        0.20 if dark_or_neutral else 0.16
    )

    source_pattern_score = float(features.pattern_score)
    raw_pattern_signal = _pattern_signal(raw_arr, raw_mask)
    pattern_required = source_pattern_score >= 0.32 or features.pattern_confidence >= 0.70
    if not pattern_required:
        pattern_passed = True
    elif source_pattern_score >= 0.70:
        pattern_passed = raw_pattern_signal >= max(0.08, source_pattern_score * 0.35)
    else:
        pattern_passed = raw_pattern_signal >= 0.045

    artifact_score = _region_artifact_score(raw_arr, raw_mask)
    artifact_passed = artifact_score <= 0.34

    from app.services.tryon_v2.category_utils import is_lower_garment_category

    # Detect CatVTON "solid pant panel": outer silhouette OK but no crotch split /
    # fabric folds. Saturated solids used to score pattern_signal≈1.0 via chroma.
    gray_raw = cv2.cvtColor(raw_arr.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    gray_src = cv2.cvtColor(garment_arr.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    source_std = float(gray_src[source_mask].std()) if source_mask.any() else 0.0
    ys, xs = np.where(raw_mask)
    rect_fill = 0.0
    interior_std = 999.0
    interior = raw_mask
    if xs.size > 0:
        bbox_area = float(
            max(1, (int(xs.max()) - int(xs.min()) + 1) * (int(ys.max()) - int(ys.min()) + 1))
        )
        rect_fill = float(xs.size) / bbox_area
        mask_u8 = raw_mask.astype(np.uint8) * 255
        eroded = cv2.erode(mask_u8, np.ones((15, 15), np.uint8), iterations=1)
        interior = eroded > 0
        if interior.any():
            interior_std = float(gray_raw[interior].std())
        else:
            interior_std = float(gray_raw[raw_mask].std())
            interior = raw_mask

    is_lower = is_lower_garment_category(garment_category)
    src_tex = _fabric_texture_score(garment_arr, source_mask)
    raw_tex = _fabric_texture_score(raw_arr, interior if interior.any() else raw_mask)
    texture_collapsed = bool(
        is_lower and src_tex >= 0.08 and raw_tex <= max(0.09, src_tex * 0.95) and raw_tex < 0.12
    )
    solid_leg_blob = bool(is_lower and _lower_result_is_solid_leg_blob(raw_arr, raw_mask))
    flat_color_block = bool(
        is_lower
        and raw_mask.any()
        and float(raw_mask.mean()) >= 0.04
        and (
            (interior_std < max(12.0, source_std * 0.45) and rect_fill >= 0.82)
            or texture_collapsed
            or solid_leg_blob
        )
    )
    if flat_color_block:
        artifact_passed = False
        artifact_score = max(artifact_score, 0.85)
        if texture_collapsed or solid_leg_blob:
            # Prefer a specific reason below for routing to pants warp.
            pass

    white_light_pattern = (
        source_value_mean > 0.76
        and source_sat_median < 0.16
        and features.sat_mean < 0.12
        and features.pattern_score >= 0.12
    )
    strong_white_motif_missing = (
        white_light_pattern
        and source_pattern_score >= 0.70
        and source_hue_entropy >= 0.65
        and raw_hue_entropy < max(0.35, source_hue_entropy * 0.45)
    )
    if strong_white_motif_missing:
        pattern_passed = False

    if color_passed and pattern_passed and artifact_passed:
        decision = "raw"
        reason = "raw_color_pattern_artifacts_passed"
    elif flat_color_block:
        decision = "strong_spatial"
        if solid_leg_blob and texture_collapsed:
            reason = "lower_solid_blob_texture_collapsed"
        elif solid_leg_blob:
            reason = "lower_solid_leg_blob_no_crotch"
        elif texture_collapsed:
            reason = "lower_fabric_texture_collapsed"
        else:
            reason = "flat_color_block_mask_paste"
    elif color_passed and pattern_passed:
        decision = "artifact_only"
        reason = (
            "white_light_pattern_artifact_only"
            if white_light_pattern
            else "raw_color_pattern_ok_artifact_only"
        )
    elif (not color_passed) and pattern_passed:
        decision = "color_only"
        reason = "raw_pattern_ok_color_missing"
    elif color_passed and (not pattern_passed):
        decision = "pattern_only"
        reason = (
            "white_light_motif_hue_missing"
            if strong_white_motif_missing
            else "raw_color_ok_pattern_missing"
        )
    else:
        decision = "strong_spatial"
        reason = "raw_color_and_pattern_missing_or_artifact"

    return RawCatVTONQuality(
        color_passed=bool(color_passed),
        pattern_passed=bool(pattern_passed),
        artifact_passed=bool(artifact_passed),
        decision=decision,
        reason=reason,
        source_value_mean=source_value_mean,
        raw_value_mean=raw_value_mean,
        color_delta=color_delta,
        source_pattern_score=source_pattern_score,
        raw_pattern_signal=raw_pattern_signal,
        artifact_score=artifact_score,
        garment_coverage=float(raw_mask.mean()),
        source_hue_entropy=source_hue_entropy,
        raw_hue_entropy=raw_hue_entropy,
    )


def repair_raw_catvton_artifacts(
    *,
    raw_result: Image.Image,
    person_image: Image.Image,
    garment_category: str,
    raw_mask_image: Image.Image | None = None,
) -> tuple[Image.Image, dict]:
    """Conservatively repair obvious raw CatVTON patches without re-warping the garment."""
    raw_rgb = raw_result.convert("RGB")
    arr = np.asarray(raw_rgb, dtype=np.uint8)
    mask = _normalize_optional_mask(raw_mask_image, raw_rgb.size)
    if mask is None:
        mask = _estimate_raw_garment_mask(
            raw_result=raw_rgb,
            person_image=person_image,
            garment_category=garment_category,
        )
    if not mask.any():
        return raw_result, {
            "engine": "raw_artifact_repair",
            "artifact_repair_applied": False,
            "reason": "empty_mask",
        }

    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY).astype(np.float32)
    local = cv2.GaussianBlur(gray, (21, 21), 0)
    resid = np.abs(gray - local)

    pale = (val > 238) & (sat < 34) & (resid > 10)
    dark = (val < 14) & (resid > 8)
    block = resid > max(24.0, float(np.percentile(resid[mask], 96)))
    candidate = (pale | dark | block) & mask

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidate.astype(np.uint8), 8)
    clean = np.zeros(mask.shape, dtype=np.uint8)
    max_area = max(64, int(mask.sum() * 0.10))
    min_area = max(8, int(mask.sum() * 0.0005))
    for label in range(1, n_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if min_area <= area <= max_area:
            clean[labels == label] = 255

    repair_ratio = float((clean > 0).sum()) / float(max(1, mask.sum()))
    if repair_ratio <= 0.0005 or repair_ratio > 0.12:
        return raw_result, {
            "engine": "raw_artifact_repair",
            "artifact_repair_applied": False,
            "reason": "no_safe_candidates",
            "artifact_repair_ratio": round(repair_ratio, 5),
            "garment_coverage": round(float(mask.mean()), 5),
        }

    clean = cv2.dilate(clean, np.ones((3, 3), dtype=np.uint8), iterations=1)
    repaired = cv2.inpaint(arr, clean, 3, cv2.INPAINT_TELEA)
    alpha = (cv2.GaussianBlur(clean.astype(np.float32) / 255.0, (9, 9), 0) * 0.35)[:, :, None]
    out = np.clip(
        arr.astype(np.float32) * (1.0 - alpha) + repaired.astype(np.float32) * alpha, 0, 255
    )
    return Image.fromarray(out.astype(np.uint8), mode="RGB"), {
        "engine": "raw_artifact_repair",
        "artifact_repair_applied": True,
        "artifact_repair_ratio": round(repair_ratio, 5),
        "garment_coverage": round(float(mask.mean()), 5),
    }


def score_input_anomaly(image: Image.Image) -> InputAnomalyScore:
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    if h < 32 or w < 32:
        return InputAnomalyScore(0.0, 0.0, True)

    left = arr[:, : w // 2, :]
    right = arr[:, w - (w // 2) :, :][:, ::-1, :]
    if left.shape != right.shape:
        min_w = min(left.shape[1], right.shape[1])
        left = left[:, :min_w, :]
        right = right[:, :min_w, :]
    mirror_diff = float(np.abs(left - right).mean()) / 255.0
    mirror_ghost_score = _clamp01(1.0 - mirror_diff * 4.0)

    gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F).var()
    jpeg_artifact_score = _clamp01(max(0.0, (18.0 - lap) / 18.0))

    passed = mirror_ghost_score <= 0.35
    return InputAnomalyScore(
        mirror_ghost_score=mirror_ghost_score,
        jpeg_artifact_score=jpeg_artifact_score,
        passed=passed,
    )


def evaluate_cutout_alpha_qc(rgba: Image.Image) -> CutoutAlphaQC:
    arr = np.asarray(rgba.convert("RGBA"), dtype=np.uint8)
    alpha = arr[:, :, 3]
    mask = alpha > 20
    h, w = mask.shape
    total = max(1, h * w)
    fg = int(mask.sum())
    alpha_coverage = fg / float(total)

    if fg == 0:
        return CutoutAlphaQC(0.0, 0, 0.0, 0.0, 1.0, 1.0, False, "empty_alpha")

    u8 = mask.astype(np.uint8)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(u8, connectivity=8)
    alpha_component_count = max(0, n_labels - 1)
    largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if n_labels > 1 else 0
    largest_component_ratio = largest / float(max(1, fg))

    ys, xs = np.where(mask)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    bbox_area = max(1, (x1 - x0) * (y1 - y0))
    bbox_fill_ratio = bbox_area / float(total)

    edge_count = int(mask[0, :].sum() + mask[-1, :].sum() + mask[:, 0].sum() + mask[:, -1].sum())
    edge_total = max(1, (2 * w) + (2 * h))
    edge_touch_ratio = edge_count / float(edge_total)

    hsv = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    bg_like = (val > 230) & (sat < 25)
    background_leak_ratio = float((bg_like & mask).sum()) / float(max(1, fg))

    passed = (
        0.08 <= alpha_coverage <= 0.75
        and alpha_component_count <= 4
        and largest_component_ratio >= 0.82
        and 0.18 <= bbox_fill_ratio <= 0.88
        and edge_touch_ratio <= 0.12
        and background_leak_ratio <= 0.22
    )
    reason = "ok" if passed else "cutout_qc_failed"
    return CutoutAlphaQC(
        alpha_coverage=alpha_coverage,
        alpha_component_count=alpha_component_count,
        largest_component_ratio=largest_component_ratio,
        bbox_fill_ratio=bbox_fill_ratio,
        edge_touch_ratio=edge_touch_ratio,
        background_leak_ratio=background_leak_ratio,
        passed=passed,
        reason=reason,
    )


def extract_engine_decision_features(image: Image.Image) -> EngineDecisionFeatures:
    arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    brightness_mask = (val >= 15) & (val <= 240)
    white_bg_mask = (val > 220) & (sat < 30)
    fg_mask = brightness_mask & ~white_bg_mask
    fg_sat = sat[fg_mask]
    fg_val = val[fg_mask]

    if len(fg_sat) < 30:
        sat_mean = 0.0
        sat_max = 0.0
        bright_mean = float(val.mean()) / 255.0
    else:
        sat_mean = float(fg_sat.mean()) / 255.0
        sat_max = float(fg_sat.max()) / 255.0
        bright_mean = float(fg_val.mean()) / 255.0 if len(fg_val) else 0.0

    pattern_score = float(detect_pattern_strength(image))
    has_color = sat_max > 0.15
    is_white_garment = bright_mean > 0.78 and sat_mean < 0.08 and pattern_score < 0.25
    contrast_signal = abs(sat_max - sat_mean)
    pattern_confidence = _clamp01(max(0.35, pattern_score) + contrast_signal * 1.5)

    return EngineDecisionFeatures(
        sat_mean=sat_mean,
        sat_max=sat_max,
        bright_mean=bright_mean,
        is_white_garment=is_white_garment,
        has_color=has_color,
        pattern_score=pattern_score,
        pattern_confidence=pattern_confidence,
    )


def decide_color_fidelity_engine(
    *,
    features: EngineDecisionFeatures,
    cutout_passed: bool,
    input_anomaly_passed: bool,
) -> tuple[str, str]:
    strong_product_pattern = (
        features.pattern_score > 0.70
        and features.pattern_confidence >= 0.55
        and (features.has_color or features.sat_max >= 0.18)
    )
    if not input_anomaly_passed:
        # Flat product photos of T-shirts are often intentionally symmetric.
        # Do not treat that alone as a hard failure when the garment cutout is
        # clean and the image carries clear print/logo detail to preserve.
        if not (
            (cutout_passed or strong_product_pattern)
            and features.pattern_score > 0.45
            and features.pattern_confidence >= 0.45
        ):
            return "skip", "input_anomaly_failed"
    if not cutout_passed:
        if not strong_product_pattern:
            return "skip", "cutout_qc_failed"
    if features.is_white_garment:
        return "skip", "white_garment"

    # Hysteresis guard band to reduce branch jitter near threshold.
    if 0.38 <= features.pattern_score <= 0.45:
        return "uniform", "guard_band_conservative"

    if features.pattern_confidence < 0.45:
        return "uniform", "low_pattern_confidence"

    if (
        features.pattern_score > 0.45
        and features.pattern_confidence >= 0.45
        and (features.sat_max > 0.25 or not features.is_white_garment)
    ):
        return "spatial", "pattern_spatial"

    if features.sat_mean >= 0.05 or features.has_color or features.pattern_score >= 0.25:
        return "uniform", "solid_or_low_pattern"

    return "skip", "low_saturation"


def detect_post_cf_artifacts(before_cf: Image.Image, after_cf: Image.Image) -> ArtifactReport:
    b = np.asarray(before_cf.convert("RGB"), dtype=np.float32)
    a = np.asarray(after_cf.convert("RGB"), dtype=np.float32)
    h = min(b.shape[0], a.shape[0])
    w = min(b.shape[1], a.shape[1])
    if h < 8 or w < 8:
        return ArtifactReport(0.0, 0.0, False, 0.0, 0.0, 0.0)
    b = b[:h, :w, :]
    a = a[:h, :w, :]

    diff = np.abs(a - b).mean(axis=2)
    outlier_ratio = float((diff > 55.0).mean())

    gray = cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    low = cv2.GaussianBlur(gray, (11, 11), 0)
    resid = np.abs(gray - low)
    blockiness_score = _clamp01(float(np.percentile(resid, 92)) / 45.0)
    change_mask = diff > 20.0

    horizontal_hard_edge_score = 0.0
    luminance_mismatch_score = 0.0
    rectangular_overlay_score = 0.0

    if int(change_mask.sum()) >= 64:
        row_strength = np.abs(np.diff(diff, axis=0)).mean(axis=1)
        col_strength = np.abs(np.diff(diff, axis=1)).mean(axis=0)
        row_peak = float(np.percentile(row_strength, 99))
        col_peak = float(np.percentile(col_strength, 99))
        horizontal_hard_edge_score = _clamp01((row_peak - col_peak * 0.72) / 42.0)

        gray_before = cv2.cvtColor(b.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
        low_before = cv2.GaussianBlur(gray_before, (31, 31), 0)
        low_after = cv2.GaussianBlur(gray, (31, 31), 0)
        changed = change_mask.astype(bool)
        if np.any(changed):
            lum_gap = np.abs(low_after[changed] - low_before[changed]).mean()
            edge_shell = cv2.dilate(
                change_mask.astype(np.uint8) * 255, np.ones((9, 9), np.uint8), iterations=1
            )
            edge_shell = (edge_shell > 0) & ~changed
            shell_gap = (
                np.abs(low_after[edge_shell] - low_before[edge_shell]).mean()
                if np.any(edge_shell)
                else lum_gap
            )
            luminance_mismatch_score = _clamp01((lum_gap * 0.65 + shell_gap * 0.35) / 40.0)

            ys, xs = np.where(changed)
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            bbox_fill = float(changed[y0:y1, x0:x1].mean())
            row_widths: list[float] = []
            for y in range(y0, y1):
                row_x = np.where(changed[y, :])[0]
                if row_x.size:
                    row_widths.append(float(row_x[-1] - row_x[0] + 1))
            width_cv = 0.0
            if row_widths:
                row_width_arr = np.asarray(row_widths, dtype=np.float32)
                width_cv = float(row_width_arr.std() / max(1.0, row_width_arr.mean()))
            rectangular_overlay_score = _clamp01(
                max(0.0, bbox_fill - 0.72) * 1.8 + max(0.0, 0.18 - width_cv) * 2.6
            )

    failed = (
        blockiness_score > 0.30
        or outlier_ratio > 0.08
        or horizontal_hard_edge_score > 0.32
        or luminance_mismatch_score > 0.42
        or rectangular_overlay_score > 0.36
    )
    return ArtifactReport(
        blockiness_score=blockiness_score,
        outlier_ratio=outlier_ratio,
        failed=failed,
        horizontal_hard_edge_score=horizontal_hard_edge_score,
        luminance_mismatch_score=luminance_mismatch_score,
        rectangular_overlay_score=rectangular_overlay_score,
    )


def estimate_pattern_enhance_strength(
    *,
    pattern_score: float,
    artifact_report: ArtifactReport | None,
    result_image: Image.Image,
) -> float:
    if artifact_report is not None and artifact_report.failed:
        return 0.0

    arr = np.asarray(result_image.convert("RGB"), dtype=np.float32)
    gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    noise = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    base = 1.05 + _clamp01(pattern_score) * 0.30
    noise_factor = 0.85 if noise > 220.0 else 1.0
    strength = base * noise_factor
    return float(max(0.0, min(1.35, strength)))
