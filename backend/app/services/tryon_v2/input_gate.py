"""Input gate and quality score heuristics for Try-on v2 pipeline A."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.services.tryon_v2.category_utils import LOWER_KEYWORDS, SKIRT_KEYWORDS, TOP_KEYWORDS

_BOTTOM_KEYWORDS = LOWER_KEYWORDS

_TOP_KEYWORDS = TOP_KEYWORDS

_SKIRT_KEYWORDS = SKIRT_KEYWORDS

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
# keywords (scarf, shawl) trigger accessory blocking here.
_ACCESSORY_KEYWORDS = (
    "accessory",
    "围巾",
    "披肩",
    "scarf",
    "shawl",
)

_LOWER_POSE_KEYS = (
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
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


def _score_full_body_aspect(person_image: Image.Image) -> float:
    """Aspect-ratio heuristic. NOTE: after 3:4 CatVTON crop this tops out near 0.56."""
    w, h = person_image.size
    ratio = h / max(float(w), 1.0)
    if ratio >= 1.6:
        return 1.0
    if ratio <= 1.0:
        return 0.15
    return _clamp01((ratio - 1.0) / 0.6)


def _score_full_body_pose_span(person_image: Image.Image) -> float | None:
    """Pose-based full-body score from head/shoulder → ankle vertical span.

    Returns None when pose is unavailable so callers can fall back to aspect ratio.
    """
    try:
        from app.services.tryon_v2.pose_utils import detect_pose_keypoints

        kpts = detect_pose_keypoints(person_image)
    except Exception:
        return None
    if not kpts:
        return None

    top_ys: list[float] = []
    for key in ("nose", "left_eye", "right_eye", "left_shoulder", "right_shoulder"):
        pt = kpts.get(key)
        if pt is not None:
            top_ys.append(float(pt[1]))
    ankle_ys: list[float] = []
    for key in ("left_ankle", "right_ankle"):
        pt = kpts.get(key)
        if pt is not None:
            ankle_ys.append(float(pt[1]))
    if not top_ys or not ankle_ys:
        return None

    span = max(ankle_ys) - min(top_ys)
    # Normalized keypoints: full standing body typically spans ~0.55–0.85 of frame.
    if span >= 0.62:
        return 1.0
    if span >= 0.50:
        return 0.85
    if span >= 0.40:
        return 0.70
    return _clamp01(span / 0.40)


def _score_full_body(person_image: Image.Image) -> float:
    """Full-body score = max(aspect, pose span).

    Critical: `/garment` normalizes people to 768x1024 (ratio≈1.333) before the
    lower input gate. Pure aspect scoring then returns ≈0.556 and always fails
    the pants threshold (0.65). Pose span recovers true full-body photos.
    """
    aspect = _score_full_body_aspect(person_image)
    pose = _score_full_body_pose_span(person_image)
    if pose is None:
        return aspect
    return max(aspect, pose)


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


def _score_lower_pose_keypoints(person_image: Image.Image) -> float:
    """Score hip/knee/ankle keypoint completeness for pants try-on.

    Returns:
        0..1 when pose is available; -1.0 when pose detection is unavailable
        (caller should skip the hard fail in that case).
    """
    try:
        from app.services.tryon_v2.pose_utils import detect_pose_keypoints

        kpts = detect_pose_keypoints(person_image)
    except Exception:
        return -1.0
    if not kpts:
        return -1.0
    present = sum(1 for key in _LOWER_POSE_KEYS if kpts.get(key) is not None)
    return present / float(len(_LOWER_POSE_KEYS))


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
    lower_pose_min = float(thresholds.get("lower_pose", 0.67 if strict else 0.50))

    kind = _category_kind(garment_category, garment_confidence)

    # Pants try-on needs a stricter full-body / leg visibility bar.
    if kind in {"bottom", "outfit"}:
        full_body_min = max(full_body_min, 0.65 if strict else 0.55)
        leg_visibility_min = max(leg_visibility_min, 0.55 if strict else 0.45)

    scores = {
        "full_body_score": _score_full_body(person_image),
        "leg_visibility_score": _score_leg_visibility(person_image),
        "front_pose_score": _score_front_pose(person_image),
        "garment_front_score": _score_garment_front(garment_image),
        "garment_bg_clean_score": _score_garment_background_cleanliness(garment_image),
        "lower_pose_score": (
            _score_lower_pose_keypoints(person_image)
            if kind in {"bottom", "skirt", "outfit"}
            else 1.0
        ),
    }

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
        message = (
            "请上传完整站立全身照，确保腰部、双腿、脚踝清晰可见。"
            if kind in {"bottom", "skirt", "outfit"}
            else "人物图未满足全身要求，请上传完整站立照片。"
        )
        return GateResult(
            passed=False,
            error_code="TRYON_V2_PERSON_NOT_FULL_BODY",
            message=message,
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
            message="请上传完整站立全身照，确保腰部、双腿、脚踝清晰可见。",
            action_hint="请避免遮挡并保证腿部清晰可见（建议全身站姿）。",
            retryable=False,
            scores=scores,
        )

    if (
        kind in {"bottom", "outfit"}
        and scores["lower_pose_score"] >= 0.0
        and scores["lower_pose_score"] < lower_pose_min
    ):
        return GateResult(
            passed=False,
            error_code="TRYON_V2_PERSON_LEG_NOT_VISIBLE",
            message="请上传完整站立全身照，确保腰部、双腿、脚踝清晰可见。",
            action_hint="裤装试衣需要检测到髋、膝、踝关键点；请换一张双腿完整入镜的全身照。",
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

    # White-bg pants product photos often letterbox to a small FG ratio after
    # preprocess, which unfairly tanks garment_front_score. Prefer pants QC.
    effective_garment_front_min = garment_front_min
    if kind == "bottom" and scores["garment_bg_clean_score"] >= 0.70:
        effective_garment_front_min = min(garment_front_min, 0.22)
        try:
            from app.services.tryon_v2.garment_struct import cutout_garment_rgba
            from app.services.tryon_v2.preprocess import evaluate_lower_garment_qc

            cutout = cutout_garment_rgba(garment_image, cloth_type="lower")
            pants_qc = evaluate_lower_garment_qc(cutout.cropped)
            scores["pants_qc_score"] = float(pants_qc.get("score") or 0.0)
            if not pants_qc.get("passed"):
                return GateResult(
                    passed=False,
                    error_code="TRYON_V2_GARMENT_NOT_FRONT_VIEW",
                    message=str(
                        pants_qc.get("message")
                        or "请上传单条裤子的正面白底商品图，裤腰和裤脚需要完整入镜。"
                    ),
                    action_hint="请上传正面、裤腰和裤脚完整、背景干净的裤子商品图。",
                    retryable=False,
                    scores=scores,
                )
            # Pants silhouette looks valid on a clean background — skip weak FG ratio.
            effective_garment_front_min = 0.0
        except Exception:
            pass

    if scores["garment_front_score"] < effective_garment_front_min:
        message = (
            "请上传单条裤子的正面白底商品图，裤腰和裤脚需要完整入镜。"
            if kind == "bottom"
            else "商品图不够清晰或主体不完整，无法进行稳定贴合。"
        )
        return GateResult(
            passed=False,
            error_code="TRYON_V2_GARMENT_NOT_FRONT_VIEW",
            message=message,
            action_hint=(
                "请上传单条裤子的正面白底商品图，裤腰和裤脚需要完整入镜。"
                if kind == "bottom"
                else "请上传正面、主体完整、背景干净的商品图。"
            ),
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
