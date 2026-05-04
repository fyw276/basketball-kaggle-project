"""MediaPipe Pose 关键点提取工具 — 供 warp_engine 和 bailian 流程共用。

主要接口:
- detect_pose_keypoints(person_image) -> dict | None
- detect_face_zone(person_image) -> tuple[int,int,int,int] | None  (x0,y0,x1,y1)
- make_clothing_mask(person_image, keypoints, category) -> Image.Image (L mode, 255=编辑区域)
  (内置：人脸椭圆保护 + Gaussian feathering 边缘羽化)

改进（v2）：
|- 删除矩形 mask，改用 polygon fillPoly 生成贴合人体轮廓的 mask
|- 使用 mediapipe 关键点（肩膀+臀部）构建 polygon 顶点
|- GaussianBlur 平滑 mask 边缘

MediaPipe 支持:
- MediaPipe Tasks API (0.10+, 推荐)
- Legacy mp.solutions.pose (降级兼容)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2  # type: ignore[import-untyped]
import numpy as np
from PIL import Image

from app.services.body_mask import create_lower_body_polygon_mask, create_upper_body_polygon_mask

# MediaPipe landmark 索引（PoseLandmark）
_MP_NOSE = 0
_MP_LEFT_EAR = 7
_MP_RIGHT_EAR = 8
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
    "left_ear": _MP_LEFT_EAR,
    "right_ear": _MP_RIGHT_EAR,
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

# ─── MediaPipe Tasks model path ─────────────────────────────────────────────

_MP_POSE_MODEL_PATH: str | None = None


def _get_pose_landmarker_model_path() -> str | None:
    """Find PoseLandmarker .task model file in common locations."""
    global _MP_POSE_MODEL_PATH
    if _MP_POSE_MODEL_PATH:
        return _MP_POSE_MODEL_PATH
    candidates = [
        Path(__file__).parent.parent.parent / "models" / "pose_landmarker_heavy.task",
        Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task",
        Path.home() / "models" / "pose_landmarker_heavy.task",
    ]
    for p in candidates:
        if p.exists():
            _MP_POSE_MODEL_PATH = str(p.resolve())
            return _MP_POSE_MODEL_PATH
    return None


# ─── Pose detection ────────────────────────────────────────────────────────────


def detect_pose_keypoints(
    person_image: Image.Image,
    min_visibility: float = _MIN_VISIBILITY,
) -> dict[str, tuple[float, float]] | None:
    """用 MediaPipe PoseLandmarker 提取人体关键点（归一化坐标 0-1）。

    Supports both legacy MediaPipe (mp.solutions.pose) and MediaPipe Tasks API
    (mp.tasks.python.vision.PoseLandmarker).

    Returns:
        dict {landmark_name: (x_norm, y_norm)} 或 None（检测失败 / 无足够可见点）。
        x_norm 和 y_norm 均为 [0, 1] 范围的归一化坐标。
    """
    import mediapipe as mp  # type: ignore[import-untyped]

    arr = np.asarray(person_image.convert("RGB"), dtype=np.uint8)

    # Try MediaPipe Tasks API first (MediaPipe 0.10+)
    try:
        import mediapipe.tasks
        from mediapipe import Image as MPImage
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

        model_path = _get_pose_landmarker_model_path()
        if model_path:
            options = PoseLandmarkerOptions(
                base_options=mediapipe.tasks.BaseOptions(model_asset_path=model_path),
                running_mode=RunningMode.IMAGE,
                output_segmentation_masks=False,
            )
            landmarker = PoseLandmarker.create_from_options(options)
            # MediaPipe 0.10.x Image has no create_from_array; use temp file
            import os as _os
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                tmp_path = f.name
            person_image.convert("RGB").save(tmp_path, format="JPEG", quality=95)
            mp_img = MPImage.create_from_file(tmp_path)
            result = landmarker.detect(mp_img)
            landmarker.close()
            _os.unlink(tmp_path)

            if not result.pose_landmarks:
                return None

            landmarks = result.pose_landmarks[0]
            kpts: dict[str, tuple[float, float]] = {}
            for name, idx in _KEY_INDICES.items():
                if idx < len(landmarks):
                    lm = landmarks[idx]
                    vis = getattr(lm, "visibility", 1.0)
                    if vis >= min_visibility:
                        kpts[name] = (
                            max(0.0, min(1.0, float(lm.x))),
                            max(0.0, min(1.0, float(lm.y))),
                        )

            has_shoulders = "left_shoulder" in kpts or "right_shoulder" in kpts
            has_hips = "left_hip" in kpts or "right_hip" in kpts
            if has_shoulders or has_hips:
                return kpts
    except Exception:
        pass

    # Fallback: legacy mp.solutions.pose
    try:
        mp_pose = mp.solutions.pose
        with mp_pose.Pose(
            static_image_mode=True,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.4,
        ) as pose:
            results = pose.process(arr)

        if not results.pose_landmarks:
            return None

        landmarks = results.pose_landmarks[0]
        kpts: dict[str, tuple[float, float]] = {}
        for name, idx in _KEY_INDICES.items():
            lm = landmarks[idx]
            vis = getattr(lm, "visibility", 1.0)
            if vis >= min_visibility:
                kpts[name] = (max(0.0, min(1.0, float(lm.x))), max(0.0, min(1.0, float(lm.y))))

        has_shoulders = "left_shoulder" in kpts or "right_shoulder" in kpts
        has_hips = "left_hip" in kpts or "right_hip" in kpts
        if not (has_shoulders or has_hips):
            return None

        return kpts
    except Exception:
        return None


def detect_face_zone(
    person_image: Image.Image,
) -> tuple[int, int, int, int] | None:
    """用 MediaPipe Face Detection 检测人脸区域（像素坐标）。

    Returns:
        (x0, y0, x1, y1) 人脸 bounding box（相对于 person_image 尺寸），
        或 None（未检测到人脸）。
    """
    try:
        import mediapipe as mp  # type: ignore[import-untyped]

        mp_face = mp.solutions.face_detection
        arr = np.asarray(person_image.convert("RGB"), dtype=np.uint8)
        h, w = arr.shape[:2]

        with mp_face.FaceDetection(
            model_selection=0,
            min_detection_confidence=0.5,
        ) as face_detector:
            results = face_detector.process(arr)

        if not results.detections:
            return None

        # 取置信度最高的人脸
        best = max(results.detections, key=lambda d: d.score[0])
        bb = best.location_data.relative_bounding_box
        x0 = max(0, int(bb.xmin * w))
        y0 = max(0, int(bb.ymin * h))
        x1 = min(w, int((bb.xmin + bb.width) * w))
        y1 = min(h, int((bb.ymin + bb.height) * h))

        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1, y1)
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


def _carve_face_ellipse(
    mask: np.ndarray,
    face_box: tuple[int, int, int, int],
    pw: int,
    ph: int,
) -> np.ndarray:
    """在 mask 上挖出人脸椭圆区域（设为 0），防止 diffusion 修改人脸。

    人脸椭圆 = 水平占 face_box 的 ±25%，垂直占 ±35%，中心在 box 中心偏上。
    这样即使 mask 矩形框靠近人脸，人脸椭圆也能确保面部区域不被编辑。
    """
    x0, y0, x1, y1 = face_box
    cx = (x0 + x1) // 2
    # 椭圆中心略微上移（约在脸的中间偏上位置）
    cy = int(y0 * 0.3 + y1 * 0.7)

    ew = (x1 - x0) // 2 + max(1, int(pw * 0.04))  # 水平半径 + padding
    eh = int((y1 - y0) // 2 * 1.1) + max(1, int(ph * 0.03))  # 垂直半径 + padding

    rows, cols = mask.shape
    y_grid, x_grid = np.ogrid[:rows, :cols]
    ellipse_mask = (
        ((x_grid - cx) ** 2) // max(1, ew**2) + ((y_grid - cy) ** 2) // max(1, eh**2)
    ) <= 1

    mask = mask.copy()
    mask[ellipse_mask] = 0
    return mask


def make_clothing_mask(
    person_image: Image.Image,
    keypoints: dict[str, tuple[float, float]] | None,
    category: str,
    feather_radius: int = 5,
) -> Image.Image:
    """根据关键点生成衣服区域 mask（白色=需编辑，黑色=保留不动）。

    改进版（v2）：
    1. 删除矩形 mask，改用 polygon fillPoly 生成贴合人体轮廓的 mask
    2. 使用 mediapipe 关键点（肩膀+臀部）构建 polygon 顶点
    3. 对 mask 边缘做 Gaussian feathering 减少边界伪影
    4. 若检测到人脸，额外挖出人脸椭圆保护区域（防止 diffusion 修改人脸）

    Args:
        person_image: 人物图（PIL RGB）。
        keypoints: detect_pose_keypoints 的返回值，可为 None。
        category: "top" | "bottom" | "skirt" | "outfit"，其余视为 "top"。
        feather_radius: mask 边缘 Gaussian feathering 半径（像素），0=禁用。

    Returns:
        与 person_image 同尺寸的灰度 Image（mode="L"）。
        255 = 需要编辑（衣服区域），0 = 保留不变。
    """
    pw, ph = person_image.size
    cat = (category or "top").strip().lower()

    mask_np: np.ndarray

    if keypoints:
        if cat in {"top", "outfit"}:
            mask_np = create_upper_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
        elif cat in {"bottom", "skirt"}:
            mask_np = create_lower_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
        else:
            mask_np = create_upper_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
    else:
        mask_np = np.zeros((ph, pw), dtype=np.uint8)
        if cat in {"top", "outfit"}:
            from app.services.body_mask import _upper_body_fallback

            mask_np = _upper_body_fallback(pw, ph, feather_radius=0)
        elif cat in {"bottom", "skirt"}:
            from app.services.body_mask import _lower_body_fallback

            mask_np = _lower_body_fallback(pw, ph, feather_radius=0)

    # 人脸保护：检测人脸并挖出椭圆
    face_box = detect_face_zone(person_image)
    if face_box is not None:
        mask_np = _carve_face_ellipse(mask_np, face_box, pw, ph)

    # 边缘羽化（Gaussian blur 过渡）
    if feather_radius > 0:
        mask_np = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask_np = np.clip(mask_np, 0, 255).astype(np.uint8)

    return Image.fromarray(mask_np, mode="L")


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
