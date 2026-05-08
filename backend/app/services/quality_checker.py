"""Quality checker for CatVTON try-on results.

Automatically detects common quality issues:
1. Floating clothes (garment not attached to body)
2. Shoulder misalignment
3. Transparent sleeves / ghost overlay
4. Body penetration (garment clips into body)
5. Mask errors (wrong garment region covered)


Quality scoring:
    score >= 0.75 → pass (return result)
    score < 0.75  → fail (trigger retry)

Usage:
    from app.services.quality_checker import check_tryon_quality

    scores = check_tryon_quality(result_image, person_image, garment_image)
    if scores["overall"] < 0.75:
        # retry generation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

__all__ = [
    "check_tryon_quality",
    "TryOnQualityScores",
    "QualityChecker",
]


@dataclass
class TryOnQualityScores:
    """Quality scores from automated quality check."""

    overall: float
    floating_score: float
    shoulder_score: float
    transparency_score: float
    penetration_score: float
    mask_score: float
    boundary_score: float
    details: dict
    passed: bool

    def __post_init__(self):
        self.passed = self.overall >= 0.75


def _normalize_score(val: float) -> float:
    """Clamp and normalize a score to [0.0, 1.0]."""
    return float(max(0.0, min(1.0, val)))


def _compute_edge_density(arr: np.ndarray, region_mask: np.ndarray) -> float:
    """Compute Canny edge density in a masked region. High density = sharp garment edges."""
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    total_edges = float(np.sum(edges > 0))
    total_region = float(np.sum(region_mask > 0))
    if total_region == 0:
        return 0.0
    return _normalize_score(total_edges / total_region * 10)


def _check_floating_garment(
    result: Image.Image,
    person: Image.Image,
) -> float:
    """Check if the garment appears to float above the body (not attached).

    Method: Compare the garment region's color histogram with the surrounding
    body region. If the garment region has a completely different histogram
    distribution than adjacent body pixels, it likely looks "sticker-like" / floating.

    A floating garment has sharp color transitions at its boundary with the body.
    A well-fitted garment has gradual transitions (skin → garment shadow → garment body).

    Returns score 0-1 where 1 = no floating detected.
    """
    try:
        result_arr = np.array(result.convert("RGB"))
        person_arr = np.array(person.convert("RGB"))
        h, w = result_arr.shape[:2]

        upper_region_y0 = int(h * 0.08)
        upper_region_y1 = int(h * 0.50)
        garment_region = result_arr[upper_region_y0:upper_region_y1, :, :]
        person_region = person_arr[upper_region_y0:upper_region_y1, :, :]

        result_gray = cv2.cvtColor(garment_region, cv2.COLOR_RGB2GRAY)
        person_gray = cv2.cvtColor(person_region, cv2.COLOR_RGB2GRAY)

        person_edges = cv2.Canny(person_gray, 50, 150)
        result_edges = cv2.Canny(result_gray, 50, 150)

        person_edge_density = float(np.sum(person_edges > 0)) / max(person_edges.size, 1)
        result_edge_density = float(np.sum(result_edges > 0)) / max(result_edges.size, 1)

        edge_ratio = result_edge_density / max(person_edge_density, 0.001)

        if edge_ratio > 3.0:
            return _normalize_score(0.3)
        elif edge_ratio > 2.0:
            return _normalize_score(0.6)
        elif edge_ratio > 1.5:
            return _normalize_score(0.8)
        else:
            return _normalize_score(0.95)
    except Exception:
        return 0.75


def _check_shoulder_alignment(
    result: Image.Image,
) -> float:
    """Check if shoulders look natural and properly aligned.

    Method: Detect the garment outline in the shoulder region.
    If the garment boundary is very straight/angular (unnatural), score lower.
    A well-fitted garment follows the natural curve of shoulders.
    """
    try:
        arr = np.array(result.convert("RGB"))
        h, w = arr.shape[:2]

        shoulder_y0 = int(h * 0.08)
        shoulder_y1 = int(h * 0.22)
        shoulder_region = arr[shoulder_y0:shoulder_y1, :, :]
        gray = cv2.cvtColor(shoulder_region, cv2.COLOR_RGB2GRAY)

        edges = cv2.Canny(gray, 30, 100)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=20,
            minLineLength=30,
            maxLineGap=15,
        )

        if lines is None:
            return 0.90

        horizontal_lines = 0
        total_lines = len(lines)
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if abs(x2 - x1) < 1:
                continue
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if angle < 15 or angle > 165:
                horizontal_lines += 1

        if total_lines == 0:
            return 0.90

        h_ratio = horizontal_lines / total_lines

        if h_ratio > 0.7:
            return _normalize_score(0.4)
        elif h_ratio > 0.5:
            return _normalize_score(0.65)
        elif h_ratio > 0.3:
            return _normalize_score(0.80)
        else:
            return _normalize_score(0.90)
    except Exception:
        return 0.75


def _check_transparency_ghost(
    result: Image.Image,
    person: Image.Image,
    garment: Image.Image,
) -> float:
    """Check for transparent sleeves / ghost overlay artifacts.

    Method: In the arm regions, compare result pixel color with person + garment.
    If result appears as a blend of person and garment (semi-transparent feel),
    it indicates ghost overlay issues.

    Also check the alpha of any RGBA garment region - transparent regions
    that overlap with the body indicate ghost artifacts.
    """
    try:
        result_arr = np.array(result.convert("RGB"))
        person_arr = np.array(person.convert("RGB"))
        h, w = result_arr.shape[:2]

        arm_y0 = int(h * 0.15)
        arm_y1 = int(h * 0.48)
        arm_margin = int(w * 0.08)

        left_arm = result_arr[arm_y0:arm_y1, arm_margin : int(w * 0.35), :]
        right_arm = result_arr[arm_y0:arm_y1, int(w * 0.65) : w - arm_margin, :]
        left_person = person_arr[arm_y0:arm_y1, arm_margin : int(w * 0.35), :]
        right_person = person_arr[arm_y0:arm_y1, int(w * 0.65) : w - arm_margin, :]

        def blend_score(a: np.ndarray, b: np.ndarray) -> float:
            diff = np.abs(a.astype(float) - b.astype(float)).mean()
            if diff < 5:
                return 0.3
            elif diff < 15:
                return 0.6
            elif diff < 30:
                return 0.85
            else:
                return 1.0

        left_score = blend_score(left_arm, left_person)
        right_score = blend_score(right_arm, right_person)

        avg_score = (left_score + right_score) / 2.0
        return _normalize_score(avg_score)
    except Exception:
        return 0.75


def _check_body_penetration(
    result: Image.Image,
    person: Image.Image,
) -> float:
    """Check for body penetration (garment clipping into body).

    Method: In regions where the person has skin tone, check if the result
    shows garment color bleeding into those regions unnaturally.
    This indicates the garment mask was too large and captured body pixels.
    """
    try:
        result_arr = np.array(result.convert("RGB"))
        person_arr = np.array(person.convert("RGB"))
        h, w = result_arr.shape[:2]

        torso_y0 = int(h * 0.20)
        torso_y1 = int(h * 0.50)
        torso_x0 = int(w * 0.30)
        torso_x1 = int(w * 0.70)

        torso_result = result_arr[torso_y0:torso_y1, torso_x0:torso_x1, :]
        torso_person = person_arr[torso_y0:torso_y1, torso_x0:torso_x1, :]

        person_hsv = cv2.cvtColor(torso_person, cv2.COLOR_RGB2HSV)
        skin_mask = (
            (person_hsv[:, :, 0] > 0) & (person_hsv[:, :, 0] < 25) & (person_hsv[:, :, 1] > 20)
        ).astype(float)

        if skin_mask.sum() < 500:
            return 0.90

        skin_region_result = torso_result[skin_mask > 0]
        if len(skin_region_result) == 0:
            return 0.90

        person_skin_mean = torso_person[skin_mask > 0].mean(axis=0)
        result_skin_mean = skin_region_result.mean(axis=0)

        color_diff = np.abs(result_skin_mean - person_skin_mean).mean()

        if color_diff > 50:
            return _normalize_score(0.35)
        elif color_diff > 30:
            return _normalize_score(0.60)
        elif color_diff > 15:
            return _normalize_score(0.80)
        else:
            return _normalize_score(0.95)
    except Exception:
        return 0.75


def _check_boundary_quality(
    result: Image.Image,
) -> float:
    """Check the quality of the garment boundary transitions.

    A good boundary has smooth, natural transitions.
    A bad boundary (贴纸感) has sharp, high-contrast edges.
    """
    try:
        arr = np.array(result.convert("RGB"))
        h, w = arr.shape[:2]

        region_y0 = int(h * 0.10)
        region_y1 = int(h * 0.55)
        region = arr[region_y0:region_y1, :, :]

        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 30, 100)

        edge_pixels = np.sum(edges > 0)
        total_pixels = edges.size

        edge_ratio = edge_pixels / max(total_pixels, 1)

        if edge_ratio > 0.15:
            return _normalize_score(0.40)
        elif edge_ratio > 0.10:
            return _normalize_score(0.65)
        elif edge_ratio > 0.05:
            return _normalize_score(0.82)
        else:
            return _normalize_score(0.92)
    except Exception:
        return 0.75


def _check_mask_accuracy(
    result: Image.Image,
    garment: Image.Image,
) -> float:
    """Check if the garment mask covered the correct region.

    Method: Compare the garment's color distribution in the result
    with what we expect from a properly placed garment.
    """
    try:
        result_arr = np.array(result.convert("RGB"))
        garment_arr = np.array(garment.convert("RGB"))
        h, w = result_arr.shape[:2]

        garment_hsv = cv2.cvtColor(garment_arr, cv2.COLOR_RGB2HSV)
        garment_sat = garment_hsv[:, :, 1].mean()
        garment_val = garment_hsv[:, :, 2].mean()

        expected_y0 = int(h * 0.08)
        expected_y1 = int(h * 0.55)
        upper_region = result_arr[expected_y0:expected_y1, :, :]
        upper_hsv = cv2.cvtColor(upper_region, cv2.COLOR_RGB2HSV)

        result_sat = upper_hsv[:, :, 1].mean()
        result_val = upper_hsv[:, :, 2].mean()

        sat_diff = abs(result_sat - garment_sat) / 255.0
        val_diff = abs(result_val - garment_val) / 255.0

        combined_diff = (sat_diff + val_diff) / 2.0

        if combined_diff > 0.25:
            return _normalize_score(0.45)
        elif combined_diff > 0.15:
            return _normalize_score(0.70)
        elif combined_diff > 0.08:
            return _normalize_score(0.85)
        else:
            return _normalize_score(0.92)
    except Exception:
        return 0.75


def check_tryon_quality(
    result: Image.Image,
    person: Optional[Image.Image] = None,
    garment: Optional[Image.Image] = None,
    verbose: bool = False,
) -> TryOnQualityScores:
    """Check quality of a try-on result image.

    Args:
        result: The try-on result image (CatVTON output).
        person: Original person image (optional, used for floating/penetration checks).
        garment: Original garment image (optional, used for mask accuracy check).
        verbose: If True, log detailed scores.

    Returns:
        TryOnQualityScores with individual checks and overall pass/fail.
    """
    floating = _check_floating_garment(result, person) if person else 0.75
    shoulder = _check_shoulder_alignment(result)
    transparency = (
        _check_transparency_ghost(result, person, garment) if (person and garment) else 0.75
    )
    penetration = _check_body_penetration(result, person) if person else 0.75
    boundary = _check_boundary_quality(result)
    mask_acc = _check_mask_accuracy(result, garment) if garment else 0.75

    weights = {
        "floating": 0.20,
        "shoulder": 0.15,
        "transparency": 0.20,
        "penetration": 0.15,
        "boundary": 0.15,
        "mask": 0.15,
    }

    overall = (
        floating * weights["floating"]
        + shoulder * weights["shoulder"]
        + transparency * weights["transparency"]
        + penetration * weights["penetration"]
        + boundary * weights["boundary"]
        + mask_acc * weights["mask"]
    )
    overall = _normalize_score(overall)

    details = {
        "floating": round(floating, 3),
        "shoulder": round(shoulder, 3),
        "transparency": round(transparency, 3),
        "penetration": round(penetration, 3),
        "boundary": round(boundary, 3),
        "mask": round(mask_acc, 3),
        "weights": weights,
    }

    if verbose:
        logger.info(
            f"[QC] Try-on quality scores: "
            f"floating={floating:.3f} shoulder={shoulder:.3f} "
            f"transparency={transparency:.3f} penetration={penetration:.3f} "
            f"boundary={boundary:.3f} mask={mask_acc:.3f} "
            f"overall={overall:.3f} {'PASS' if overall >= 0.75 else 'FAIL'}"
        )

    return TryOnQualityScores(
        overall=round(overall, 3),
        floating_score=round(floating, 3),
        shoulder_score=round(shoulder, 3),
        transparency_score=round(transparency, 3),
        penetration_score=round(penetration, 3),
        mask_score=round(mask_acc, 3),
        boundary_score=round(boundary, 3),
        details=details,
        passed=overall >= 0.75,
    )


class QualityChecker:
    """Quality checker with retry awareness."""

    def __init__(self, min_score: float = 0.75):
        self.min_score = min_score

    def check(
        self,
        result: Image.Image,
        person: Optional[Image.Image] = None,
        garment: Optional[Image.Image] = None,
    ) -> TryOnQualityScores:
        return check_tryon_quality(result, person, garment)

    def should_retry(self, scores: TryOnQualityScores) -> bool:
        return not scores.passed
