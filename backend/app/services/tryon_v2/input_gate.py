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
    "bottom",
    "pants",
    "jeans",
)

_TOP_KEYWORDS = (
    "上装",
    "上衣",
    "t恤",
    "t-shirt",
    "shirt",
    "top",
    "upper",  # returned by _map_to_tryon_category as fallback for misclassified shoes/bags
    "hoodie",
    "sweater",
    "外套",
    "jacket",
    "coat",
)

_SKIRT_KEYWORDS = (
    "裙",
    "裙装",
    "半身裙",
    "连衣裙",
    "dress",
    "skirt",
)

_OUTFIT_KEYWORDS = (
    "outfit",
    "set",
    "套装",
    "上下装",
    "top+bottom",
    "top_bottom",
)

# NOTE: "shoes", "shoe", "bag", "hat" removed — these are often misclassified
# from T-shirt / top images and should not block try-on. Only clear accessory
# keywords (scarf, shawl, scarf) trigger accessory blocking here.
_ACCESSORY_KEYWORDS = (
    "accessory",
    "围巾",
    "披肩",
    "scarf",
    "shawl",
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


def _score_garment_background_cleanliness(garment_image: Image.Image) -> float:
    """Heuristic: clean product photo tends to have noticeable bright background area."""
    arr = np.asarray(garment_image.convert("RGB"), dtype=np.uint8)
    gray = arr.mean(axis=2)
    sat = arr.max(axis=2) - arr.min(axis=2)
    bg_mask = (gray > 235) & (sat < 18)
    bg_ratio = float(bg_mask.mean())
    # >= 25% clean bg => good; <= 5% => likely poster/scene.
    if bg_ratio >= 0.25:
        return 1.0
    if bg_ratio <= 0.05:
        return 0.0
    return _clamp01((bg_ratio - 0.05) / 0.20)


def _has_any_keyword(garment_category: str | None, keywords: tuple[str, ...]) -> bool:
    gc = (garment_category or "").strip().lower()
    if not gc:
        return False
    return any(k in gc for k in keywords)


def _category_kind(garment_category: str | None, confidence: float | None = None) -> str:
    """Return one of: top|bottom|skirt|outfit|accessory|auto|unknown."""
    gc = (garment_category or "").strip().lower()
    if not gc:
        return "auto"
    if _has_any_keyword(gc, _ACCESSORY_KEYWORDS):
        # Only block high-confidence accessory classifications.
        # Low-confidence accessory (e.g., T-shirt misclassified as shoes) → unknown.
        if confidence is not None and confidence < 0.20:
            return "unknown"
        return "accessory"
    if _has_any_keyword(gc, _OUTFIT_KEYWORDS):
        return "outfit"
    if _has_any_keyword(gc, _BOTTOM_KEYWORDS):
        return "bottom"
    if _has_any_keyword(gc, _SKIRT_KEYWORDS):
        return "skirt"
    if _has_any_keyword(gc, _TOP_KEYWORDS):
        return "top"
    if gc in {"auto", "unknown", "默认"}:
        return "auto"
    return "unknown"


def evaluate_input_gate(
    person_image: Image.Image,
    garment_image: Image.Image,
    garment_category: str | None,
    strict: bool = True,
    thresholds: dict[str, float] | None = None,
    garment_confidence: float | None = None,
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
        "garment_bg_clean_score": _score_garment_background_cleanliness(garment_image),
    }

    kind = _category_kind(garment_category, garment_confidence)
    if kind == "accessory":
        return GateResult(
            passed=False,
            error_code="TRYON_V2_UNSUPPORTED_CATEGORY",
            message="识别为配饰/围巾等非上装商品图：方案A无法做贴身替换试衣。",
            action_hint="请换成真实上衣/下装/裙装商品图；围巾/包/鞋建议走「叠加展示」或衣橱入库，不做贴身替换。",
            retryable=False,
            scores=scores,
        )
    if kind in {"unknown", "auto"}:
        return GateResult(
            passed=False,
            error_code="TRYON_V2_UNSUPPORTED_CATEGORY",
            message="当前仅支持上装/下装/裙装试衣。请将 garment_category 设为 top/bottom/skirt（或上传两件用 outfit）。",
            action_hint="上装：top；下装：bottom；裙装：skirt；两件：outfit。",
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

    # Leg visibility is only required for bottom/skirt/outfit.
    if (
        kind in {"bottom", "skirt", "outfit"}
        and scores["leg_visibility_score"] < leg_visibility_min
    ):
        return GateResult(
            passed=False,
            error_code="TRYON_V2_PERSON_LEG_NOT_VISIBLE",
            message="人物腿部可见度不足，无法稳定贴合下装/裙装。",
            action_hint="请避免遮挡并保证腿部清晰可见（建议全身站姿）。",
            retryable=False,
            scores=scores,
        )

    # Front-view check is important for stable geometric warps, but selfie / phone / bag
    # often breaks left-right symmetry. Relax for top/skirt in balanced mode.
    effective_front_pose_min = front_pose_min
    if not strict and kind in {"top", "skirt"}:
        effective_front_pose_min = max(0.0, front_pose_min - 0.12)

    if scores["front_pose_score"] < effective_front_pose_min:
        return GateResult(
            passed=False,
            error_code="TRYON_V2_PERSON_NOT_FRONT_VIEW",
            message="人物图偏离正面视角，建议使用正面站姿图。",
            action_hint="请上传正面拍摄的人像；自拍/侧身过大时建议换站姿正面照。",
            retryable=False,
            scores=scores,
        )

    if scores["garment_front_score"] < garment_front_min:
        return GateResult(
            passed=False,
            error_code="TRYON_V2_GARMENT_NOT_FRONT_VIEW",
            message="商品图不够清晰或主体不完整，无法进行稳定贴合。",
            action_hint="请上传正面、主体完整、背景干净的商品图。",
            retryable=False,
            scores=scores,
        )

    # Background complexity is handled by auto-preprocess (crop + GrabCut + white background).
    # Do NOT hard-fail here; keep as a score for UI hints.

    return GateResult(
        passed=True,
        error_code=None,
        message="ok",
        action_hint=None,
        retryable=False,
        scores=scores,
    )
