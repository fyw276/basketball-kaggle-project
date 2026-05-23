from __future__ import annotations

import cv2
import numpy as np


def expand_binary_mask_to_ratio(
    mask: np.ndarray,
    *,
    target_ratio: float,
    kernel_size: int = 5,
    max_iterations: int = 12,
    min_width_ratio: float | None = None,
    max_width_ratio: float | None = None,
    max_area_ratio: float | None = None,
    top_guard_y: int | None = None,
) -> np.ndarray:
    """Dilate a binary mask until it reaches a target area/width without crossing a top guard."""
    if mask.ndim != 2:
        raise ValueError("mask must be a 2D array")
    if mask.size == 0:
        return mask.astype(np.uint8)

    out = (mask > 127).astype(np.uint8) * 255
    h, w = out.shape
    if top_guard_y is not None:
        guard = max(0, min(h, int(top_guard_y)))
        out[:guard, :] = 0

    kernel_dim = max(1, int(kernel_size))
    kernel = np.ones((kernel_dim, kernel_dim), np.uint8)
    min_width = None
    if min_width_ratio is not None:
        min_width = int(max(1, min(w, round(w * float(min_width_ratio)))))
    max_width = None
    if max_width_ratio is not None:
        max_width = int(max(1, min(w, round(w * float(max_width_ratio)))))

    def _stats_ok(arr: np.ndarray) -> bool:
        area_ok = float((arr > 127).mean()) >= float(target_ratio)
        if min_width is None:
            return area_ok
        ys, xs = np.where(arr > 127)
        if xs.size == 0:
            return False
        width_ok = (int(xs.max()) - int(xs.min()) + 1) >= min_width
        return area_ok and width_ok

    for _ in range(max(0, int(max_iterations))):
        if _stats_ok(out):
            break
        out = cv2.dilate(out, kernel, iterations=1)
        if top_guard_y is not None:
            out[: max(0, min(h, int(top_guard_y))), :] = 0

    if max_width is not None:
        ys, xs = np.where(out > 127)
        if xs.size > 0 and (int(xs.max()) - int(xs.min()) + 1) > max_width:
            cx = int(round((int(xs.min()) + int(xs.max())) / 2))
            x0 = max(0, cx - max_width // 2)
            x1 = min(w, x0 + max_width)
            x0 = max(0, x1 - max_width)
            width_guard = np.zeros_like(out)
            width_guard[:, x0:x1] = 255
            out = cv2.bitwise_and(out, width_guard)

    if max_area_ratio is not None:
        max_area = float(max_area_ratio)
        shrink_kernel = np.ones((max(1, int(kernel_size)), max(1, int(kernel_size))), np.uint8)
        while float((out > 127).mean()) > max_area:
            eroded = cv2.erode(out, shrink_kernel, iterations=1)
            if not (eroded > 127).any():
                break
            out = eroded

    return (out > 127).astype(np.uint8) * 255
