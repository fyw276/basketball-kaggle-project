"""Quality scoring for Try-on v2 pipeline A outputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.services.tryon_v2.occlusion_blend import occlusion_validity_score


@dataclass
class QCResult:
    passed: bool
    threshold: float
    scores: dict[str, float]
    message: str
    action_hint: str


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _to_gray_arr(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32)


def _identity_preserve_score(person_image: Image.Image, result_image: Image.Image) -> float:
    """Measure how similar upper body/head region remains after try-on."""
    p = _to_gray_arr(person_image)
    r = _to_gray_arr(result_image)
    h = min(p.shape[0], r.shape[0])
    w = min(p.shape[1], r.shape[1])
    if h <= 0 or w <= 0:
        return 0.0

    p = p[:h, :w]
    r = r[:h, :w]
    y0 = 0
    y1 = max(1, int(h * 0.42))
    x0 = int(w * 0.2)
    x1 = max(x0 + 1, int(w * 0.8))

    diff = np.abs(p[y0:y1, x0:x1] - r[y0:y1, x0:x1]).mean()
    # 0 diff => 1.0, large diff => 0.0
    return _clamp01(1.0 - (diff / 60.0))


def _boundary_artifact_score(person_image: Image.Image, result_image: Image.Image) -> float:
    """Estimate whether changed boundary looks smooth enough."""
    p = _to_gray_arr(person_image)
    r = _to_gray_arr(result_image)
    h = min(p.shape[0], r.shape[0])
    w = min(p.shape[1], r.shape[1])
    if h <= 2 or w <= 2:
        return 0.0

    p = p[:h, :w]
    r = r[:h, :w]
    delta = np.abs(r - p)
    change_mask = delta > 18.0
    if not np.any(change_mask):
        return 0.35

    gy, gx = np.gradient(r)
    grad = np.sqrt(gx * gx + gy * gy)
    edge_energy = float(grad[change_mask].mean())
    # higher edge energy often means harsh artifacts
    return _clamp01(1.0 - (edge_energy / 90.0))


def evaluate_qc(
    person_image: Image.Image,
    result_image: Image.Image,
    threshold: float = 0.6,
) -> QCResult:
    threshold = _clamp01(threshold)
    scores = {
        "identity_preserve_score": _identity_preserve_score(person_image, result_image),
        "boundary_artifact_score": _boundary_artifact_score(person_image, result_image),
        "occlusion_validity_score": occlusion_validity_score(person_image, result_image),
    }
    aggregate = float(np.mean(list(scores.values())))
    scores["qc_aggregate_score"] = _clamp01(aggregate)

    passed = scores["qc_aggregate_score"] >= threshold
    if passed:
        return QCResult(
            passed=True,
            threshold=threshold,
            scores=scores,
            message="输出通过方案A质量评估",
            action_hint="",
        )

    return QCResult(
        passed=False,
        threshold=threshold,
        scores=scores,
        message="输出未通过方案A质量评估，请更换更清晰的人像或商品图后重试。",
        action_hint="请上传正面全身照与清晰无模特商品图，避免遮挡和过曝。",
    )
