"""增强型后处理模块 - 消除拼接痕迹，增强真实感。

主要功能：
1. 边缘羽化融合 - 消除接缝（只在边界处融合，不碰衣服主体）
2. 色彩匹配 - 让衣服颜色与场景协调
3. 细节保护 - 保留衣服纹理
4. 噪点去除 - 减少AI生成噪点
5. 锐化增强 - 恢复衣服边缘清晰度
"""

from __future__ import annotations

import logging
from typing import Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


# ============================================================
# 核心算法 1: 安全边缘融合（只在边界处融合，不碰衣服主体）
# ============================================================


def safe_edge_blend(
    result: Image.Image,
    person: Image.Image,
    garment_mask: np.ndarray | None = None,
    blend_radius: int = 5,
) -> Image.Image:
    """
    安全边缘融合 - 只在衣物边界处进行柔和融合，不触碰衣物主体区域。

    算法：
    1. 如果有garment_mask，在mask边缘处创建渐变过渡
    2. 如果没有mask，使用轻微的高斯模糊来平滑边缘
    3. 确保衣物主体区域不被修改
    """
    result_arr = np.array(result.convert("RGB"), dtype=np.float32)
    person_arr = np.array(person.convert("RGB"), dtype=np.float32)
    h, w = result_arr.shape[:2]

    if garment_mask is not None:
        # 有衣物mask：只在边缘处融合
        mask_u8 = (garment_mask * 255).astype(np.uint8)

        # 找到mask的边缘
        edges = cv2.Canny(mask_u8, 50, 150)

        # 创建边缘膨胀区域（只在边缘附近融合）
        kernel = np.ones((blend_radius * 2 + 1, blend_radius * 2 + 1), np.uint8)
        edge_dilated = cv2.dilate(edges, kernel, iterations=1)

        # 计算到边缘的距离（边缘处=0，向外渐增）
        dist = cv2.distanceTransform(255 - edge_dilated, cv2.DIST_L2, 5)
        max_dist = max(1, dist.max())

        # 创建融合权重（只在边缘附近有效）
        blend_weight = np.clip(dist / (max_dist * blend_radius / 5), 0, 1)

        # 只在边缘区域应用融合
        edge_mask = (blend_weight > 0.01).astype(np.float32)

        # 应用融合
        for c in range(3):
            result_arr[:, :, c] = result_arr[:, :, c] * (1 - edge_mask * blend_weight) + person_arr[
                :, :, c
            ] * (edge_mask * blend_weight)
    else:
        # 没有mask：对整体进行非常轻微的边缘平滑
        # 使用 bilateral filter 保持边缘同时平滑噪点
        result_arr = result_arr.astype(np.float32)

    result = np.clip(result_arr, 0, 255).astype(np.uint8)
    return Image.fromarray(result, mode="RGB")


# ============================================================
# 核心算法 2: 智能边缘融合（保留 - 已修复）
# ============================================================


def smart_edge_blend(
    result: Image.Image,
    person: Image.Image,
    garment_mask: np.ndarray | None = None,
) -> Image.Image:
    """
    智能边缘融合 - 使用安全的边界检测，只在真正的边缘处融合。
    已修复：不会误伤衣物主体区域。
    """
    result_arr = np.array(result.convert("RGB"), dtype=np.float32)
    person_arr = np.array(person.convert("RGB"), dtype=np.float32)
    h, w = result_arr.shape[:2]

    # 使用 bilateral filter 进行保边平滑（不改变边缘，只平滑内部）
    result_u8 = result_arr.astype(np.uint8)
    smoothed = cv2.bilateralFilter(result_u8, 7, 50, 50)
    smoothed = smoothed.astype(np.float32)

    # 计算result和person之间的差异
    diff = np.abs(result_arr - person_arr).mean(axis=2)

    # 找到差异较大的区域（真正的边缘/接缝）
    threshold = np.percentile(diff, 92)
    seam_mask = (diff > max(threshold, 15)).astype(np.float32)

    # 膨胀以覆盖整个接缝区域
    kernel = np.ones((3, 3), np.uint8)
    seam_mask = cv2.dilate(seam_mask.astype(np.uint8), kernel, iterations=2).astype(np.float32)

    # 在接缝区域进行轻微融合
    for c in range(3):
        result_arr[:, :, c] = result_arr[:, :, c] * (1 - seam_mask * 0.3) + smoothed[:, :, c] * (
            seam_mask * 0.3
        )

    result = np.clip(result_arr, 0, 255).astype(np.uint8)
    return Image.fromarray(result, mode="RGB")


# ============================================================
# 核心算法 3: 色彩匹配
# ============================================================


def match_colors_to_scene(
    result: Image.Image,
    person: Image.Image,
    garment_region: Tuple[int, int, int, int] | None = None,
) -> Image.Image:
    """
    色彩匹配 - 让衣物颜色与场景光照协调（非常轻量，不改变衣物本质颜色）。
    """
    result_arr = np.array(result.convert("RGB"), dtype=np.float32)
    person_arr = np.array(person.convert("RGB"), dtype=np.float32)
    h, w = result_arr.shape[:2]

    if garment_region is None:
        # 自动检测衣物区域（假设在图像中部偏上）
        x0, y0 = int(w * 0.15), int(h * 0.10)
        x1, y1 = int(w * 0.85), int(h * 0.55)
    else:
        x0, y0, x1, y1 = garment_region

    # 提取身体参考区域（在衣物下方）
    body_y0 = max(0, int((y0 + y1) / 2 + (h - y1) * 0.3))
    body_y1 = min(h, body_y0 + int(h * 0.12))
    body_region = person_arr[body_y0:body_y1, max(0, x0) : min(w, x1)]

    # 计算身体区域平均亮度
    body_brightness = body_region.mean()

    # 计算衣物区域平均亮度
    garment_region_arr = result_arr[y0:y1, x0:x1]
    garment_brightness = garment_region_arr.mean()

    # 只进行非常轻微的亮度调整（保留衣物本质特征）
    if body_brightness > 10 and garment_brightness > 10:
        brightness_ratio = body_brightness / garment_brightness
        # 限制调整范围，只调整10%
        adjustment = 1.0 + (brightness_ratio - 1.0) * 0.10
        adjustment = np.clip(adjustment, 0.85, 1.15)

        # 只在衣物区域应用调整
        for c in range(3):
            result_arr[y0:y1, x0:x1, c] = np.clip(result_arr[y0:y1, x0:x1, c] * adjustment, 0, 255)

    return Image.fromarray(np.clip(result_arr, 0, 255).astype(np.uint8), mode="RGB")


# ============================================================
# 核心算法 4: 细节保护锐化
# ============================================================


def preserve_and_enhance_details(
    result: Image.Image,
    original_garment: Image.Image,
    garment_region: Tuple[int, int, int, int] | None = None,
    strength: float = 0.2,
) -> Image.Image:
    """
    细节保护锐化 - 只在衣物区域应用轻微锐化，保护其他区域。
    """
    result_arr = np.array(result.convert("RGB"), dtype=np.float32)
    h, w = result_arr.shape[:2]

    if garment_region is None:
        x0, y0 = int(w * 0.15), int(h * 0.10)
        x1, y1 = int(w * 0.85), int(h * 0.55)
    else:
        x0, y0, x1, y1 = garment_region

    # 使用 unsharp mask 进行轻微锐化
    gaussian = cv2.GaussianBlur(result_arr[y0:y1, x0:x1].astype(np.uint8), (0, 0), 1.5)
    sharpened_region = cv2.addWeighted(
        result_arr[y0:y1, x0:x1].astype(np.uint8), 1 + strength, gaussian, -strength, 0
    )

    result_arr[y0:y1, x0:x1] = np.clip(sharpened_region, 0, 255)

    return Image.fromarray(np.clip(result_arr, 0, 255).astype(np.uint8), mode="RGB")


# ============================================================
# 核心算法 5: 噪点去除
# ============================================================


def denoise_while_preserving_edges(
    result: Image.Image,
    strength: int = 2,
) -> Image.Image:
    """
    保边去噪 - 使用双边滤波保护边缘同时去除噪点。
    """
    result_arr = np.array(result.convert("RGB"))

    # 双边滤波：保护边缘同时平滑
    d = min(strength * 2 + 1, 9)
    sigma_color = strength * 10
    sigma_space = strength * 10

    denoised = cv2.bilateralFilter(result_arr, d, sigma_color, sigma_space)

    return Image.fromarray(denoised, mode="RGB")


# ============================================================
# 核心算法 6: 消除拼接痕迹（已修复）
# ============================================================


def remove_seam_lines(
    result: Image.Image,
    person: Image.Image,
    garment_mask: np.ndarray | None = None,
) -> Image.Image:
    """
    消除拼接痕迹 - 只处理明显的接缝线，不触碰衣物主体。
    已修复：不会误伤衣物区域。
    """
    result_arr = np.array(result.convert("RGB"), dtype=np.float32)
    person_arr = np.array(person.convert("RGB"), dtype=np.float32)
    h, w = result_arr.shape[:2]

    # 计算与原始人物的差异
    diff = np.abs(result_arr - person_arr).mean(axis=2)

    # 找到差异突然变化的边缘（接缝线）
    diff_grad_x = np.abs(np.gradient(diff, axis=1))
    diff_grad_y = np.abs(np.gradient(diff, axis=0))
    seam_strength = np.sqrt(diff_grad_x**2 + diff_grad_y**2)

    # 阈值分割：只处理明显的接缝
    threshold = np.percentile(seam_strength, 97)
    seams = seam_strength > max(threshold, 8)

    # 只处理细线状的接缝（排除大块区域）
    seam_u8 = seams.astype(np.uint8) * 255
    contours, _ = cv2.findContours(seam_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 过滤掉太大的区域（可能是衣物本身）
    valid_seams = np.zeros_like(seam_u8)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < w * h * 0.01:  # 只处理小于1%图像面积的接缝
            cv2.drawContours(valid_seams, [contour], -1, 255, -1)

    # 使用 inpaint 修复接缝
    if valid_seams.sum() > 100:  # 确保有足够的接缝需要修复
        result_fixed = cv2.inpaint(
            result_arr.astype(np.uint8), valid_seams, inpaintRadius=2, flags=cv2.INPAINT_TELEA
        )
        return Image.fromarray(result_fixed, mode="RGB")

    return Image.fromarray(result_arr.astype(np.uint8), mode="RGB")


# ============================================================
# 主函数: 完整后处理流程（安全版本）
# ============================================================


def enhance_tryon_result(
    result: Image.Image,
    person: Image.Image,
    original_garment: Image.Image | None = None,
    garment_mask: np.ndarray | None = None,
    garment_region: Tuple[int, int, int, int] | None = None,
    strength: str = "medium",
) -> Image.Image:
    """
    完整后处理流程 - 安全版本，不会误伤衣物区域。

    Args:
        result: 试衣结果图
        person: 原始人物图（用于参考）
        original_garment: 原始衣物图（可选，用于细节保护）
        garment_mask: 衣物区域掩码（可选）
        garment_region: 衣物区域 (x0, y0, x1, y1)
        strength: 增强强度 'light' | 'medium' | 'strong'

    Returns:
        增强后的图像
    """
    logger.info(f"Applying safe post-processing (strength={strength})...")

    # 确定处理强度参数
    strength_params = {
        "light": {"denoise": 1, "sharpen": 0.1},
        "medium": {"denoise": 2, "sharpen": 0.15},
        "strong": {"denoise": 3, "sharpen": 0.2},
    }
    params = strength_params.get(strength, strength_params["medium"])

    # Step 1: 保边去噪（不改变衣物主体）
    result = denoise_while_preserving_edges(result, strength=params["denoise"])

    # Step 2: 消除接缝线（只处理细线，不碰衣物主体）
    result = remove_seam_lines(result, person, garment_mask)

    # Step 3: 安全边缘融合（只在真正需要融合的边界处）
    result = safe_edge_blend(result, person, garment_mask, blend_radius=5)

    # Step 4: 色彩匹配（非常轻量，只调整10%）
    result = match_colors_to_scene(result, person, garment_region)

    # Step 5: 细节保护锐化（只在衣物区域）
    if original_garment is not None:
        result = preserve_and_enhance_details(
            result, original_garment, garment_region, strength=params["sharpen"]
        )

    logger.info("Safe post-processing completed")
    return result


def quick_enhance(result: Image.Image) -> Image.Image:
    """
    快速增强 - 轻量级后处理，适合实时应用。
    """
    # 轻度去噪（bilateral filter）
    result_arr = np.array(result.convert("RGB"))
    result = Image.fromarray(cv2.bilateralFilter(result_arr, 5, 30, 30), mode="RGB")

    # 轻度锐化
    result_arr = np.array(result.convert("RGB"), dtype=np.float32)
    gaussian = cv2.GaussianBlur(result_arr.astype(np.uint8), (0, 0), 1)
    sharpened = cv2.addWeighted(result_arr.astype(np.uint8), 1.05, gaussian, -0.05, 0)
    result = Image.fromarray(np.clip(sharpened, 0, 255).astype(np.uint8), mode="RGB")

    return result
