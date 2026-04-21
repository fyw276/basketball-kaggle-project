"""Occlusion and blend quality helpers for Try-on v2 pipeline A."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _gray(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32)


def build_change_mask(
    person_image: Image.Image,
    result_image: Image.Image,
    delta_threshold: float = 18.0,
) -> np.ndarray:
    """Binary mask of regions changed by try-on output (0/1 float array)."""
    p = _gray(person_image)
    r = _gray(result_image)
    h = min(p.shape[0], r.shape[0])
    w = min(p.shape[1], r.shape[1])
    if h <= 0 or w <= 0:
        return np.zeros((1, 1), dtype=np.float32)

    delta = np.abs(r[:h, :w] - p[:h, :w])
    return (delta >= float(delta_threshold)).astype(np.float32)


def occlusion_validity_score(
    person_image: Image.Image,
    result_image: Image.Image,
) -> float:
    """Heuristic occlusion validity using changed area ratio + edge continuity."""
    p = _gray(person_image)
    r = _gray(result_image)
    h = min(p.shape[0], r.shape[0])
    w = min(p.shape[1], r.shape[1])
    if h <= 2 or w <= 2:
        return 0.0

    p = p[:h, :w]
    r = r[:h, :w]

    y0 = int(h * 0.28)
    y1 = int(h * 0.9)
    x0 = int(w * 0.15)
    x1 = int(w * 0.85)
    roi_p = p[y0:y1, x0:x1]
    roi_r = r[y0:y1, x0:x1]
    if roi_p.size == 0 or roi_r.size == 0:
        return 0.0

    change_mask = build_change_mask(
        Image.fromarray(roi_p.astype(np.uint8), mode="L"),
        Image.fromarray(roi_r.astype(np.uint8), mode="L"),
    )

    change_ratio = float(change_mask.mean())
    # Penalize no-change and over-change; both indicate poor occlusion/blend quality.
    if change_ratio < 0.01:
        area_score = 0.15
    elif change_ratio > 0.65:
        area_score = _clamp01(1.0 - (change_ratio - 0.65) / 0.35)
    else:
        area_score = 1.0

    gy_p, gx_p = np.gradient(roi_p)
    gy_r, gx_r = np.gradient(roi_r)
    grad_p = np.sqrt(gx_p * gx_p + gy_p * gy_p)
    grad_r = np.sqrt(gx_r * gx_r + gy_r * gy_r)

    boundary = np.logical_xor(change_mask > 0.5, np.roll(change_mask > 0.5, 1, axis=0))
    boundary |= np.logical_xor(change_mask > 0.5, np.roll(change_mask > 0.5, 1, axis=1))

    if np.any(boundary):
        edge_diff = np.abs(grad_r[boundary] - grad_p[boundary]).mean()
        edge_score = _clamp01(1.0 - edge_diff / 45.0)
    else:
        edge_score = 0.35

    dark_ratio = float((roi_r < 8.0).mean())
    bright_ratio = float((roi_r > 248.0).mean())
    clip_penalty = dark_ratio * 0.6 + bright_ratio * 0.4
    clip_score = _clamp01(1.0 - clip_penalty * 2.0)

    final = 0.45 * area_score + 0.35 * edge_score + 0.20 * clip_score
    return _clamp01(final)
