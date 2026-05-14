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


def _detect_face_box_seam(
    result: Image.Image,
    person_image: Image.Image,
) -> tuple[int, int, int, int] | None:
    """Detect face bounding box for seam protection.

    Strategy:
      1. Haar cascade on ORIGINAL person image (clear, reliable).
         Scale detected bbox to result coordinates proportionally.
      2. Fallback: fixed ratio estimate (upper 15% of image, centered 30%-70%).

    Returns (x, y, w, h) in result pixel coordinates, or None if undetected.
    """
    try:
        from app.services.cascade_manager import load_cascade

        cascade = load_cascade("haarcascade_frontalface_default.xml")
        if cascade is None or cascade.empty():
            logger.warning(
                "remove_seam_lines: Haar cascade unavailable, " "face protection disabled"
            )
            return None

        # ── Priority 1: Detect on ORIGINAL person image ─────────────────────
        orig_arr = np.asarray(person_image.convert("RGB"))
        orig_h, orig_w = orig_arr.shape[:2]

        if orig_h >= 64 and orig_w >= 64:
            orig_gray = cv2.cvtColor(orig_arr, cv2.COLOR_RGB2GRAY)
            orig_gray_eq = cv2.equalizeHist(orig_gray)

            orig_faces = cascade.detectMultiScale(
                orig_gray_eq,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(int(orig_w * 0.06), int(orig_h * 0.06)),
                maxSize=(int(orig_w * 0.60), int(orig_h * 0.60)),
            )

            if orig_faces is not None and len(orig_faces) > 0:
                orig_face_list = sorted(orig_faces, key=lambda f: f[2] * f[3], reverse=True)
                ofx, ofy, ofw, ofh = [int(v) for v in orig_face_list[0]]

                # Scale from original person coords → result coords
                res_w, res_h = result.size
                scale_x = res_w / float(orig_w)
                scale_y = res_h / float(orig_h)
                fx = _clamp_int(int(ofx * scale_x), 0, res_w - 1)
                fy = _clamp_int(int(ofy * scale_y), 0, res_h - 1)
                fw = _clamp_int(int(ofw * scale_x), 4, res_w)
                fh = _clamp_int(int(ofh * scale_y), 4, res_h)

                logger.info(
                    "remove_seam_lines: face detected on original person "
                    "([%d,%d,%d,%d] at %dx%d) -> scaled to result([%d,%d,%d,%d] at %dx%d)",
                    ofx,
                    ofy,
                    ofw,
                    ofh,
                    orig_w,
                    orig_h,
                    fx,
                    fy,
                    fw,
                    fh,
                    res_w,
                    res_h,
                )
                return (fx, fy, fw, fh)

    except Exception as e:
        logger.debug("remove_seam_lines: face detection failed (%s)", e)

    return None


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
    person_image: Image.Image | None = None,
) -> Image.Image:
    """
    消除拼接痕迹 - 只处理明显的接缝线，不触碰衣物主体和面部。
    已修复：不会误伤衣物区域和面部区域。
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

    # ── 面部保护：将脸部区域从 valid_seams 中剔除 ─────────────────────────
    # CatVTON 扩散模型生成的脸部与原图有细微差异，会被误判为"接缝"，
    # inpaint 填充后导致脸部模糊。将脸部区域从 mask 中剔除以保护。
    _face_source = person_image or person
    face_box = _detect_face_box_seam(result, _face_source)
    if face_box is not None:
        fx, fy, fw, fh = face_box
        # 向下延伸 30% 覆盖下巴→颈部过渡
        extend = max(2, int(fh * 0.30))
        protect_y0 = max(0, fy)
        protect_y1 = min(h, fy + fh + extend)
        protect_x0 = max(0, fx - int(fw * 0.10))
        protect_x1 = min(w, fx + fw + int(fw * 0.10))
        valid_seams[protect_y0:protect_y1, protect_x0:protect_x1] = 0
        logger.info(
            "remove_seam_lines: face protected [%d,%d,%d,%d]",
            protect_x0,
            protect_y0,
            protect_x1,
            protect_y1,
        )

    # 使用 inpaint 修复接缝
    if valid_seams.sum() > 100:  # 确保有足够的接缝需要修复
        result_fixed = cv2.inpaint(
            result_arr.astype(np.uint8),
            valid_seams,
            inpaintRadius=2,
            flags=cv2.INPAINT_TELEA,
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
    is_white_garment: bool = False,
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
        is_white_garment: 是否为白色/低饱和度衣物（跳过后处理以避免污染）

    Returns:
        增强后的图像
    """
    # 白色/低饱和度衣物跳过后处理，避免褐色阴影、边缘污染、fidelity 误采样
    if is_white_garment:
        logger.info(
            "White/low-saturation garment detected (is_white_garment=True) — "
            "skipping post-processing to preserve CatVTON's clean white output"
        )
        return result

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

    # Step 2: 消除接缝线（只处理细线，不碰衣物主体和面部）
    result = remove_seam_lines(result, person, garment_mask, person_image=person)

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


def catvton_safe_enhance(
    result: Image.Image,
    person: Image.Image,
    garment_mask: np.ndarray | None = None,
) -> Image.Image:
    """
    CatVTON 安全后处理 — 只做去噪 + 接缝消除 + 轻度锐化，
    不与原图混合（避免贴纸/幽灵效果）。
    """
    logger.info("CatVTON safe enhance: denoise + seam removal + sharpen")

    # Step 1: 保边去噪
    result = denoise_while_preserving_edges(result, strength=1)

    # Step 2: 消除接缝线（传入 person_image 用于面部保护）
    result = remove_seam_lines(result, person, garment_mask, person_image=person)

    # Step 3: 保图案的细节增强（USM + 频率分离）
    result = enhance_pattern_details(result)

    logger.info("CatVTON safe enhance completed")
    return result


def enhance_pattern_details(result: Image.Image, strength: float = 1.2) -> Image.Image:
    """
    频率分离增强 - 在保护高频图案细节（印花/格子/条纹）的前提下
    恢复因 VAE 编码误差而模糊的中频结构（衣物轮廓、褶皱）。

    策略：
    1. 频率分离：高频层 = 原图 - 高斯模糊(原图)
    2. 中频层保留，增强褶皱和轮廓清晰度（unsharp mask）
    3. 高频层叠加回去，保护印花/格子/条纹不被抹平
    4. 对饱和度高的像素（图案区）降低增强强度，避免颜色失真

    Args:
        result: CatVTON 试穿结果
        strength: 锐化强度 (1.0=轻度, 1.5=中度, 2.0=强)

    Returns:
        细节增强后的图像
    """
    result_arr = np.array(result.convert("RGB"), dtype=np.float32)

    # ── Step 1: 频率分离 ───────────────────────────────────────────
    # 高斯模糊层（低频）：包含大尺度光影、颜色分布
    blur_k = 7
    low_freq = cv2.GaussianBlur(result_arr.astype(np.uint8), (blur_k, blur_k), 0)
    low_freq = low_freq.astype(np.float32)

    # 高频层 = 原图 - 低频层（保留印花/格子/条纹）
    high_freq = result_arr - low_freq

    # ── Step 2: 中频增强（unsharp mask）────────────────────────────
    # 对低频层应用 unsharp mask，增强褶皱和结构清晰度
    median_k = 5
    blurred = cv2.medianBlur(result_arr.astype(np.uint8), median_k)
    blurred_f = blurred.astype(np.float32)

    # 增强量：模糊越大的地方增强越多（补偿 VAE 模糊）
    diff_from_median = np.abs(result_arr - blurred_f).mean(axis=2, keepdims=True)
    enhance_mask = np.clip(diff_from_median / 40.0, 0, 1)

    # unsharp mask: result + strength * (result - blurred)
    amount = strength - 1.0
    sharpened_low = result_arr + enhance_mask * (result_arr - blurred_f) * amount

    # ── Step 3: 叠加高频层（保护图案细节）────────────────────────
    # 饱和度检测：图案区域（高饱和度）降低锐化，避免颜色失真
    hsv = cv2.cvtColor(result_arr.astype(np.uint8), cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1].astype(np.float32) / 255.0
    value = hsv[:, :, 2].astype(np.float32) / 255.0

    # 高亮度且高饱和度 = 图案区域，降低混合强度
    pattern_mask = saturation * (1.0 - np.abs(value - 0.6) * 2)
    pattern_mask = np.clip(pattern_mask, 0, 1)

    # 图案区域保留更多高频（叠加回 100% 高频），非图案区使用增强后的低频
    # pattern_mask 是 (H,W)，high_freq 是 (H,W,3)，需要 [np.newaxis] 对齐
    enhanced = sharpened_low + high_freq * (1.0 - pattern_mask[..., np.newaxis] * 0.4)

    result_final = np.clip(enhanced, 0, 255).astype(np.uint8)
    return Image.fromarray(result_final, mode="RGB")


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
