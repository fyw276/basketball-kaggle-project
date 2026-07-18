"""人体 Polygon Mask 生成模块 — 基于 MediaPipe 关键点（肩膀 + 臀部）。

核心设计：
1. 使用 mediapipe 关键点（肩膀 + 臀部）构建 polygon 顶点
2. 使用 cv2.fillPoly 生成贴合人体轮廓的 mask
3. 对 mask 进行 GaussianBlur 平滑边缘

用法：
    from app.services.body_mask import (
        create_upper_body_polygon_mask,
        create_lower_body_polygon_mask,
        create_full_body_polygon_mask,
    )
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

# ─── Polygon mask 构建 ─────────────────────────────────────────────────────────


def _points_to_pixel(
    pts: list[tuple[float, float]],
    pw: int,
    ph: int,
) -> list[tuple[int, int]]:
    """将归一化关键点 (x_norm, y_norm) 转换为像素坐标。"""
    return [(max(0, min(pw - 1, int(p[0] * pw))), max(0, min(ph - 1, int(p[1] * ph)))) for p in pts]


def _blunt_polygon(
    pts: list[tuple[int, int]],
    margin: float = 0.02,
) -> list[tuple[int, int]]:
    """对 polygon 顶点做微小模糊，防止 sharp corner 造成 mask 边缘锯齿。

    Args:
        pts: 像素坐标的关键点列表
        margin: 每对相邻点之间的插值步数（越多越平滑，默认3步）
    """
    if len(pts) < 3:
        return pts
    result = []
    n = len(pts)
    for i in range(n):
        p0 = pts[i]
        p1 = pts[(i + 1) % n]
        steps = max(2, int(margin * 100))
        for t in range(steps):
            alpha = t / steps
            result.append(
                (
                    int(p0[0] * (1 - alpha) + p1[0] * alpha),
                    int(p0[1] * (1 - alpha) + p1[1] * alpha),
                )
            )
    return result


def create_upper_body_polygon_mask(
    keypoints: dict[str, tuple[float, float]],
    pw: int,
    ph: int,
    feather_radius: int = 0,
) -> np.ndarray:
    """使用肩膀+臀部关键点生成上装 polygon mask（cv2.fillPoly）。

    Polygon 顶点顺序（左→右→下→左）：
        1. 左肩
        2. 右肩
        3. 右臀
        4. 左臀

    高帽领/宽松款额外延伸：加入手腕关键点以覆盖袖子区域。

    Args:
        keypoints: detect_pose_keypoints() 返回的归一化关键点字典
        pw, ph: 图像宽高（像素）
        feather_radius: 边缘羽化半径（0=禁用）

    Returns:
        (ph, pw) uint8 数组，255=上装区域，0=保留区域
    """
    ls = keypoints.get("left_shoulder")
    rs = keypoints.get("right_shoulder")
    lh = keypoints.get("left_hip")
    rh = keypoints.get("right_hip")
    le = keypoints.get("left_elbow")
    re = keypoints.get("right_elbow")

    pts: list[tuple[float, float]] = []

    # 基础四边形：肩膀-臀部（左肩→右肩→右臀→左臀）
    if ls:
        pts.append(ls)
    if rs:
        pts.append(rs)
    if rh:
        pts.append(rh)
    if lh:
        pts.append(lh)

    # 袖子延伸：如果有肘部关键点，额外包含袖子区域
    # 在左肩-左肘 和 右肩-右肘 方向各取一个中间点作为袖口
    sleeve_pts: list[tuple[float, float]] = []
    if le and ls:
        sleeve_pts.append(
            (
                le[0] * 0.6 + ls[0] * 0.4,
                le[1] * 0.6 + ls[1] * 0.4,
            )
        )
    if re and rs:
        sleeve_pts.append(
            (
                re[0] * 0.6 + rs[0] * 0.4,
                re[1] * 0.6 + rs[1] * 0.4,
            )
        )

    if sleeve_pts:
        # 将袖子点插入到对应肩膀后面
        final_pts: list[tuple[float, float]] = []
        if ls:
            final_pts.append(ls)
        if sleeve_pts[0:1] and ls:
            final_pts.append(sleeve_pts[0])
        if rs:
            final_pts.append(rs)
        if len(sleeve_pts) > 1 and rs:
            final_pts.append(sleeve_pts[1])
        if rh:
            final_pts.append(rh)
        if lh:
            final_pts.append(lh)
        pts = final_pts

    if len(pts) < 3:
        return _upper_body_fallback(pw, ph, feather_radius)

    pixel_pts = _points_to_pixel(pts, pw, ph)

    mask = np.zeros((ph, pw), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(pixel_pts, dtype=np.int32)], 255)

    if feather_radius > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    return mask


def create_lower_body_polygon_mask(
    keypoints: dict[str, tuple[float, float]],
    pw: int,
    ph: int,
    feather_radius: int = 0,
    outer_pad_ratio: float = 0.90,
) -> np.ndarray:
    """使用臀部+膝+踝关键点生成下装 polygon mask（cv2.fillPoly）。

    Polygon 顶点顺序（图像空间顺时针，含左右腿外侧 padding）：
        图像左髋 -> 图像右髋 -> 右膝外侧 -> 右踝外侧 -> 左踝外侧 -> 左膝外侧

    重要：MediaPipe 的 left/right 是人物自身左右。正面照时人物左髋在图像右侧，
    因此外侧 padding 必须按图像 x 相对髋中心向外扩展，不能按语义 left=-1/right=+1。

    Args:
        keypoints: detect_pose_keypoints() 返回的归一化关键点字典
        pw, ph: 图像宽高（像素）
        feather_radius: 边缘羽化半径（0=禁用）
        outer_pad_ratio: 左右腿外侧水平扩张比例（相对髋宽）

    Returns:
        (ph, pw) uint8 数组，255=下装区域，0=保留区域
    """
    lh = keypoints.get("left_hip")
    rh = keypoints.get("right_hip")
    la = keypoints.get("left_ankle")
    ra = keypoints.get("right_ankle")
    lk = keypoints.get("left_knee")
    rk = keypoints.get("right_knee")
    ls = keypoints.get("left_shoulder")
    rs = keypoints.get("right_shoulder")

    if not (lh and rh):
        return _lower_body_fallback(pw, ph, feather_radius)

    # Reorder into image-space left/right so fillPoly walks without self-intersection.
    if lh[0] <= rh[0]:
        img_l_hip, img_r_hip = lh, rh
        img_l_knee, img_r_knee = lk, rk
        img_l_ankle, img_r_ankle = la, ra
    else:
        img_l_hip, img_r_hip = rh, lh
        img_l_knee, img_r_knee = rk, lk
        img_l_ankle, img_r_ankle = ra, la

    hip_width = abs(img_r_hip[0] - img_l_hip[0])
    shoulder_width = abs(rs[0] - ls[0]) if ls and rs else hip_width
    pad = max(
        0.055,
        float(outer_pad_ratio) * max(hip_width, 0.08),
        0.50 * max(shoulder_width, hip_width),
    )
    ankle_pad = max(pad, pad * 1.40)
    waist_lift = 0.03

    def _outer_left(pt: tuple[float, float], p_pad: float = pad) -> tuple[float, float]:
        return (float(pt[0]) - p_pad, float(pt[1]))

    def _outer_right(pt: tuple[float, float], p_pad: float = pad) -> tuple[float, float]:
        return (float(pt[0]) + p_pad, float(pt[1]))

    pts: list[tuple[float, float]] = []
    pts.append(_outer_left((img_l_hip[0], max(0.0, img_l_hip[1] - waist_lift))))
    pts.append(_outer_right((img_r_hip[0], max(0.0, img_r_hip[1] - waist_lift))))

    if img_r_knee:
        pts.append(_outer_right(img_r_knee))
    elif img_r_ankle:
        mid = ((img_r_hip[0] + img_r_ankle[0]) / 2.0, (img_r_hip[1] + img_r_ankle[1]) / 2.0)
        pts.append(_outer_right(mid))

    if img_r_ankle:
        ankle = (img_r_ankle[0], max(0.0, img_r_ankle[1] - 0.01))
        pts.append(_outer_right(ankle, ankle_pad))
    elif img_r_knee:
        pts.append(_outer_right((img_r_knee[0], min(0.98, img_r_knee[1] + 0.18)), ankle_pad))

    if img_l_ankle:
        ankle = (img_l_ankle[0], max(0.0, img_l_ankle[1] - 0.01))
        pts.append(_outer_left(ankle, ankle_pad))
    elif img_l_knee:
        pts.append(_outer_left((img_l_knee[0], min(0.98, img_l_knee[1] + 0.18)), ankle_pad))

    if img_l_knee:
        pts.append(_outer_left(img_l_knee))
    elif img_l_ankle:
        mid = ((img_l_hip[0] + img_l_ankle[0]) / 2.0, (img_l_hip[1] + img_l_ankle[1]) / 2.0)
        pts.append(_outer_left(mid))

    # Need at least a trapezoid (hips + two lower points).
    if len(pts) < 4:
        mid_y = (img_l_hip[1] + img_r_hip[1]) / 2.0 + 0.35
        pts = [
            _outer_left(img_l_hip),
            _outer_right(img_r_hip),
            _outer_right((img_r_hip[0], mid_y), ankle_pad),
            _outer_left((img_l_hip[0], mid_y), ankle_pad),
        ]

    if len(pts) < 3:
        return _lower_body_fallback(pw, ph, feather_radius)

    pixel_pts = _points_to_pixel(pts, pw, ph)

    mask = np.zeros((ph, pw), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(pixel_pts, dtype=np.int32)], 255)

    if feather_radius > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    return mask


def create_full_body_polygon_mask(
    keypoints: dict[str, tuple[float, float]],
    pw: int,
    ph: int,
    feather_radius: int = 0,
) -> np.ndarray:
    """使用全身关键点生成完整 body polygon mask（cv2.fillPoly）。

    Polygon 由以下关键点构成（左→右 顺时针）：
        左肩 → 右肩 → 右臀 → 右踝 → 左踝 → 左臀

    优先使用完整的关键点序列，如果某些点缺失则逐步降级。

    Args:
        keypoints: detect_pose_keypoints() 返回的归一化关键点字典
        pw, ph: 图像宽高（像素）
        feather_radius: 边缘羽化半径（0=禁用）

    Returns:
        (ph, pw) uint8 数组，255=人体区域，0=背景
    """
    ls = keypoints.get("left_shoulder")
    rs = keypoints.get("right_shoulder")
    lh = keypoints.get("left_hip")
    rh = keypoints.get("right_hip")
    la = keypoints.get("left_ankle")
    ra = keypoints.get("right_ankle")
    le = keypoints.get("left_elbow")
    re = keypoints.get("right_elbow")

    pts: list[tuple[float, float]] = []

    # 左半侧（从左肩开始，顺时针）
    if ls:
        pts.append(ls)
    # 左袖口延伸
    if le and ls:
        pts.append((le[0] * 0.7 + ls[0] * 0.3, le[1] * 0.7 + ls[1] * 0.3))

    # 右半侧
    if rs:
        pts.append(rs)
    if re and rs:
        pts.append((re[0] * 0.7 + rs[0] * 0.3, re[1] * 0.7 + rs[1] * 0.3))
    if rh:
        pts.append(rh)
    if ra:
        pts.append(ra)
    if la:
        pts.append(la)
    if lh:
        pts.append(lh)

    if len(pts) < 3:
        return _full_body_fallback(pw, ph, feather_radius)

    pixel_pts = _points_to_pixel(pts, pw, ph)

    mask = np.zeros((ph, pw), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(pixel_pts, dtype=np.int32)], 255)

    if feather_radius > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    return mask


# ─── Fallback masks（无关键点时的比例估算）─────────────────────────────────────


def _upper_body_fallback(pw: int, ph: int, feather_radius: int = 0) -> np.ndarray:
    """无关键点时的上装 polygon fallback（使用身体比例估算轮廓）。"""
    # 用梯形近似上装轮廓：肩膀宽，腰部窄
    shoulder_w = 0.36  # 肩膀占图像宽度的比例
    hip_w = 0.28  # 臀部宽度比例
    top_y = 0.12  # 肩膀高度
    bottom_y = 0.58  # 臀部高度

    shoulder_cx = 0.5
    cx_px = int(pw * shoulder_cx)
    top_px = int(ph * top_y)
    bottom_px = int(ph * bottom_y)
    shoulder_hw_px = int(pw * shoulder_w / 2)
    hip_hw_px = int(pw * hip_w / 2)

    pts = [
        (cx_px - shoulder_hw_px, top_px),
        (cx_px + shoulder_hw_px, top_px),
        (cx_px + hip_hw_px, bottom_px),
        (cx_px - hip_hw_px, bottom_px),
    ]

    mask = np.zeros((ph, pw), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(pts, dtype=np.int32)], 255)

    if feather_radius > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    return mask


def _lower_body_fallback(pw: int, ph: int, feather_radius: int = 0) -> np.ndarray:
    """无关键点时的下装 polygon fallback（使用身体比例估算轮廓）。"""
    hip_w = 0.28
    ankle_w = 0.20
    top_y = 0.44
    bottom_y = 0.97

    cx_px = int(pw * 0.5)
    top_px = int(ph * top_y)
    bottom_px = int(ph * bottom_y)
    hip_hw_px = int(pw * hip_w / 2)
    ankle_hw_px = int(pw * ankle_w / 2)

    pts = [
        (cx_px - hip_hw_px, top_px),
        (cx_px + hip_hw_px, top_px),
        (cx_px + ankle_hw_px, bottom_px),
        (cx_px - ankle_hw_px, bottom_px),
    ]

    mask = np.zeros((ph, pw), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(pts, dtype=np.int32)], 255)

    if feather_radius > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    return mask


def _full_body_fallback(pw: int, ph: int, feather_radius: int = 0) -> np.ndarray:
    """无关键点时的全身 polygon fallback（使用身体比例估算轮廓）。"""
    shoulder_w = 0.36
    ankle_w = 0.20
    top_y = 0.12
    bottom_y = 0.97

    cx_px = int(pw * 0.5)
    top_px = int(ph * top_y)
    bottom_px = int(ph * bottom_y)
    shoulder_hw_px = int(pw * shoulder_w / 2)
    ankle_hw_px = int(pw * ankle_w / 2)

    # 左肩→右肩→右踝→左踝（简化6边形）
    pts = [
        (cx_px - shoulder_hw_px, top_px),
        (cx_px + shoulder_hw_px, top_px),
        (cx_px + ankle_hw_px, bottom_px),
        (cx_px - ankle_hw_px, bottom_px),
    ]

    mask = np.zeros((ph, pw), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(pts, dtype=np.int32)], 255)

    if feather_radius > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask = np.clip(mask, 0, 255).astype(np.uint8)

    return mask


# ─── 对外高层接口 ─────────────────────────────────────────────────────────────


def create_body_mask(
    keypoints: dict[str, tuple[float, float]] | None,
    pw: int,
    ph: int,
    category: str,
    feather_radius: int = 0,
) -> Image.Image:
    """根据衣物类别和关键点生成 polygon body mask。

    Args:
        keypoints: detect_pose_keypoints() 返回的归一化关键点字典，可为 None
        pw, ph: 图像宽高（像素）
        category: "top" | "bottom" | "skirt" | "outfit"（等同于 full body）
        feather_radius: 边缘羽化半径（0=禁用）

    Returns:
        PIL Image (mode="L")，255=衣物区域，0=保留区域
    """
    cat = (category or "top").strip().lower()

    if keypoints:
        if cat in {"top", "outfit"}:
            mask_np = create_upper_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
        elif cat in {"bottom", "skirt"}:
            mask_np = create_lower_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
        else:
            mask_np = create_upper_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
    else:
        if cat in {"top", "outfit"}:
            mask_np = _upper_body_fallback(pw, ph, feather_radius=0)
        elif cat in {"bottom", "skirt"}:
            mask_np = _lower_body_fallback(pw, ph, feather_radius=0)
        else:
            mask_np = _upper_body_fallback(pw, ph, feather_radius=0)

    # 应用羽化
    if feather_radius > 0:
        mask_np = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask_np = np.clip(mask_np, 0, 255).astype(np.uint8)

    return Image.fromarray(mask_np, mode="L")
