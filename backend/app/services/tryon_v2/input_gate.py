"""Input gate and quality score heuristics for Try-on v2 pipeline A."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

_BOTTOM_KEYWORDS = (
    "下装",
    "裤",
    "裤装",
    "短裤",
    "牛仔",
    "裙",
    "裙装",
    "dress",
    "skirt",
    "bottom",
    "pants",
    "jeans",
)


@dataclass
class GateResult:
    passed: bool
    error_code: str | None
    message: str
    action_hint: str | None
    retryable: bool
    scores: dict[str, float]


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _score_full_body(person_image: Image.Image) -> float:
    w, h = person_image.size
    ratio = h / max(float(w), 1.0)
    if ratio >= 1.6:
        return 1.0
    if ratio <= 1.0:
        return 0.15
    return _clamp01((ratio - 1.0) / 0.6)


def _score_leg_visibility(person_image: Image.Image) -> float:
    arr = np.asarray(person_image.convert("L"), dtype=np.float32)
    h = arr.shape[0]
    lower = arr[int(h * 0.55) :, :]
    std = float(lower.std())
    return _clamp01(std / 55.0)


def _score_front_pose(person_image: Image.Image) -> float:
    arr = np.asarray(person_image.convert("L"), dtype=np.float32)
    h, w = arr.shape
    mid = w // 2
    left = arr[:, :mid]
    right = arr[:, w - mid :]
    right_flip = np.flip(right, axis=1)
    diff = np.abs(left - right_flip).mean() if left.size and right_flip.size else 255.0
    return _clamp01(1.0 - diff / 120.0)


def _score_garment_front(garment_image: Image.Image) -> float:
    arr = np.asarray(garment_image.convert("RGB"), dtype=np.uint8)
    gray = arr.mean(axis=2)
    sat = arr.max(axis=2) - arr.min(axis=2)
    # Very bright + low saturation pixels are likely background.
    bg_mask = (gray > 235) & (sat < 18)
    fg_ratio = 1.0 - float(bg_mask.mean())
    return _clamp01((fg_ratio - 0.1) / 0.45)


def _is_bottom_category(garment_category: str | None) -> bool:
    gc = (garment_category or "").strip().lower()
    if not gc:
        return False
    return any(k in gc for k in _BOTTOM_KEYWORDS)


def evaluate_input_gate(
    person_image: Image.Image,
    garment_image: Image.Image,
    garment_category: str | None,
    strict: bool = True,
    thresholds: dict[str, float] | None = None,
) -> GateResult:
    thresholds = thresholds or {}
    full_body_min = float(thresholds.get("full_body", 0.55 if strict else 0.45))
    leg_visibility_min = float(thresholds.get("leg_visibility", 0.45 if strict else 0.35))
    front_pose_min = float(thresholds.get("front_pose", 0.35 if strict else 0.25))
    garment_front_min = float(thresholds.get("garment_front", 0.45 if strict else 0.35))

    scores = {
        "full_body_score": _score_full_body(person_image),
        "leg_visibility_score": _score_leg_visibility(person_image),
        "front_pose_score": _score_front_pose(person_image),
        "garment_front_score": _score_garment_front(garment_image),
    }

    if not _is_bottom_category(garment_category):
        return GateResult(
            passed=False,
            error_code="TRYON_V2_UNSUPPORTED_CATEGORY",
            message="当前仅支持下装试衣，请将 garment_category 设为 bottom/下装/裤装/裙装。",
            action_hint="请上传下装商品图并设置 garment_category=bottom。",
            retryable=False,
            scores=scores,
        )

    if scores["full_body_score"] < full_body_min:
        return GateResult(
            passed=False,
            error_code="TRYON_V2_PERSON_NOT_FULL_BODY",
            message="人物图未满足全身要求，请上传完整站立照片。",
            action_hint="请确保头顶到脚部完整入镜。",
            retryable=False,
            scores=scores,
        )

    if scores["leg_visibility_score"] < leg_visibility_min:
        return GateResult(
            passed=False,
            error_code="TRYON_V2_PERSON_LEG_NOT_VISIBLE",
            message="人物腿部可见度不足，无法稳定贴合下装。",
            action_hint="请避免遮挡并保证腿部清晰可见。",
            retryable=False,
            scores=scores,
        )

    if scores["front_pose_score"] < front_pose_min:
        return GateResult(
            passed=False,
            error_code="TRYON_V2_PERSON_NOT_FRONT_VIEW",
            message="人物图偏离正面视角，建议使用正面站姿图。",
            action_hint="请上传正面拍摄的人像。",
            retryable=False,
            scores=scores,
        )

    if scores["garment_front_score"] < garment_front_min:
        return GateResult(
            passed=False,
            error_code="TRYON_V2_GARMENT_NOT_FRONT_VIEW",
            message="下装商品图不够清晰或非正面，无法进行稳定贴合。",
            action_hint="请上传正面、主体完整、背景干净的商品图。",
            retryable=False,
            scores=scores,
        )

    return GateResult(
        passed=True,
        error_code=None,
        message="ok",
        action_hint=None,
        retryable=False,
        scores=scores,
    )
