"""MediaPipe Pose 关键点提取工具 — 供 warp_engine 和 bailian 流程共用。

主要接口:
- detect_pose_keypoints(person_image) -> dict | None
- make_clothing_mask(person_image, keypoints, category) -> Image.Image (L mode, 255=编辑区域)
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageDraw

# MediaPipe landmark 索引（PoseLandmark）
_MP_NOSE = 0
_MP_LEFT_SHOULDER = 11
_MP_RIGHT_SHOULDER = 12
_MP_LEFT_ELBOW = 13
_MP_RIGHT_ELBOW = 14
_MP_LEFT_WRIST = 15
_MP_RIGHT_WRIST = 16
_MP_LEFT_HIP = 23
_MP_RIGHT_HIP = 24
_MP_LEFT_KNEE = 25
_MP_RIGHT_KNEE = 26
_MP_LEFT_ANKLE = 27
_MP_RIGHT_ANKLE = 28

_KEY_INDICES: dict[str, int] = {
    "nose": _MP_NOSE,
    "left_shoulder": _MP_LEFT_SHOULDER,
    "right_shoulder": _MP_RIGHT_SHOULDER,
    "left_elbow": _MP_LEFT_ELBOW,
    "right_elbow": _MP_RIGHT_ELBOW,
    "left_wrist": _MP_LEFT_WRIST,
    "right_wrist": _MP_RIGHT_WRIST,
    "left_hip": _MP_LEFT_HIP,
    "right_hip": _MP_RIGHT_HIP,
    "left_knee": _MP_LEFT_KNEE,
    "right_knee": _MP_RIGHT_KNEE,
    "left_ankle": _MP_LEFT_ANKLE,
    "right_ankle": _MP_RIGHT_ANKLE,
}

# 最小可见度阈值（低于此值的关键点视为不可靠）
_MIN_VISIBILITY = 0.35


def detect_pose_keypoints(
    person_image: Image.Image,
    min_visibility: float = _MIN_VISIBILITY,
) -> dict[str, tuple[float, float]] | None:
    """用 MediaPipe Pose 提取人体关键点（归一化坐标 0-1）。

    Returns:
        dict {landmark_name: (x_norm, y_norm)} 或 None（检测失败 / 无足够可见点）。
        x_norm 和 y_norm 均为 [0, 1] 范围的归一化坐标。
    """
    try:
        import mediapipe as mp  # type: ignore[import-untyped]

        mp_pose = mp.solutions.pose
        arr = np.asarray(person_image.convert("RGB"), dtype=np.uint8)

        with mp_pose.Pose(
            static_image_mode=True,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.4,
        ) as pose:
            results = pose.process(arr)

        if not results.pose_landmarks:
            return None

        landmarks = results.pose_landmarks.landmark
        kpts: dict[str, tuple[float, float]] = {}
        for name, idx in _KEY_INDICES.items():
            lm = landmarks[idx]
            vis = getattr(lm, "visibility", 1.0)
            if vis >= min_visibility:
                # 归一化坐标 clamp 到 [0, 1]
                kpts[name] = (max(0.0, min(1.0, float(lm.x))), max(0.0, min(1.0, float(lm.y))))

        # 必须至少检测到肩膀或髋部才认为有效
        has_shoulders = "left_shoulder" in kpts or "right_shoulder" in kpts
        has_hips = "left_hip" in kpts or "right_hip" in kpts
        if not (has_shoulders or has_hips):
            return None

        return kpts
    except Exception:
        return None


def _avg_x(*pts: tuple[float, float] | None) -> float | None:
    """对若干 (x,y) 取 x 均值，忽略 None。"""
    valid = [p[0] for p in pts if p is not None]
    return sum(valid) / len(valid) if valid else None


def _avg_y(*pts: tuple[float, float] | None) -> float | None:
    """对若干 (x,y) 取 y 均值，忽略 None。"""
    valid = [p[1] for p in pts if p is not None]
    return sum(valid) / len(valid) if valid else None


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def make_clothing_mask(
    person_image: Image.Image,
    keypoints: dict[str, tuple[float, float]] | None,
    category: str,
) -> Image.Image:
    """根据关键点生成衣服区域 mask（白色=需编辑，黑色=保留不动）。

    Args:
        person_image: 人物图（PIL RGB）。
        keypoints: detect_pose_keypoints 的返回值，可为 None。
        category: "top" | "bottom" | "skirt" | "outfit"，其余视为 "top"。

    Returns:
        与 person_image 同尺寸的灰度 Image（mode="L"）。
        255 = 需要编辑（衣服区域），0 = 保留不变。
    """
    pw, ph = person_image.size
    cat = (category or "top").strip().lower()
    mask = Image.new("L", (pw, ph), color=0)

    if keypoints:
        top_box = _top_region(keypoints, pw, ph) if cat in {"top", "outfit"} else None
        bottom_box = (
            _bottom_region(keypoints, pw, ph) if cat in {"bottom", "skirt", "outfit"} else None
        )
    else:
        top_box = _top_fallback(pw, ph) if cat in {"top", "outfit"} else None
        bottom_box = _bottom_fallback(pw, ph) if cat in {"bottom", "skirt", "outfit"} else None

    draw = ImageDraw.Draw(mask)
    if top_box:
        draw.rectangle(top_box, fill=255)
    if bottom_box:
        draw.rectangle(bottom_box, fill=255)

    return mask


# ─── 上装区域 ───────────────────────────────────────────────────────────────


def _top_region(
    kpts: dict[str, tuple[float, float]], pw: int, ph: int
) -> tuple[int, int, int, int] | None:
    """从肩膀到腰部（髋部）的躯干矩形框。"""
    ls = kpts.get("left_shoulder")
    rs = kpts.get("right_shoulder")
    lh = kpts.get("left_hip")
    rh = kpts.get("right_hip")
    le = kpts.get("left_elbow")
    re = kpts.get("right_elbow")

    shoulder_y = _avg_y(ls, rs)
    hip_y = _avg_y(lh, rh)
    if shoulder_y is None or hip_y is None:
        return _top_fallback(pw, ph)

    # 水平范围：以肘部延伸，确保袖子覆盖
    x_pts = [p[0] for p in [ls, rs, le, re] if p is not None]
    x0_n = max(0.0, min(x_pts) - 0.04)
    x1_n = min(1.0, max(x_pts) + 0.04)

    # 垂直范围：肩膀往上留空防止遮脸，往下延伸到髋部
    y0_n = max(0.0, shoulder_y - 0.06)
    y1_n = min(1.0, hip_y + 0.04)

    if y1_n <= y0_n:
        return _top_fallback(pw, ph)

    x0 = _clamp_int(int(x0_n * pw), 0, pw - 2)
    y0 = _clamp_int(int(y0_n * ph), 0, ph - 2)
    x1 = _clamp_int(int(x1_n * pw), x0 + 2, pw)
    y1 = _clamp_int(int(y1_n * ph), y0 + 2, ph)
    return (x0, y0, x1, y1)


def _top_fallback(pw: int, ph: int) -> tuple[int, int, int, int]:
    """无关键点时的上装区域 fallback（比例估算）。"""
    return (
        _clamp_int(int(pw * 0.12), 0, pw - 2),
        _clamp_int(int(ph * 0.12), 0, ph - 2),
        _clamp_int(int(pw * 0.88), 2, pw),
        _clamp_int(int(ph * 0.60), 2, ph),
    )


# ─── 下装区域 ───────────────────────────────────────────────────────────────


def _bottom_region(
    kpts: dict[str, tuple[float, float]], pw: int, ph: int
) -> tuple[int, int, int, int] | None:
    """从腰部（髋部）到踝部的下装矩形框。"""
    lh = kpts.get("left_hip")
    rh = kpts.get("right_hip")
    la = kpts.get("left_ankle")
    ra = kpts.get("right_ankle")
    lk = kpts.get("left_knee")
    rk = kpts.get("right_knee")

    hip_y = _avg_y(lh, rh)
    ankle_y = _avg_y(la, ra) or _avg_y(lk, rk)
    if hip_y is None:
        return _bottom_fallback(pw, ph)

    x_pts = [p[0] for p in [lh, rh, la, ra] if p is not None]
    x0_n = max(0.0, (min(x_pts) - 0.06) if x_pts else 0.16)
    x1_n = min(1.0, (max(x_pts) + 0.06) if x_pts else 0.84)

    y0_n = max(0.0, hip_y - 0.04)
    y1_n = min(1.0, (ankle_y + 0.03) if ankle_y is not None else hip_y + 0.55)

    if y1_n <= y0_n:
        return _bottom_fallback(pw, ph)

    x0 = _clamp_int(int(x0_n * pw), 0, pw - 2)
    y0 = _clamp_int(int(y0_n * ph), 0, ph - 2)
    x1 = _clamp_int(int(x1_n * pw), x0 + 2, pw)
    y1 = _clamp_int(int(y1_n * ph), y0 + 2, ph)
    return (x0, y0, x1, y1)


def _bottom_fallback(pw: int, ph: int) -> tuple[int, int, int, int]:
    """无关键点时的下装区域 fallback（比例估算）。"""
    return (
        _clamp_int(int(pw * 0.16), 0, pw - 2),
        _clamp_int(int(ph * 0.44), 0, ph - 2),
        _clamp_int(int(pw * 0.84), 2, pw),
        _clamp_int(int(ph * 0.97), 2, ph),
    )


def get_body_bounds_from_keypoints(
    keypoints: dict[str, tuple[float, float]],
    pw: int,
    ph: int,
    category: str,
) -> dict[str, Any]:
    """从关键点提取用于 warp_engine 的身体边界参数（像素坐标）。

    Returns dict with keys:
        x0, x1          — 水平范围（像素）
        neck_y / waist_y — 上装 y 坐标
        waist_y / ankle_y — 下装 y 坐标
        shoulder_width  — 肩宽像素
        hip_width       — 腰宽像素
        valid           — bool，是否有足够的关键点
    """
    cat = (category or "top").strip().lower()
    result: dict[str, Any] = {"valid": False}

    ls = keypoints.get("left_shoulder")
    rs = keypoints.get("right_shoulder")
    lh = keypoints.get("left_hip")
    rh = keypoints.get("right_hip")
    la = keypoints.get("left_ankle")
    ra = keypoints.get("right_ankle")
    le = keypoints.get("left_elbow")
    re = keypoints.get("right_elbow")
    nose = keypoints.get("nose")

    # 肩宽 / 腰宽
    if ls and rs:
        shoulder_width = abs(rs[0] - ls[0]) * pw
        shoulder_cx = (ls[0] + rs[0]) / 2.0
    elif ls:
        shoulder_width = pw * 0.36
        shoulder_cx = ls[0]
    elif rs:
        shoulder_width = pw * 0.36
        shoulder_cx = rs[0]
    else:
        shoulder_width = pw * 0.36
        shoulder_cx = 0.5

    if lh and rh:
        hip_width = abs(rh[0] - lh[0]) * pw
        hip_cx = (lh[0] + rh[0]) / 2.0
    else:
        hip_width = shoulder_width * 0.90
        hip_cx = shoulder_cx

    # 水平范围：取肩膀/肘部中最宽的
    x_candidates = [p[0] for p in [ls, rs, le, re, lh, rh] if p is not None]
    if x_candidates:
        x0_n = max(0.0, min(x_candidates) - 0.04)
        x1_n = min(1.0, max(x_candidates) + 0.04)
    else:
        x0_n, x1_n = 0.16, 0.84

    x0 = _clamp_int(int(x0_n * pw), 0, pw - 2)
    x1 = _clamp_int(int(x1_n * pw), x0 + 2, pw)

    result.update(
        {
            "x0": x0,
            "x1": x1,
            "shoulder_width": shoulder_width,
            "hip_width": hip_width,
            "shoulder_cx": shoulder_cx,
            "hip_cx": hip_cx,
        }
    )

    if cat in {"top", "outfit"}:
        shoulder_y = _avg_y(ls, rs)
        hip_y = _avg_y(lh, rh)
        if shoulder_y is not None:
            # neck_y：脖子在鼻子到肩膀之间
            if nose:
                neck_y = _clamp_int(
                    int((nose[1] * 0.35 + shoulder_y * 0.65) * ph), int(ph * 0.06), int(ph * 0.38)
                )
            else:
                neck_y = _clamp_int(int((shoulder_y - 0.06) * ph), int(ph * 0.06), int(ph * 0.32))
            waist_y = _clamp_int(
                int((hip_y or (shoulder_y + 0.30)) * ph), int(ph * 0.38), int(ph * 0.82)
            )
            result.update({"neck_y": neck_y, "waist_y": waist_y, "valid": True})

    if cat in {"bottom", "skirt", "outfit"}:
        hip_y = _avg_y(lh, rh)
        ankle_y = _avg_y(la, ra)
        if hip_y is not None:
            waist_y = _clamp_int(int((hip_y - 0.04) * ph), int(ph * 0.28), int(ph * 0.58))
            ankle_y_px = _clamp_int(
                int((ankle_y or (hip_y + 0.52)) * ph), int(ph * 0.70), int(ph * 0.98)
            )
            result.update({"waist_y": waist_y, "ankle_y": ankle_y_px, "valid": True})

    return result
