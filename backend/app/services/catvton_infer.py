"""CatVTON Inference — 修正版（v2）。

关键修正：
1. 删除所有颜色迁移逻辑（_transfer_color_to_region 已移除）
2. 所有输入统一 normalize 到 [-1, 1]
3. garment 输入使用 preprocess_garment() 去背景 + bbox 居中
4. 使用 polygon mask（来自 body_mask.py）替代矩形 mask
5. num_inference_steps=40, guidance_scale=7.5

架构：
- polygon mask 生成：调用 body_mask.py 的 polygon 函数
- garment 预处理：调用 garment_preprocess.py 的 preprocess_garment()
- CatVTON 推理：调用 catvton_engine.py 的 CatVTONEngine
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ─── 默认推理参数 ───────────────────────────────────────────────────────────────

DEFAULT_STEPS = 40
DEFAULT_GUIDANCE = 7.5


# ─── 输入预处理 ────────────────────────────────────────────────────────────────


def normalize_to_tensor(img: np.ndarray) -> np.ndarray:
    """将 uint8 [0,255] 图像 normalize 到 float32 [-1, 1]。

    CatVTON VAE 期望输入范围为 [-1, 1]。
    可供外部工具或测试使用。
    """
    return (img.astype(np.float32) / 127.5) - 1.0


# ─── Polygon Mask 生成 ──────────────────────────────────────────────────────────


def create_polygon_body_mask(
    person_img: Image.Image,
    cloth_type: str,
    feather_radius: int = 0,
) -> Image.Image:
    """使用 polygon fillPoly 生成贴合人体轮廓的 body mask。

    关键修正（v2）：
    - 删除矩形 mask，改用 polygon fillPoly
    - 使用 mediapipe 关键点（肩膀+臀部）构建 polygon 顶点
    - GaussianBlur 平滑边缘（feather_radius > 0 时）

    Args:
        person_img: 人物图（PIL RGB）
        cloth_type: "upper" | "lower" | "overall"
        feather_radius: 边缘羽化半径（0=禁用）

    Returns:
        PIL Image (mode="L")，255=衣物区域，0=保留区域
    """
    from app.services.body_mask import (
        create_lower_body_polygon_mask,
        create_upper_body_polygon_mask,
    )
    from app.services.tryon_v2.pose_utils import detect_pose_keypoints

    pw, ph = person_img.size
    keypoints = detect_pose_keypoints(person_img)

    if keypoints:
        if cloth_type in {"upper", "outfit"}:
            mask_np = create_upper_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
        elif cloth_type in {"lower", "skirt"}:
            mask_np = create_lower_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
        else:
            mask_np = create_upper_body_polygon_mask(keypoints, pw, ph, feather_radius=0)
    else:
        # 无关键点 fallback
        from app.services.body_mask import _lower_body_fallback, _upper_body_fallback

        if cloth_type in {"upper", "outfit"}:
            mask_np = _upper_body_fallback(pw, ph, feather_radius=0)
        elif cloth_type in {"lower", "skirt"}:
            mask_np = _lower_body_fallback(pw, ph, feather_radius=0)
        else:
            mask_np = _upper_body_fallback(pw, ph, feather_radius=0)

    if feather_radius > 0:
        import cv2

        mask_np = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        mask_np = np.clip(mask_np, 0, 255).astype(np.uint8)

    return Image.fromarray(mask_np, mode="L")


# ─── 推理入口 ────────────────────────────────────────────────────────────────


def infer_catvton(
    person_img: Image.Image,
    garment_img: Image.Image,
    cloth_type: str = "upper",
    num_inference_steps: int = DEFAULT_STEPS,
    guidance_scale: float = DEFAULT_GUIDANCE,
    seed: Optional[int] = None,
    mask_image: Optional[Image.Image] = None,
    target_size: tuple[int, int] = (768, 1024),
    catvton_path: Optional[str] = None,
) -> Image.Image:
    """CatVTON 虚拟试穿推理（修正版 v2）。

    输入修正：
    1. mask → polygon fillPoly（来自 body_mask.py）
    2. 删除颜色迁移（_transfer_color_to_region）
    3. num_inference_steps=40, guidance_scale=7.5
    4. garment 预处理由 engine.infer() 内部完成（避免 double preprocess）

    Args:
        person_img: 人物原图（PIL RGB）
        garment_img: 衣服产品图（PIL RGB）
        cloth_type: "upper" | "lower" | "overall"
        num_inference_steps: 扩散步数（默认 40）
        guidance_scale: CFG 引导强度（默认 7.5）
        seed: 随机种子（None=随机）
        mask_image: 可选手动提供的 mask（None=自动 polygon mask）
        target_size: 目标分辨率 (width, height)
        catvton_path: CatVTON 仓库路径

    Returns:
        试穿结果图（PIL RGB）
    """
    logger.info(
        f"[CatVTON-v2] infer: cloth_type={cloth_type}, "
        f"steps={num_inference_steps}, guidance={guidance_scale}, "
        f"seed={seed}, size={target_size}"
    )

    # Step 1: 生成 polygon body mask（替代矩形 mask）
    if mask_image is None:
        mask_image = create_polygon_body_mask(person_img, cloth_type, feather_radius=0)

    # Step 2: CatVTON 推理（engine 内部完成 garment 预处理 + 计时）
    # 注意：engine.infer() 内部会调用 preprocess_garment()，此处传原始 garment_img
    # 避免重复预处理（double preprocess 会导致 rembg 在已处理图上再次运行）
    engine = _get_engine(catvton_path, target_size)
    result = engine.infer(
        person_image=person_img,
        garment_image=garment_img,
        cloth_type=cloth_type,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        seed=seed,
        mask_image=mask_image,
    )

    logger.info("[CatVTON-v2] inference completed")
    return result


# ─── Engine 单例 ──────────────────────────────────────────────────────────────


_engine: "CatVTONEngine | None" = None  # noqa: F821


def _get_engine(
    catvton_path: Optional[str] = None,
    target_size: tuple[int, int] = (768, 1024),
):
    """获取或创建 CatVTONEngine 单例。"""
    global _engine

    if _engine is None:
        from vton_inference_service.catvton_engine import CatVTONEngine

        logger.info(f"Creating CatVTONEngine singleton (size={target_size})")
        _engine = CatVTONEngine(
            catvton_path=catvton_path,
            width=target_size[0],
            height=target_size[1],
            mixed_precision="bf16",
            repaint=True,
        )

    return _engine


def reset_engine():
    """重置 engine 单例（用于更换模型路径时）。"""
    global _engine
    _engine = None
    logger.info("CatVTON engine singleton reset")
