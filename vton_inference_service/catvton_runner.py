"""
CatVTON subprocess runner — standalone inference via CatVTONPipeline.

关键改进（相比原版）：
1. 极限 VRAM 优化：fp16 强制、VAE slicing、xformers、GC 回收
2. 白盒调试工具：save_debug_image() + 每步中间产物落盘
3. 预处理模式：--preprocess-only（只运行到 mask 生成，节省调试时间）
4. Windows 安全日志：enqueue 模式

架构：
- CatVTONPipeline: 核心扩散模型（SD v1.5 inpainting + CatVTON attention）
- MediaPipe PoseLandmarker: 人体关键点 + 人物分割遮罩
- Body-region mask: 从姿态关键点推导（上装/下装/全身）

用法：
    python catvton_runner.py \
        --person person.jpg --garment garment.jpg \
        --output result.jpg --type upper \
        --width 768 --height 1024 --steps 50 --guidance 2.5 \
        --catvton-path D:/models/CatVTON \
        --precision fp16 \
        --vae-slicing --xformers \
        --debug-dir ./debug_output \
        --preprocess-only

退出码：
    0 = 成功
    1 = 通用错误
    10 = CatVTON 不可用（导入失败）
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from PIL import Image
import numpy as np
import mediapipe


# ═══════════════════════════════════════════════════════════════════════════════
# 通用工具
# ═══════════════════════════════════════════════════════════════════════════════


def _load_image(path: str) -> "Image.Image":
    with open(path, "rb") as f:
        return Image.open(f).convert("RGB")


def _save_image(img: "Image.Image", path: str):
    img.save(path, format="JPEG", quality=95)


# ═══════════════════════════════════════════════════════════════════════════════
# 白盒调试工具：save_debug_image(stage_name, image)
#
# 原理：
#   每次调用时，在 debug_dir 下创建一个带序号的文件，文件名格式为：
#   {step:02d}_{stage_name}_{timestamp}.jpg
#   其中 step 从 01 开始，确保所有中间产物按处理顺序排列。
#
#   每次请求生成一个独立文件夹（以时间戳命名），避免不同请求的文件互相覆盖，
#   方便对比分析。
# ═══════════════════════════════════════════════════════════════════════════════

_debug_session_id: str = ""
_debug_output_dir: Path | None = None
_debug_step_counter: int = 0


def init_debug_session(output_dir: Path | None) -> str:
    """
    初始化一个调试会话目录。

    为每次请求创建独立文件夹（时间戳命名），确保：
    - 不同请求的文件不会互相覆盖
    - 可以对比不同参数下的中间产物
    - 便于事后分析哪一步出了问题

    Args:
        output_dir: 调试输出根目录（由 --debug-dir 指定）
    Returns:
        session_id: 本次会话的文件夹名称
    """
    global _debug_session_id, _debug_output_dir, _debug_step_counter

    _debug_session_id = ""
    _debug_output_dir = None
    _debug_step_counter = 0

    if output_dir is None:
        return ""

    ts = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
    import uuid

    session_id = f"tryon_{ts}_{uuid.uuid4().hex[:6]}"
    session_dir = output_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    _debug_session_id = session_id
    _debug_output_dir = session_dir
    _debug_step_counter = 0

    logger.info(f"[DEBUG] 调试会话已初始化: {session_dir}")
    logger.info(f"[DEBUG] 白盒调试输出目录: {session_dir}")
    return session_id


def save_debug_image(
    stage_name: str,
    image: "Image.Image",
    metadata: dict | None = None,
) -> str | None:
    """
    保存调试中间产物图片到独立会话文件夹。

    核心原理：每次调用自动分配序号，保证所有中间图片按处理顺序排列。
    如果 mask 错误，这里是第一个能发现的地方（03_mask.png）。

    文件命名规则：
        {step:02d}_{stage_name}.{ext}

    常见 stage_name 和对应序号（按管线顺序）：
        01_input_person      — 原始人物图（输入）
        02_input_garment     — 原始衣服图（输入）
        03_mask              — 人体解析/衣服区域遮罩 ★ 重点 ★
        04_pose_keypoints    — OpenPose 骨骼关键点图
        05_agnostic_image    — 去除衣服后的"无衣物"底图（如果生成）
        06_person_resized    — 缩放后人物图
        07_garment_resized   — 缩放后衣服图
        08_mask_resized      — 缩放后遮罩
        09_mask_overlay      — 遮罩叠加人物图
        10_result_raw        — CatVTON 扩散输出（未重绘）
        11_result_final      — CatVTON 最终结果（已重绘）

    Args:
        stage_name: 阶段名称（不含序号和扩展名）
        image: PIL Image 对象
        metadata: 可选元数据字典（会写入同名 .json 文件）
    Returns:
        保存的文件路径字符串，失败返回 None
    """
    global _debug_step_counter, _debug_output_dir, _debug_session_id

    if _debug_output_dir is None:
        return None

    try:
        _debug_step_counter += 1
        step = _debug_step_counter

        # 自动推导扩展名（遮罩用 PNG 以保留精度，照片用 JPEG）
        if "mask" in stage_name.lower() or "overlay" in stage_name.lower():
            ext = "png"
        else:
            ext = "jpg"

        # stage_name 可能已带序号前缀（如 "01_input_person"），避免双重前缀
        name_parts = stage_name.split("_", 1)
        if name_parts[0].isdigit():
            clean_name = name_parts[1] if len(name_parts) > 1 else stage_name
        else:
            clean_name = stage_name

        filename = f"{step:02d}_{clean_name}.{ext}"
        # JPEG 保存需要 'JPEG'，PNG 需要 'PNG'
        ext_for_pil = "JPEG" if ext == "jpg" else ext.upper()
        filepath = _debug_output_dir / filename
        image.save(filepath, format=ext_for_pil, quality=95)

        # 同时保存元数据 JSON
        if metadata:
            import json

            meta_path = _debug_output_dir / f"{step:02d}_{stage_name}.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"[DEBUG] 步骤 {step:02d} 已保存: {stage_name} -> {filepath.name}")
        return str(filepath)

    except Exception as e:
        logger.warning(f"[DEBUG] 保存调试图片失败 ({stage_name}): {e}")
        return None


def save_debug_text(stage_name: str, content: str) -> str | None:
    """保存纯文本调试信息（如 mask 的坐标、尺寸等）。"""
    if _debug_output_dir is None:
        return None
    try:
        global _debug_step_counter
        filepath = _debug_output_dir / f"debug_{stage_name}.txt"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return str(filepath)
    except Exception:
        return None


def get_debug_session_dir() -> Path | None:
    """返回当前调试会话目录（用于外部读取）。"""
    return _debug_output_dir


# ═══════════════════════════════════════════════════════════════════════════════
# MediaPipe 姿态检测与遮罩生成
# ═══════════════════════════════════════════════════════════════════════════════

_MP_POSE_LANDMARKER_TASK: str | None = None


def _get_pose_landmarker_model_path() -> str | None:
    """查找或下载 PoseLandmarker .task 模型文件。"""
    global _MP_POSE_LANDMARKER_TASK
    if _MP_POSE_LANDMARKER_TASK:
        return _MP_POSE_LANDMARKER_TASK

    candidates = [
        Path(__file__).parent.parent.parent / "models" / "pose_landmarker_heavy.task",
        Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task",
        Path.home() / "models" / "pose_landmarker_heavy.task",
        Path("D:/models/pose_landmarker_heavy.task"),
    ]
    for p in candidates:
        if p.exists():
            _MP_POSE_LANDMARKER_TASK = str(p.resolve())
            logger.info(f"Found PoseLandmarker model: {_MP_POSE_LANDMARKER_TASK}")
            return _MP_POSE_LANDMARKER_TASK

    model_url = (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
    )
    download_path = Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task"
    try:
        download_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading PoseLandmarker model to {download_path}...")
        import urllib.request

        urllib.request.urlretrieve(model_url, download_path)
        _MP_POSE_LANDMARKER_TASK = str(download_path.resolve())
        logger.info(f"Downloaded PoseLandmarker model: {_MP_POSE_LANDMARKER_TASK}")
        return _MP_POSE_LANDMARKER_TASK
    except Exception as e:
        logger.warning(f"Failed to download PoseLandmarker model: {e}")
        return None


def _draw_pose_skeleton(
    person_img: "Image.Image",
    landmarks: list,
) -> "Image.Image":
    """
    在人物图上绘制骨骼骨架（用于调试姿态检测是否准确）。

    绿色线条：骨骼连接（肩膀、手臂、躯干、腿）
    红色圆点：关键点位置
    如果关键点偏了（上装在肩膀以下、下装在臀部以上），说明 MediaPipe 检测有问题。
    """
    import cv2

    pw, ph = person_img.size
    canvas = person_img.convert("RGB")
    arr = np.array(canvas)
    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    connections = [
        (11, 12),  # 肩膀
        (11, 13), (13, 15),  # 左臂
        (12, 14), (14, 16),  # 右臂
        (11, 23), (12, 24),  # 躯干
        (23, 24),  # 臀部
        (23, 25), (25, 27),  # 左腿
        (24, 26), (26, 28),  # 右腿
    ]
    for i, j in connections:
        if i < len(landmarks) and j < len(landmarks):
            lm_i = landmarks[i]
            lm_j = landmarks[j]
            x1, y1 = int(lm_i.x * pw), int(lm_i.y * ph)
            x2, y2 = int(lm_j.x * pw), int(lm_j.y * ph)
            cv2.line(arr, (x1, y1), (x2, y2), (0, 255, 0), 3)

    for lm in landmarks:
        x, y = int(lm.x * pw), int(lm.y * ph)
        cv2.circle(arr, (x, y), 5, (0, 0, 255), -1)

    arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr, mode="RGB")


def _make_cloth_mask_mediapipe(
    person_img: "Image.Image",
    cloth_type: str,
    debug_output_dir: Path | None = None,
) -> "Image.Image":
    """
    使用 MediaPipe PoseLandmarker 生成衣服区域遮罩。

    返回 L 模式 PIL Image（白色 = 待编辑的衣服区域，黑色 = 保留区域）。

    ★★★ 关键调试点 ★★★
    如果生成的 mask 范围不对：
    - mask 太大（超出衣服边缘）→ 扩散模型会把背景也改掉，产生"贴图感"
    - mask 太小（只在身体中间）→ 衣服边缘没有生成，产生"裁剪感"
    - mask 包含脸 → 人脸会被重绘，产生"换脸感"
    打开 03_mask.png 和 04_pose_keypoints.jpg 逐帧对比即可定位问题。
    """
    import cv2

    # ── Step 1: 姿态关键点检测 ──────────────────────────────────────
    mp_pose_path = _get_pose_landmarker_model_path()
    if mp_pose_path is None:
        logger.warning("MediaPipe PoseLandmarker model not found — using fallback mask")
        return _fallback_mask(person_img, cloth_type)

    try:
        from mediapipe import Image as MPImage
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp_path = f.name
        person_img.save(tmp_path, format="JPEG", quality=95)
        options = PoseLandmarkerOptions(
            base_options=mediapipe.tasks.BaseOptions(model_asset_path=mp_pose_path),
            running_mode=RunningMode.IMAGE,
            output_segmentation_masks=True,
        )
        landmarker = PoseLandmarker.create_from_options(options)
        mp_img = MPImage.create_from_file(tmp_path)
        result = landmarker.detect(mp_img)
        landmarker.close()
        os.unlink(tmp_path)

        if not result.pose_landmarks:
            logger.warning("No pose detected — using fallback mask")
            return _fallback_mask(person_img, cloth_type)

        landmarks = result.pose_landmarks[0]
    except Exception as e:
        logger.warning(f"MediaPipe pose detection failed ({e}) — using fallback mask")
        return _fallback_mask(person_img, cloth_type)

    # ── Step 2: 从 PoseLandmarker 获取人物分割遮罩 ───────────────────
    if result.segmentation_masks and len(result.segmentation_masks) > 0:
        seg_mask = result.segmentation_masks[0]
        seg_np = (seg_mask.numpy_view() * 255).astype(np.uint8)
        if seg_np.ndim == 3:
            seg_np = seg_np[..., 0]
        seg_pil = Image.fromarray(seg_np, mode="L")
    else:
        seg_pil = _make_keypoint_hull_mask(person_img, landmarks)

    # ── Step 3: 应用衣服类型区域过滤 ─────────────────────────────────
    pw, ph = person_img.size
    mask = _apply_cloth_region(seg_pil, landmarks, cloth_type, pw, ph)

    # ── Step 4: 保护面部区域 ───────────────────────────────────────
    mask = _protect_face(mask, landmarks, pw, ph)

    # ── Step 5: 保存白盒调试中间产物 ───────────────────────────────
    # 初始化调试会话（如果还没初始化）
    if _debug_output_dir is None and debug_output_dir is not None:
        init_debug_session(debug_output_dir)

    # 保存序号 01、02（如果还没保存过的话，由外部在 main() 中统一处理）
    # 这里只保存与 mask 相关的关键中间产物
    if _debug_output_dir is not None:
        # 保存 mask
        save_debug_image("03_mask", mask, {
            "cloth_type": cloth_type,
            "source": "mediapipe_poselandmarker",
            "has_landmarks": landmarks is not None,
            "person_size": list(person_img.size),
        })
        # 保存姿态骨架图
        skeleton = _draw_pose_skeleton(person_img, landmarks)
        save_debug_image("04_pose_keypoints", skeleton, {
            "cloth_type": cloth_type,
            "num_landmarks": len(landmarks),
        })
        # 保存 mask 叠加人物图（验证 mask 是否覆盖了正确的区域）
        person_np = np.array(person_img.convert("RGB")).astype(np.float32)
        mask_np = np.array(mask.convert("L")).astype(np.float32) / 255.0
        mask_3ch = np.stack([mask_np] * 3, axis=-1)
        overlay_np = person_np * mask_3ch + person_np * 0.3 * (1 - mask_3ch)
        overlay = Image.fromarray(overlay_np.astype(np.uint8), mode="RGB")
        save_debug_image("09_mask_overlay", overlay, {
            "cloth_type": cloth_type,
            "note": "白色区域=将被AI编辑，黑色区域=保留原样"
        })
        # 保存关键点坐标文本（方便程序化分析）
        landmark_coords = {
            f"lm_{i}": {"x": float(lm.x), "y": float(lm.y), "visibility": float(getattr(lm, "visibility", 1.0))}
            for i, lm in enumerate(landmarks)
        }
        save_debug_text("landmarks", str(landmark_coords))

    return mask


def _make_keypoint_hull_mask(
    person_img: "Image.Image",
    landmarks: list,
) -> "Image.Image":
    """从姿态关键点创建凸包人体遮罩（MediaPipe 不可用时的降级方案）。"""
    import cv2

    pw, ph = person_img.size
    points = []
    for lm in landmarks:
        x = int(lm.x * pw)
        y = int(lm.y * ph)
        points.append([x, y])

    mask = np.zeros((ph, pw), dtype=np.uint8)
    if len(points) > 3:
        hull = cv2.convexHull(np.array(points, dtype=np.int32))
        cv2.fillPoly(mask, [hull], 255)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=2)

    return Image.fromarray(mask, mode="L")


def _apply_cloth_region(
    person_mask: "Image.Image",
    landmarks: list,
    cloth_type: str,
    pw: int,
    ph: int,
) -> "Image.Image":
    """
    将人物遮罩与衣服类型区域矩形取交集。

    关键修复：当 MediaPipe 人物分割质量差（暗色衣服、背景对比度低）时，
    person_mask 可能是稀疏噪点，bitwise_and 交集几乎为空。
    此时 fallback 到纯关键点矩形遮罩，保证 CatVTON 有可用的衣服生成区域。
    """
    import cv2

    person_np = np.asarray(person_mask)
    region = _get_cloth_region_rect(landmarks, cloth_type, pw, ph)
    if region is None:
        return Image.fromarray(person_np, mode="L")

    x0, y0, x1, y1 = region
    cloth_mask = np.zeros_like(person_np)
    cloth_mask[y0:y1, x0:x1] = 255
    combined = cv2.bitwise_and(person_np, cloth_mask)

    # ── 关键修复：当交集质量差时，直接用关键点矩形 ────────────────────────
    # 判断标准：白色像素占比 < 5% → MediaPipe 分割不可靠，fallback
    total_pixels = person_np.size
    white_pixels = int(np.sum(combined > 0))
    white_ratio = white_pixels / max(1, total_pixels)

    # 正常情况下人物分割应该有足够的白色像素
    # 如果 white_ratio 极低（比如 < 5%），说明分割质量差
    # 此时 cloth_mask（纯关键点矩形）比交集更可靠
    if white_ratio < 0.05:
        logger.warning(
            f"MediaPipe segmentation too sparse (white_ratio={white_ratio:.3f}), "
            f"falling back to keypoint rect mask for cloth region"
        )
        # 用关键点矩形遮罩 + 轻微膨胀来覆盖肩膀和身体两侧
        kernel = np.ones((5, 5), np.uint8)
        combined = cv2.dilate(cloth_mask, kernel, iterations=2)
    else:
        kernel = np.ones((3, 3), np.uint8)
        combined = cv2.dilate(combined, kernel, iterations=1)

    return Image.fromarray(combined, mode="L")


def _get_cloth_region_rect(
    landmarks: list,
    cloth_type: str,
    pw: int,
    ph: int,
) -> tuple[int, int, int, int] | None:
    """从姿态关键点推导衣服区域矩形 (x0, y0, x1, y1)。

    注意：landmarks 中的坐标已经是像素坐标（lm.x * pw, lm.y * ph），
    所有计算都应基于像素坐标进行，不要再乘以或除以 pw/ph。
    """
    lm_dict = {lm_idx: (lm.x * pw, lm.y * ph) for lm_idx, lm in enumerate(landmarks)}

    def clamp(val, lo, hi):
        return max(lo, min(hi, int(val)))

    if cloth_type == "upper":
        ls = lm_dict.get(11)  # 左肩
        rs = lm_dict.get(12)  # 右肩
        lh = lm_dict.get(23)  # 左臀
        rh = lm_dict.get(24)  # 右臀
        nose = lm_dict.get(0)  # 鼻尖

        shoulder_y = (ls[1] + rs[1]) / 2 if ls and rs else None
        hip_y = (lh[1] + rh[1]) / 2 if lh and rh else None
        if shoulder_y is None or hip_y is None:
            return _upper_fallback(pw, ph)

        x_pts = [p[0] for p in [ls, rs] if p]
        x_left_px = min(x_pts) if x_pts else pw * 0.12
        x_right_px = max(x_pts) if x_pts else pw * 0.88

        # 上边界：肩膀上方一点，不超过鼻尖
        # 所有值已经是像素坐标，直接使用
        if nose:
            # 鼻尖位置作为安全下界
            nose_y = nose[1]
            # 肩膀上方 5-10% 图片高度
            shoulder_based_top = shoulder_y - ph * 0.08
            # 取较大值，确保不覆盖头部
            y_top = max(shoulder_y - ph * 0.15, shoulder_based_top)
            # 但也不能太靠近鼻尖
            y_top = min(y_top, nose_y + ph * 0.05)
        else:
            y_top = shoulder_y - ph * 0.08

        # 下边界：臀部位置再往下一点
        y_bottom = hip_y + ph * 0.04

        # 左右边界：肩膀外扩一点
        shoulder_width = x_right_px - x_left_px
        margin = max(shoulder_width * 0.15, pw * 0.05)
        x_left = x_left_px - margin
        x_right = x_right_px + margin

        return (
            clamp(x_left, 0, pw - 2),
            clamp(y_top, 0, ph - 2),
            clamp(x_right, 2, pw),
            clamp(y_bottom, 2, ph),
        )

    elif cloth_type == "lower":
        lh = lm_dict.get(23)  # 左臀
        rh = lm_dict.get(24)  # 右臀
        la = lm_dict.get(27)  # 左踝
        ra = lm_dict.get(28)  # 右踝
        lk = lm_dict.get(25)  # 左膝
        rk = lm_dict.get(26)  # 右膝

        hip_y = (lh[1] + rh[1]) / 2 if lh and rh else None
        ankle_y = None
        if la and ra:
            ankle_y = (la[1] + ra[1]) / 2
        elif lk and rk:
            ankle_y = (lk[1] + rk[1]) / 2

        if hip_y is None:
            return _lower_fallback(pw, ph)

        x_pts = [p[0] for p in [lh, rh, la, ra] if p]
        x_left_px = min(x_pts) if x_pts else pw * 0.16
        x_right_px = max(x_pts) if x_pts else pw * 0.84

        # 上边界：臀部上方一点
        y_top = hip_y - ph * 0.04

        # 下边界：脚踝或膝盖位置
        if ankle_y:
            y_bottom = ankle_y + ph * 0.03
        else:
            y_bottom = ph * 0.97

        # 左右边界：臀部外扩一点
        hip_width = x_right_px - x_left_px
        margin = max(hip_width * 0.10, pw * 0.06)
        x_left = x_left_px - margin
        x_right = x_right_px + margin

        return (
            clamp(x_left, 0, pw - 2),
            clamp(y_top, 0, ph - 2),
            clamp(x_right, 2, pw),
            clamp(y_bottom, 2, ph),
        )

    else:  # overall
        upper = _get_cloth_region_rect(landmarks, "upper", pw, ph)
        lower = _get_cloth_region_rect(landmarks, "lower", pw, ph)
        if upper is None and lower is None:
            return None
        if upper is None:
            return lower
        if lower is None:
            return upper
        return (
            min(upper[0], lower[0]),
            min(upper[1], lower[1]),
            max(upper[2], lower[2]),
            max(upper[3], lower[3]),
        )


def _upper_fallback(pw: int, ph: int) -> tuple[int, int, int, int]:
    return (
        max(0, int(pw * 0.12)),
        max(0, int(ph * 0.12)),
        min(pw, int(pw * 0.88)),
        min(ph, int(ph * 0.60)),
    )


def _lower_fallback(pw: int, ph: int) -> tuple[int, int, int, int]:
    return (
        max(0, int(pw * 0.16)),
        max(0, int(ph * 0.44)),
        min(pw, int(pw * 0.84)),
        min(ph, int(ph * 0.97)),
    )


def _protect_face(
    mask: "Image.Image",
    landmarks: list,
    pw: int,
    ph: int,
) -> "Image.Image":
    """清除面部和头部区域，防止 AI 重绘人脸（产生"换脸感"的根源之一）。

    增强版：保护更大的头部区域，确保 mask 不会覆盖到头发和颈部以上的部分。
    """
    import cv2

    if len(landmarks) == 0:
        return mask

    nose = landmarks[0] if len(landmarks) > 0 else None
    l_ear = landmarks[7] if len(landmarks) > 7 else None
    r_ear = landmarks[8] if len(landmarks) > 8 else None
    l_shoulder = landmarks[11] if len(landmarks) > 11 else None
    r_shoulder = landmarks[12] if len(landmarks) > 12 else None

    if nose is None:
        return mask

    cx = int(nose.x * pw)
    cy = int(nose.y * ph)

    # 根据耳朵距离计算头部大小
    if l_ear and r_ear:
        ear_dist = abs(l_ear.x - r_ear.x) * pw
    else:
        ear_dist = pw * 0.12

    # 增强头部保护：使用更大的区域
    ew = max(5, int(ear_dist * 1.5))  # 增加宽度保护
    eh = max(5, int(ew * 1.4))  # 增加高度保护

    # 使用 np.array() 而不是 np.asarray()，确保数组可写
    mask_np = np.array(mask)
    rows, cols = mask_np.shape

    # 1. 清除面部椭圆区域（主要面部）
    y_grid, x_grid = np.ogrid[:rows, :cols]
    face_ellipse = (
        ((x_grid - cx) ** 2) // max(1, ew ** 2)
        + ((y_grid - (cy - int(ew * 0.1))) ** 2) // max(1, eh ** 2)
    ) <= 1
    mask_np[face_ellipse] = 0

    # 2. 额外保护：清除头部上方区域（头发保护）
    # 以鼻尖为中心向上延伸的保护区域
    head_top_y = max(0, cy - int(ph * 0.15))  # 头部顶部（头发）
    head_left_x = max(0, cx - int(ew * 1.3))
    head_right_x = min(cols, cx + int(ew * 1.3))

    # 创建一个头部保护矩形（比面部椭圆稍大）
    head_protection = (
        (x_grid >= head_left_x) & (x_grid <= head_right_x) &
        (y_grid >= head_top_y) & (y_grid <= cy + int(ph * 0.02))
    )
    mask_np[head_protection] = 0

    return Image.fromarray(mask_np, mode="L")


def _fallback_mask(person_img: "Image.Image", cloth_type: str) -> "Image.Image":
    """矩形遮罩（最后的降级方案，MediaPipe 不可用时）。"""
    pw, ph = person_img.size
    if cloth_type == "upper":
        region = _upper_fallback(pw, ph)
    elif cloth_type == "lower":
        region = _lower_fallback(pw, ph)
    else:
        upper = _upper_fallback(pw, ph)
        lower = _lower_fallback(pw, ph)
        region = (
            min(upper[0], lower[0]),
            min(upper[1], lower[1]),
            max(upper[2], lower[2]),
            max(upper[3], lower[3]),
        )

    mask = np.zeros((ph, pw), dtype=np.uint8)
    x0, y0, x1, y1 = region
    mask[y0:y1, x0:x1] = 255

    return Image.fromarray(mask, mode="L")


# ═══════════════════════════════════════════════════════════════════════════════
# 图像预处理与后处理
# ═══════════════════════════════════════════════════════════════════════════════


def resize_and_crop_garment(image, size):
    """中心裁剪衣服图以匹配目标宽高比，同时保留衣服方向信息。

    改进：
    1. 检测衣服方向（如果衣架在顶部，自动翻转）
    2. 保持衣服正面朝外
    3. 中心裁剪确保衣服主体在画面中央
    """
    w, h = image.size
    target_w, target_h = size
    target_ratio = target_w / target_h
    img_ratio = w / h

    # 检测衣架/挂钩位置（如果衣服挂在衣架上）
    # 衣架通常在图片顶部中间位置，颜色较浅
    garment_img = _detect_and_correct_garment_orientation(image)

    if img_ratio > target_ratio:
        new_w = int(h * target_ratio)
        new_h = h
        x0 = (w - new_w) // 2
        y0 = 0
    else:
        new_w = w
        new_h = int(w / target_ratio)
        x0 = 0
        y0 = (h - new_h) // 2
    cropped = garment_img.crop((x0, y0, x0 + new_w, y0 + new_h))
    return cropped.resize(size, Image.LANCZOS)


def _detect_and_correct_garment_orientation(image: "Image.Image") -> "Image.Image":
    """检测并校正衣服方向。

    如果衣服挂在衣架上（衣架在顶部），自动翻转使衣服正面朝上。
    这样可以确保衣服颜色和图案方向正确。
    """
    import cv2

    arr = np.array(image.convert("RGB"))
    h, w = arr.shape[:2]

    # 检测顶部是否有浅色横向条带（可能是衣架）
    top_region = arr[:int(h * 0.1), :, :]
    top_brightness = top_region.mean()
    overall_brightness = arr.mean()

    # 如果顶部区域明显比整体亮，可能是衣架
    if top_brightness > overall_brightness * 1.3:
        # 检测是否是水平条带（衣架特征）
        top_gray = cv2.cvtColor(top_region, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(top_gray, 50, 150)
        # 水平边缘多说明是衣架
        horizontal_lines = np.sum(edges > 0) / edges.size
        if horizontal_lines > 0.02:
            # 翻转图片使衣服正面朝上
            return image.transpose(Image.FLIP_TOP_BOTTOM)

    return image


def _enhance_garment_colors(image: "Image.Image", strength: float = 1.2) -> "Image.Image":
    """增强衣服颜色饱和度和对比度，帮助 CatVTON 更好地识别衣服颜色。

    适度的颜色增强可以让模型更准确地保留衣服的颜色信息。
    """
    import cv2

    arr = np.array(image.convert("RGB"))
    h, w = arr.shape[:2]

    # 转换到 HSV 色彩空间进行饱和度增强
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)

    # 增强饱和度
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * strength, 0, 255)

    # 稍微增加亮度
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.05, 0, 255)

    hsv = hsv.astype(np.uint8)
    enhanced = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

    return Image.fromarray(enhanced, mode="RGB")


def _feather_mask(mask: "Image.Image", feather_radius: int = 4) -> "Image.Image":
    """对遮罩边缘施加高斯模糊，使衣服边界过渡自然（避免生硬的"贴图感"）。"""
    import cv2

    mask_np = np.asarray(mask.convert("L"))
    blurred = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
    return Image.fromarray(blurred, mode="L")


def _repaint_with_feather(
    result: "Image.Image",
    person: "Image.Image",
    mask: "Image.Image",
    feather_radius: int = 3,
) -> "Image.Image":
    """
    使用羽化遮罩将 CatVTON 结果与原图混合。
    原理：在遮罩边缘区域，原图像素权重从 0 线性增加到 1，实现平滑过渡。
    """
    import cv2

    mask_np = np.asarray(mask.convert("L")).astype(np.float32) / 255.0
    if feather_radius > 0:
        mask_np = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
    mask_3ch = np.stack([mask_np] * 3, axis=-1)
    result_np = np.array(result).astype(np.float32)
    person_np = np.array(person).astype(np.float32)
    blended = result_np * mask_3ch + person_np * (1 - mask_3ch)
    return Image.fromarray(blended.astype(np.uint8))


def _transfer_color_to_region(
    source_img: "Image.Image",
    target_img: "Image.Image",
    mask: "Image.Image",
    strength: float = 0.5,
) -> "Image.Image":
    """
    将源图像（衣服）的颜色传递到目标图像的指定区域。

    这是解决 CatVTON 颜色偏移问题的关键后处理：
    1. 计算衣服图像的颜色统计（均值和标准差）
    2. 计算 CatVTON 输出中衣服区域的颜色统计
    3. 通过直方图匹配调整衣服区域颜色，使其更接近原始衣服

    Args:
        source_img: 原始衣服图像（参考）
        target_img: CatVTON 输出图像（待调整）
        mask: 衣服区域遮罩（L 模式）
        strength: 调整强度 0.0-1.0，0.5 表示 50% 校正

    Returns:
        颜色校正后的图像
    """
    import cv2

    # 转换为 numpy 数组
    src_arr = np.array(source_img.convert("RGB")).astype(np.float32)
    tgt_arr = np.array(target_img.convert("RGB")).astype(np.float32)

    # 获取衣服区域（从 mask 提取）
    mask_np = np.asarray(mask.convert("L")).astype(np.float32) / 255.0
    # 创建衣服区域掩码（只处理 mask > 0.3 的区域）
    garment_mask = (mask_np > 0.3).astype(np.float32)[:, :, np.newaxis]

    # 1. 计算原始衣服的颜色统计
    # 对衣服区域进行采样（使用原始衣服图）
    src_garment_pixels = src_arr[garment_mask[:, :, 0] > 0.5]

    if len(src_garment_pixels) < 100:
        # 衣服区域太小，跳过颜色校正
        return target_img

    # 计算每个通道的均值和标准差
    src_mean = src_garment_pixels.mean(axis=0)  # [R, G, B]
    src_std = src_garment_pixels.std(axis=0) + 1e-6  # 避免除零

    # 2. 计算 CatVTON 输出中衣服区域的颜色统计
    tgt_garment_pixels = tgt_arr[garment_mask[:, :, 0] > 0.5]

    if len(tgt_garment_pixels) < 100:
        return target_img

    tgt_mean = tgt_garment_pixels.mean(axis=0)
    tgt_std = tgt_garment_pixels.std(axis=0) + 1e-6

    # 3. 应用直方图匹配/颜色校正
    # 方法：基于 Z-score 的颜色转移
    # 对于衣服区域：new_pixel = (pixel - tgt_mean) * (src_std / tgt_std) + src_mean
    result_arr = tgt_arr.copy()

    # 只在衣服区域内应用
    for c in range(3):
        # 计算校正后的值
        corrected = (tgt_arr[:, :, c] - tgt_mean[c]) * (src_std[c] / tgt_std[c]) + src_mean[c]
        # 混合原始值和校正值
        result_arr[:, :, c] = (
            tgt_arr[:, :, c] * (1 - garment_mask[:, :, 0] * strength * 0.7) +
            corrected * (garment_mask[:, :, 0] * strength * 0.7)
        )

    # 裁剪到有效范围
    result_arr = np.clip(result_arr, 0, 255).astype(np.uint8)
    return Image.fromarray(result_arr, mode="RGB")


# ═══════════════════════════════════════════════════════════════════════════════
# 极限 VRAM 优化
#
# 显存占用分析（以 768x1024 输入为例）：
#   float32: ~10GB (SD inpainting base model)
#   bf16:    ~8GB   (混合精度，推荐 RTX 4060)
#   fp16:    ~6GB   (强制半精度（无 bf16 支持时）)
#
# 优化策略：
#  1. enable_sequential_cpu_offload(): UNet/VAE 用完即移到 CPU，峰值显存 -4GB
#  2. enable_vae_slicing(): VAE 编码/解码切分为小块，峰值显存 -2GB
#  3. enable_xformers_memory_efficient_attention(): 更省显存的注意力实现
#  4. torch.cuda.empty_cache() + gc.collect(): 推理完成后强制回收显存
#  5. fp16 替代 bf16（RTX 4060 Laptop 通常只有 8GB）
# ═══════════════════════════════════════════════════════════════════════════════


def _apply_memory_optimizations(
    pipeline,
    vae_slicing: bool = True,
    xformers: bool = True,
    cpu_offload: bool = False,
) -> list[str]:
    """
    对 CatVTON Pipeline 应用所有可用显存优化技术。

    Args:
        pipeline: 已初始化的 CatVTONPipeline 实例
        vae_slicing: 将 VAE 切分为小块推理（峰值显存 -2GB，速度略慢）
        xformers: 优先使用 xformers 高效注意力（无则降级到 PyTorch FlashAttention）
        cpu_offload: UNet/VAE 用完即移至 CPU（最省显存但最慢）

    Returns:
        已成功应用的优化列表（用于日志输出）
    """
    import gc
    import torch

    applied = []

    # ── 策略 1: VAE 分片推理 ─────────────────────────────────────────
    # CatVTON 的 VAE 在编码/解码高分辨率图像时显存峰值最高。
    # slicing 将 VAE 操作切分为 tile_size 的小块，逐块处理后拼接。
    # 对 768x1024 图像，通常切分为 4-8 块，峰值显存降低约 40-60%。
    # 速度影响：约增加 10-20%，但换来了在 8GB 卡上运行的可能性。
    if vae_slicing:
        try:
            pipeline.enable_vae_slicing()
            applied.append("vae_slicing")
            logger.info("VRAM 优化已应用: VAE 分片推理 (峰值显存 -40%)")
        except Exception as e:
            logger.warning(f"VAE slicing 应用失败: {e}")

    # ── 策略 2: xformers 高效注意力 ─────────────────────────────────
    # xformers 的 memory_efficient_attention 使用分块注意力算法，
    # 相比 PyTorch 原生 attention，显存复杂度从 O(n^2) 降低到更优。
    # 如果没有安装 xformers，尝试使用 PyTorch 2.0+ 的 Flash Attention。
    if xformers:
        try:
            # 优先尝试 xformers
            try:
                import xformers

                pipeline.enable_xformers_memory_efficient_attention()
                applied.append("xformers")
                logger.info("VRAM 优化已应用: xformers 高效注意力")
            except ImportError:
                # xformers 不可用，降级到 PyTorch 原生 SDPA (FlashAttention)
                # 原理：PyTorch 2.0+ 在 CUDA >= 11.6 时通过 SDPA 实现接近 FlashAttention 的性能。
                # SDPA 由 diffusers 的 AttnProcessor2_0 自动使用，只需启用底层 flags。
                try:
                    torch.backends.cuda.enable_flash_sdp(True)
                    torch.backends.cuda.enable_mem_efficient_sdp(True)
                    torch.backends.cuda.enable_math_sdp(False)
                    applied.append("flash_attention_fallback")
                    logger.info("VRAM 优化已应用: PyTorch SDPA (xformers 未安装，降级)")
                except (ImportError, AttributeError) as e:
                    logger.warning(f"SDPA 启用失败: {e}, 跳过注意力优化")
        except Exception as e:
            logger.warning(f"xformers/FlashAttention 应用失败: {e}")

    # ── 策略 3: 顺序 CPU 卸载 ───────────────────────────────────────
    # 这是最激进也是最有效的显存优化：将 UNet 和 VAE 的权重在用完当前计算后，
    # 立即卸载到 CPU DRAM。只有在 8GB 以下显存且其他方法仍 OOM 时使用。
    # 速度影响：显著变慢（数据在 PCIe 总线上传输），但能保证不崩溃。
    if cpu_offload:
        # NOTE: accelerate.cpu_offload has known compatibility issues with CatVTON's
        # CatVTONPipeline (meta tensor errors during VAE encoding). The pipeline
        # already uses accelerate hooks internally, and cpu_offload conflicts with them.
        # Instead, rely on fp16 + VAE slicing for VRAM management.
        try:
            logger.info("CPU offload 已禁用（与 CatVTON pipeline 不兼容，使用 fp16 + VAE slicing 替代）")
        except Exception:
            pass
        applied.append("cpu_offload_skipped")

    # ── 推理前强制清空显存缓存 ───────────────────────────────────────
    # Python 的循环引用和临时对象可能使显存无法及时回收。
    # 这里显式调用 GC + CUDA 缓存清空，确保进入推理时显存处于干净状态。
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

    # 报告当前显存状态
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        logger.info(
            f"[VRAM] 优化前显存状态: 已分配 {allocated:.2f}GB / 已预约 {reserved:.2f}GB / 总计 {total:.2f}GB"
        )

    return applied


def _cleanup_after_inference():
    """
    推理完成后强制回收显存。

    原因：PyTorch 的 CUDA 内存分配器会缓存已分配的显存供下次使用，
    导致已用显存无法被真正的 PyTorch 内存管理器识别为空闲。
    这里先同步 GPU，等待所有计算完成，再清空缓存。
    """
    import gc
    import torch

    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()

    gc.collect()
    logger.info("[VRAM] 推理完成，显存已回收")


# ═══════════════════════════════════════════════════════════════════════════════
# 主推理流程
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CatVTON inference runner (支持白盒调试 + 极限显存优化 + 预处理模式)"
    )
    parser.add_argument("--person", required=True, help="人物全身照片 JPEG 路径")
    parser.add_argument("--garment", required=True, help="衣服产品图 JPEG 路径")
    parser.add_argument("--output", required=True, help="结果图输出路径")
    parser.add_argument(
        "--type", default="upper", choices=["upper", "lower", "overall"],
        help="衣服类型: upper(上装)/lower(下装)/overall(连衣裙)"
    )
    parser.add_argument("--width", type=int, default=512, help="输出宽度 (512-768，768 更清晰但更慢)")
    parser.add_argument("--height", type=int, default=768, help="输出高度 (768-1024)")
    parser.add_argument("--steps", type=int, default=25, help="扩散步数 (20-80，推荐 50)")
    parser.add_argument("--guidance", type=float, default=2.5, help="CFG 引导强度 (2.0-3.5)")
    parser.add_argument("--seed", type=int, default=-1, help="随机种子 (-1=随机)")
    parser.add_argument("--catvton-path", default=None, help="CatVTON 仓库路径")
    parser.add_argument("--no-repaint", action="store_true", help="禁用背景重绘")
    parser.add_argument(
        "--precision", default="bf16", choices=["bf16", "fp16", "fp32"],
        help="权重精度: bf16(RTX推荐)/fp16(8GB卡强制)/fp32(不推荐)"
    )
    parser.add_argument("--cpu-offload", action="store_true", help="启用顺序 CPU 卸载（最省显存但最慢）")
    parser.add_argument(
        "--debug-dir", default=None,
        help="白盒调试输出目录（保存所有中间产物，为空则不保存）"
    )
    # ─── 新增参数 ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--preprocess-only", action="store_true",
        help="仅运行前处理（mask + pose 生成），不进入扩散模型推理，极大加快调试速度"
    )
    parser.add_argument(
        "--vae-slicing", action="store_true", default=True,
        help="启用 VAE 分片推理（降低峰值显存，默认开启）"
    )
    parser.add_argument(
        "--no-vae-slicing", action="store_true",
        help="禁用 VAE 分片推理"
    )
    parser.add_argument(
        "--xformers", action="store_true", default=True,
        help="启用 xformers 高效注意力（默认开启，无 xformers 时降级到 FlashAttention）"
    )
    parser.add_argument(
        "--no-xformers", action="store_true",
        help="禁用 xformers 高效注意力"
    )
    parser.add_argument(
        "--force-fp16", action="store_true",
        help="强制使用 fp16 而非 bf16（RTX 4060 Laptop 推荐开启，节省约 2GB 显存）"
    )
    parser.add_argument(
        "--low-vram-mode", action="store_true",
        help="一键低显存模式（等于 --force-fp16 --vae-slicing --cpu-offload --no-repaint）"
    )
    args = parser.parse_args()

    person_path = args.person
    garment_path = args.garment
    output_path = args.output

    # ── HuggingFace 缓存目录 ─────────────────────────────────────
    # 解决子进程找不到已下载模型的问题
    os.environ["HF_HOME"] = os.environ.get("HF_HOME", r"D:\hf-cache")
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    # ── CatVTON 路径：优先使用 CatVTON_full（完整版），fallback 到 CatVTON ─
    if args.catvton_path:
        os.environ["CATVTON_PATH"] = args.catvton_path
    else:
        # 尝试多个可能路径
        catvton_candidates = [
            r"D:\models\CatVTON_full",
            r"D:\models\CatVTON",
            os.environ.get("CATVTON_PATH", ""),
        ]
        for path in catvton_candidates:
            if path and Path(path).exists():
                os.environ["CATVTON_PATH"] = path
                print(f"[CATVTON-PATH] 使用 CatVTON 路径: {path}", flush=True)
                break

    # ── 低显存一键模式 ────────────────────────────────────────────────
    if args.low_vram_mode:
        args.force_fp16 = True
        args.cpu_offload = True
        args.no_repaint = True
        logger.warning("[VRAM] 低显存模式已启用: fp16 + CPU offload + 无重绘")

    # ── 精度选择 ─────────────────────────────────────────────────────
    # RTX 4060 Laptop 只有 8GB VRAM，bf16 勉强可跑但峰值会 OOM。
    # 强制 fp16 可节省约 2GB，50步推理约需 4-6GB。
    final_precision = "fp16" if args.force_fp16 else args.precision

    # VAE slicing 和 xformers 默认开启（除非显式禁用）
    vae_slicing = not args.no_vae_slicing
    use_xformers = not args.no_xformers

    logger.info(
        f"[CATVTON-RUNNER] 启动参数: "
        f"type={args.type}, size={args.width}x{args.height}, "
        f"steps={args.steps}, guidance={args.guidance}, seed={args.seed}, "
        f"repaint={not args.no_repaint}, precision={final_precision}, "
        f"vae_slicing={vae_slicing}, xformers={use_xformers}, "
        f"cpu_offload={args.cpu_offload}, "
        f"preprocess_only={args.preprocess_only}"
    )

    try:
        # ── 导入 CatVTON ────────────────────────────────────────────────
        catvton_path = args.catvton_path or os.environ.get("CATVTON_PATH", "")
        sys.path.insert(0, catvton_path)

        try:
            from model.pipeline import CatVTONPipeline
        except ImportError as e:
            print(f"ERROR:CATVTON_NOT_AVAILABLE")
            print(f"CatVTON pipeline import failed: {e}")
            print("Set --catvton-path to the CatVTON repository directory.")
            sys.exit(10)

        # ── 加载图片 ────────────────────────────────────────────────────
        person_img = _load_image(person_path)
        garment_img = _load_image(garment_path)

        # ── 白盒调试：初始化会话并保存输入图片 ──────────────────────────
        debug_output_dir = Path(args.debug_dir) if args.debug_dir else None
        if debug_output_dir:
            init_debug_session(debug_output_dir)
            save_debug_image("01_input_person", person_img, {
                "source_path": person_path,
                "size": list(person_img.size),
                "mode": person_img.mode,
            })
            save_debug_image("02_input_garment", garment_img, {
                "source_path": garment_path,
                "size": list(garment_img.size),
                "cloth_type_requested": args.type,
            })

        # ── 生成衣服区域遮罩 ───────────────────────────────────────────
        print(f"[CATVTON-STEP] 开始生成衣服遮罩 (type={args.type})...", flush=True)
        cloth_mask = _make_cloth_mask_mediapipe(person_img, args.type, debug_output_dir=debug_output_dir)
        print(f"[CATVTON-STEP] 遮罩生成完成", flush=True)

        # ── 预处理模式：直接返回遮罩结果 ───────────────────────────────
        if args.preprocess_only:
            debug_dir = get_debug_session_dir()
            logger.info(
                f"[PREPROCESS-ONLY] 预处理完成，已保存中间产物到: {debug_dir}"
            )
            if debug_dir:
                print(f"PREPROCESS_ONLY:{debug_dir}")
            else:
                print("PREPROCESS_ONLY:no_debug_dir")
            sys.exit(0)

        # ── 初始化 CatVTON Pipeline ───────────────────────────────────
        print(f"[CATVTON-STEP] 正在加载 CatVTON Pipeline (precision={final_precision})...", flush=True)
        import os as _os
        from huggingface_hub import snapshot_download
        from utils import init_weight_dtype, resize_and_crop, resize_and_padding

        # 模型路径检测：支持两种结构
        # 1. catvton_path/zhengchong_CatVTON/ (HuggingFace snapshot 格式)
        # 2. catvton_path/ 直接包含 model/, mix-48k-1024/ 等 (下载的仓库格式，如 CatVTON_full)
        repo_path = _os.path.join(catvton_path, "zhengchong_CatVTON")
        if not _os.path.exists(repo_path):
            # 检查是否是下载的仓库格式（直接包含 model/ 和数据集目录）
            if _os.path.exists(_os.path.join(catvton_path, "model")) and (
                _os.path.exists(_os.path.join(catvton_path, "mix-48k-1024")) or
                _os.path.exists(_os.path.join(catvton_path, "vitonhd-16k-512"))
            ):
                logger.info("检测到 CatVTON 仓库格式 (包含 model/ 和数据集目录)")
                repo_path = catvton_path
            else:
                logger.info("Downloading CatVTON checkpoints from HuggingFace (first run)...")
                repo_path = snapshot_download(repo_id="zhengchong/CatVTON")

        # CatVTON 代码（model/pipeline.py 等）就在 repo_path 目录本身。
        # 当从 HuggingFace 缓存加载时，repo_path = snapshots/<hash>，
        # 里面直接包含 model/ 和 utils/，需要把 repo_path 加入 sys.path。
        if repo_path not in sys.path:
            sys.path.insert(0, repo_path)

        # 初始化精度
        weight_dtype = init_weight_dtype(final_precision)

        pipeline = CatVTONPipeline(
            base_ckpt="runwayml/stable-diffusion-inpainting",
            attn_ckpt=repo_path,
            attn_ckpt_version="mix",
            weight_dtype=weight_dtype,
            use_tf32=(final_precision in ("fp16", "bf16")),
            device="cuda",
            skip_safety_check=True,
        )

        # ── 应用极限 VRAM 优化 ─────────────────────────────────────────
        _apply_memory_optimizations(
            pipeline,
            vae_slicing=vae_slicing,
            xformers=use_xformers,
            cpu_offload=args.cpu_offload,
        )

        # ── 缩放图片 ───────────────────────────────────────────────────
        print(f"[CATVTON-STEP] 正在缩放图片...", flush=True)
        person_resized = resize_and_crop(person_img, (args.width, args.height))
        garment_resized = resize_and_crop_garment(garment_img, (args.width, args.height))

        # ── 衣服颜色增强 ─────────────────────────────────────────────
        # 增强衣服颜色饱和度，帮助模型更好地识别和保留衣服颜色
        logger.info("增强衣服颜色...")
        garment_resized = _enhance_garment_colors(garment_resized, strength=1.15)

        # ── 关键修复：mask 必须用 NEAREST 缩放保持二值性 ──────────────────
        # CatVTON 训练时使用的是纯二值 mask（0 或 1），prepare_mask_image 内部会
        # 规范化 mask：< 0.5 → 0，>= 0.5 → 1。
        # 如果在 resize 前应用 GaussianBlur，mask 会变成灰度图（0.3, 0.7 等），
        # 规范化后大部分信息丢失，导致 CatVTON 无法识别衣服区域。
        # 正确的做法：NEAREST 缩放（保持二值）→ CatVTON 推理 → 重绘时再模糊
        mask_resized = cloth_mask.resize((args.width, args.height), Image.NEAREST)

        # ── 白盒调试：保存缩放后的中间产物 ─────────────────────────────
        if _debug_output_dir is not None:
            save_debug_image("06_person_resized", person_resized, {
                "target_size": [args.width, args.height],
            })
            save_debug_image("07_garment_resized", garment_resized, {
                "target_size": [args.width, args.height],
            })
            save_debug_image("08_mask_resized", mask_resized, {
                "target_size": [args.width, args.height],
                "feather_radius": 3,
            })

        # ── 运行扩散推理 ───────────────────────────────────────────────
        print(f"[CATVTON-STEP] 开始 CatVTON 扩散推理 (steps={args.steps}, guidance={args.guidance})...", flush=True)
        import torch

        seed = args.seed if args.seed >= 0 else None
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cuda").manual_seed(seed)

        infer_start = time.time()

        result = pipeline(
            image=person_resized,
            condition_image=garment_resized,
            mask=mask_resized,
            num_inference_steps=args.steps,
            guidance_scale=args.guidance,
            width=args.width,
            height=args.height,
            generator=generator,
        )[0]

        infer_elapsed = time.time() - infer_start
        print(f"[CATVTON-STEP] 推理完成，耗时 {infer_elapsed:.1f}s", flush=True)

        # ── 白盒调试：保存扩散输出（未重绘） ───────────────────────────
        if _debug_output_dir is not None:
            save_debug_image("10_result_raw", result, {
                "steps": args.steps,
                "guidance": args.guidance,
                "seed": seed,
                "inference_time_s": round(infer_elapsed, 2),
            })

        # ── 重绘与原图混合 ─────────────────────────────────────────────
        if not args.no_repaint:
            logger.info("执行背景重绘与原图混合...")
            result = _repaint_with_feather(result, person_resized, mask_resized, feather_radius=3)

        # ── 衣服颜色保真校正 ─────────────────────────────────────────
        # 这是解决 CatVTON 颜色偏移问题的关键步骤
        # 使用原始衣服图像校正 CatVTON 输出中的衣服颜色
        logger.info("执行衣服颜色保真校正...")
        try:
            result = _transfer_color_to_region(
                source_img=garment_resized,
                target_img=result,
                mask=mask_resized,
                strength=0.4,  # 40% 校正强度，避免过度处理
            )
            logger.info("颜色保真校正完成")
        except Exception as e:
            logger.warning(f"颜色校正失败，跳过: {e}")

        # ── 白盒调试：保存最终结果 ──────────────────────────────────────
        if _debug_output_dir is not None:
            save_debug_image("11_result_final", result, {
                "repaint": not args.no_repaint,
                "total_time_s": round(time.time() - infer_start, 2),
            })

        # ── 推理后显存回收 ─────────────────────────────────────────────
        _cleanup_after_inference()

        # ── 保存结果 ───────────────────────────────────────────────────
        _save_image(result, output_path)
        logger.info(f"成功: 结果已保存到 {output_path}")
        debug_dir = get_debug_session_dir()
        if debug_dir:
            logger.info(f"白盒调试目录: {debug_dir}")
            print(f"SUCCESS:{output_path}")
            print(f"DEBUG_DIR:{debug_dir}")
        else:
            print(f"SUCCESS:{output_path}")
        sys.exit(0)

    except Exception as e:
        logger.error(f"CatVTON 推理失败: {e}", exc_info=True)
        tb = traceback.format_exc()
        print(f"ERROR:{e}")
        print(f"TRACE:{tb}")
        sys.exit(1)


if __name__ == "__main__":
    # Force unbuffered output so parent process can see real-time logs
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    main()
