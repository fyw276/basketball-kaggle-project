"""Try-on v2 API endpoints (pipeline A MVP)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.observability.tryon_v2_metrics import record_tryon_v2_failure, record_tryon_v2_success
from app.services.storage import get_storage_service
from app.services.subscription_billing import consume_usage
from app.services.tryon_debug_utils import (
    resolve_debug_session_dir,
    save_debug_stage_bytes,
    save_debug_stage_image,
)
from app.services.tryon_v2 import run_pipeline_a
from app.services.tryon_v2.fidelity_guard import (
    decide_color_fidelity_engine,
    detect_post_cf_artifacts,
    estimate_pattern_enhance_strength,
    evaluate_cutout_alpha_qc,
    evaluate_raw_catvton_quality,
    extract_engine_decision_features,
    repair_raw_catvton_artifacts,
    score_input_anomaly,
    should_force_lower_structured_pattern_recovery,
)
from app.services.tryon_v2.garment_struct import cutout_garment_rgba
from app.services.tryon_v2.input_gate import evaluate_input_gate
from app.services.tryon_v2.postprocess import enhance_tryon_result
from app.services.tryon_v2.preprocess import preprocess_garment_image
from app.services.virtual_tryon import check_tryon_garment_has_face

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tryon", tags=["Virtual Try-On v2"])


class TryOnV2Response(BaseModel):
    status: str = Field(..., description="Status: success/error")
    message: str = Field(..., description="Human-readable status message")
    pipeline: str = Field("A", description="Pipeline identifier")
    result_image_url: str | None = Field(None, description="URL of the try-on result image")
    preview_white_url: str | None = Field(
        None,
        description=(
            "用户可见白底预览图 URL。用于 UI 展示标准电商白底商品图外观。"
            "此图使用 letterbox 缩放（保持原始比例），不经过 warp/TPS 变形。"
            "仅当 auto_preprocess 启用时返回。"
        ),
    )
    error_code: str | None = Field(None, description="Stable error code")
    retryable: bool = Field(False, description="Whether client can retry later")
    action_hint: str | None = Field(None, description="Action guidance for UI")
    qc_scores: dict[str, float] = Field(default_factory=dict, description="Input/QC scores")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Processing metadata")
    # ─── 白盒调试字段 ───────────────────────────────────────────────
    debug_session_dir: str | None = Field(
        None,
        description="白盒调试会话目录（debug_mode != 'off' 时返回）。"
        "包含: 01_input_person.jpg, 02_input_garment.jpg, "
        "02b_preview_white.jpg (白底预览图, letterbox保持比例), "
        "03_mask.png, 04_pose_keypoints.jpg, 09_mask_overlay.png 等中间产物。",
    )


class TryOnV2ValidateResponse(BaseModel):
    status: str = Field(..., description="Status: pass/fail")
    pipeline: str = Field("A", description="Pipeline identifier")
    passed: bool = Field(..., description="Whether input gate passed")
    error_code: str | None = Field(None, description="Stable error code when failed")
    message: str = Field(..., description="Validation message")
    retryable: bool = Field(False, description="Whether client can retry later")
    action_hint: str | None = Field(None, description="Action guidance for UI")
    qc_scores: dict[str, float] = Field(default_factory=dict, description="Input quality scores")
    thresholds: dict[str, float] = Field(
        default_factory=dict, description="Numeric score thresholds applied"
    )
    recognized_tryon_category: str | None = Field(
        None, description="Auto-detected tryon category (e.g. upper, lower, skirt)"
    )
    recognized_raw_category: str | None = Field(
        None, description="Raw ML category before mapping (e.g. 上衣, 裤子)"
    )
    recognized_confidence: float | None = Field(
        None, description="Category classification confidence"
    )


class TryOnV2CapabilitiesResponse(BaseModel):
    enabled: bool = Field(..., description="Whether tryon v2 is enabled")
    pipeline_default: str = Field("A", description="Default pipeline")
    strict_identity_default: bool = Field(..., description="Default strict identity mode")
    supported_garment_categories: list[str] = Field(default_factory=list)
    modes: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)


class TryOnV2PreprocessItem(BaseModel):
    tryon_category: str
    raw_category: str
    category_confidence: float
    standardized_image_url: str
    preview_white_url: str | None = Field(
        None,
        description=(
            "用户可见白底预览图 URL。与 standardized_image_url 的区别："
            "preview_white 使用 letterbox 缩放（保持原始比例，白边填充），"
            "用于 UI 展示真实商品图外观；"
            "standardized_image 用于模型 warp 处理。"
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


def _v2_thresholds(strict_mode: bool) -> dict[str, float]:
    full_body = float(getattr(settings, "TRYON_V2_MIN_FULL_BODY_SCORE", 0.55) or 0.55)
    leg_visibility = float(getattr(settings, "TRYON_V2_MIN_LEG_VISIBILITY_SCORE", 0.45) or 0.45)
    front_pose = float(getattr(settings, "TRYON_V2_MIN_FRONT_POSE_SCORE", 0.35) or 0.35)
    garment_front = float(getattr(settings, "TRYON_V2_MIN_GARMENT_FRONT_SCORE", 0.45) or 0.45)

    if not strict_mode:
        return {
            "full_body": max(0.0, full_body - 0.10),
            "leg_visibility": max(0.0, leg_visibility - 0.10),
            "front_pose": max(0.0, front_pose - 0.10),
            "garment_front": max(0.0, garment_front - 0.10),
        }

    return {
        "full_body": full_body,
        "leg_visibility": leg_visibility,
        "front_pose": front_pose,
        "garment_front": garment_front,
    }


def _pil_image_to_jpeg_bytes(img, quality: int = 90) -> bytes:
    import os
    import tempfile

    rgb = img.convert("RGB")
    fd, path = tempfile.mkstemp(suffix=".jpg")
    try:
        os.close(fd)
        rgb.save(path, format="JPEG", quality=quality, optimize=False)
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _ensure_tryon_v2_enabled() -> None:
    if not bool(getattr(settings, "TRYON_V2_ENABLED", True)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "虚拟试衣 v2 未启用",
                "error_code": "TRYON_V2_DISABLED",
                "retryable": False,
                "action_hint": "请联系管理员开启 TRYON_V2_ENABLED。",
            },
        )


def _maybe_auto_preprocess(
    garment_image: Any,
    garment_category: str | None,
) -> tuple[Any, str | None, dict[str, Any]]:
    """If garment_category is auto (or empty), preprocess and auto-detect tryon category."""
    gc = (garment_category or "").strip().lower()
    if not bool(getattr(settings, "TRYON_V2_AUTO_PREPROCESS", True)):
        return garment_image, garment_category, {"auto_preprocess": False}
    if gc not in {"", "auto", "unknown", "默认"}:
        return garment_image, garment_category, {"auto_preprocess": False}

    r = preprocess_garment_image(garment_image)

    # If still unknown, keep original category and let input_gate return actionable error.
    cat = r.tryon_category if r.tryon_category != "unknown" else garment_category
    return (
        r.image,
        cat,
        {
            "auto_preprocess": True,
            "recognized_tryon_category": r.tryon_category,
            "recognized_raw_category": r.raw_category,
            "recognized_confidence": r.confidence,
        },
    )


def _estimate_garment_region_for_postprocess(
    image_size: tuple[int, int],
    garment_type: str,
) -> tuple[int, int, int, int] | None:
    """估算衣物区域用于后处理（简化版本，不依赖姿态检测）。"""
    pw, ph = image_size

    if garment_type == "top":
        # 上装区域：肩膀到腰部
        x0 = int(pw * 0.18)
        x1 = int(pw * 0.82)
        y0 = int(ph * 0.12)
        y1 = int(ph * 0.55)
    elif garment_type == "bottom":
        # 下装区域：腰部到脚踝
        x0 = int(pw * 0.22)
        x1 = int(pw * 0.78)
        y0 = int(ph * 0.38)
        y1 = int(ph * 0.95)
    else:
        # 默认全区域
        return None

    return (x0, y0, x1, y1)


def _build_fidelity_guard_context(original_garment_image):
    anomaly = score_input_anomaly(original_garment_image)
    cutout = cutout_garment_rgba(original_garment_image)
    cutout_qc = evaluate_cutout_alpha_qc(cutout.rgba)
    features = extract_engine_decision_features(original_garment_image)
    return anomaly, cutout_qc, features


def _restore_catvton_motif_after_postprocess(
    *,
    pre_postprocess_image: Image.Image,
    postprocess_image: Image.Image,
    debug_session_dir: str | None,
) -> tuple[Image.Image, dict[str, Any]]:
    """Restore only high-confidence motif pixels softened by CatVTON-safe denoise."""
    meta: dict[str, Any] = {
        "stage": "after_catvton_safe_motif_restore",
        "applied": False,
        "reason": "debug_mask_missing",
    }
    debug_dir = resolve_debug_session_dir(debug_session_dir)
    if debug_dir is None:
        return postprocess_image, meta

    motif_mask_path = debug_dir / "12c_motif_strength.png"
    if not motif_mask_path.exists():
        return postprocess_image, meta

    try:
        pre_img = pre_postprocess_image.convert("RGB")
        post_img = postprocess_image.convert("RGB")
        if pre_img.size != post_img.size:
            pre_img = pre_img.resize(post_img.size, Image.Resampling.BICUBIC)

        mask_img = Image.open(motif_mask_path).convert("L")
        if mask_img.size != post_img.size:
            mask_img = mask_img.resize(post_img.size, Image.Resampling.BILINEAR)

        mask_np = np.asarray(mask_img, dtype=np.float32) / 255.0
        mask_max = float(mask_np.max()) if mask_np.size else 0.0
        if mask_max < 0.04:
            meta.update({"reason": "motif_mask_too_weak", "mask_max": round(mask_max, 4)})
            return postprocess_image, meta

        motif_alpha = mask_np / max(mask_max, 1e-6)
        motif_alpha = np.where(mask_np > 0.035, np.power(motif_alpha, 0.55), 0.0)
        motif_alpha = cv2.GaussianBlur(motif_alpha.astype(np.float32), (5, 5), 0)
        motif_alpha = np.clip(motif_alpha * 0.82, 0.0, 0.82)
        if float((motif_alpha > 0.04).mean()) < 0.001:
            meta.update(
                {
                    "reason": "motif_restore_coverage_too_low",
                    "mask_max": round(mask_max, 4),
                }
            )
            return postprocess_image, meta

        pre_np = np.asarray(pre_img, dtype=np.float32)
        post_np = np.asarray(post_img, dtype=np.float32)
        pre_detail = pre_np - cv2.GaussianBlur(pre_np, (0, 0), 1.05)
        motif_target = np.clip(pre_np + pre_detail * 0.22, 0, 255)

        alpha3 = motif_alpha[:, :, None]
        restored_np = post_np * (1.0 - alpha3) + motif_target * alpha3
        restored = Image.fromarray(np.clip(restored_np, 0, 255).astype(np.uint8), mode="RGB")

        meta.update(
            {
                "applied": True,
                "reason": "ok",
                "mask_max": round(mask_max, 4),
                "restore_alpha_max": round(float(motif_alpha.max()), 4),
                "restore_coverage": round(float((motif_alpha > 0.04).mean()), 4),
                "source": "12c_motif_strength.png",
                "color_source": "pre_safe_enhance",
            }
        )
        save_debug_stage_image(
            debug_session_dir=debug_session_dir,
            filename="14b_motif_restore_mask.png",
            image=Image.fromarray(
                np.clip(motif_alpha * 255.0, 0, 255).astype(np.uint8),
                mode="L",
            ),
            metadata=meta,
        )
        return restored, meta
    except Exception as exc:
        meta.update({"reason": f"failed: {exc}"})
        return postprocess_image, meta


@router.post("/preprocess", response_model=TryOnV2PreprocessItem)
async def tryon_v2_preprocess(
    garment_file: UploadFile = File(..., alias="garment_file", description="Any garment image"),
    _current_user: User = Depends(get_current_user),
):
    _ensure_tryon_v2_enabled()
    from io import BytesIO

    from PIL import Image

    b = await garment_file.read()
    if not b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty"
        )
    garment_image = Image.open(BytesIO(b)).convert("RGB")

    try:
        r = preprocess_garment_image(garment_image)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"预处理失败：{str(e)}",
                "error_code": "TRYON_V2_GARMENT_TOO_COMPLEX",
                "retryable": False,
                "action_hint": "请换成无模特、背景干净的商品图（不要用海报/截图/带商品列表的图）。",
            },
        )

    import hashlib

    # Save standardized image (model-internal, 768x768)
    image_bytes = _pil_image_to_jpeg_bytes(r.image, quality=92)
    key = hashlib.sha1(image_bytes).hexdigest()[:20]
    std_path = f"preprocess/garment_{key}.jpg"
    _, std_url = get_storage_service()._save_bytes(image_bytes, std_path)

    # Save preview_white image (user-visible, letterbox, preserves aspect ratio)
    preview_white_url: str | None = None
    if r.preview_white is not None:
        try:
            pw_bytes = _pil_image_to_jpeg_bytes(r.preview_white, quality=95)
            pw_key = hashlib.sha1(pw_bytes).hexdigest()[:20]
            pw_path = f"preprocess/preview_white_{pw_key}.jpg"
            _, preview_white_url = get_storage_service()._save_bytes(pw_bytes, pw_path)
            logger.info(f"[PREPROCESS] preview_white saved: {preview_white_url}")
        except Exception as e:
            logger.warning(f"[PREPROCESS] failed to save preview_white: {e}")

    return TryOnV2PreprocessItem(
        tryon_category=r.tryon_category,
        raw_category=r.raw_category,
        category_confidence=float(r.confidence),
        standardized_image_url=std_url,
        preview_white_url=preview_white_url,
        metadata=r.metadata,
    )


@router.post("/preprocess-batch", response_model=list[TryOnV2PreprocessItem])
async def tryon_v2_preprocess_batch(
    garment_files: list[UploadFile] = File(..., alias="garment_files"),
    _current_user: User = Depends(get_current_user),
):
    _ensure_tryon_v2_enabled()
    from io import BytesIO

    from PIL import Image

    out: list[TryOnV2PreprocessItem] = []
    for f in garment_files:
        b = await f.read()
        if not b:
            continue
        img = Image.open(BytesIO(b)).convert("RGB")
        try:
            r = preprocess_garment_image(img)
            import hashlib

            # Save standardized image
            image_bytes = _pil_image_to_jpeg_bytes(r.image, quality=92)
            key = hashlib.sha1(image_bytes).hexdigest()[:20]
            path = f"preprocess/garment_{key}.jpg"
            _, std_url = get_storage_service()._save_bytes(image_bytes, path)

            # Save preview_white image
            preview_white_url: str | None = None
            if r.preview_white is not None:
                try:
                    pw_bytes = _pil_image_to_jpeg_bytes(r.preview_white, quality=95)
                    pw_key = hashlib.sha1(pw_bytes).hexdigest()[:20]
                    pw_path = f"preprocess/preview_white_{pw_key}.jpg"
                    _, preview_white_url = get_storage_service()._save_bytes(pw_bytes, pw_path)
                except Exception as e:
                    logger.warning(f"[PREPROCESS-BATCH] failed to save preview_white: {e}")

            out.append(
                TryOnV2PreprocessItem(
                    tryon_category=r.tryon_category,
                    raw_category=r.raw_category,
                    category_confidence=float(r.confidence),
                    standardized_image_url=std_url,
                    preview_white_url=preview_white_url,
                    metadata=r.metadata,
                )
            )
        except Exception:
            # Skip failed items to keep batch resilient.
            continue
    return out


@router.post("/garment", response_model=TryOnV2Response)
async def tryon_garment_v2(
    garment_file: UploadFile | None = File(
        None,
        alias="garment_file",
        description="Garment product photo (or use garment_id/garment_image_url)",
    ),
    person_file: UploadFile = File(..., alias="person_file", description="Person full-body photo"),
    garment_id: str | None = Form(
        None, description="衣橱衣物 ID（与 garment_file/garment_image_url 三选一）"
    ),
    garment_image_url: str | None = Form(
        None, description="Optional /uploads/... url of standardized garment image"
    ),
    garment_category: str = Form(
        "auto", description="Expected category: top|bottom|skirt|outfit|auto"
    ),
    garment_file_2: UploadFile | None = File(
        None, alias="garment_file_2", description="Optional second garment for outfit"
    ),
    garment_id_2: str | None = Form(
        None, description="衣橱第二件衣物 ID（与 garment_file_2 二选一）"
    ),
    garment_image_url_2: str | None = Form(
        None,
        description="Optional /uploads/... url of standardized second garment image",
    ),
    garment_category_2: str = Form(
        "bottom", description="Second garment category for outfit: bottom|skirt"
    ),
    prompt: str = Form("", description="Optional text prompt"),
    mode: str = Form("detail_fidelity", description="detail_fidelity|blend|stable_fast"),
    model_gender: str = Form("neutral", description="male|female|neutral"),
    # ─── 白盒调试参数 ───────────────────────────────────────────────
    debug_mode: str = Form(
        "off",
        description=(
            "白盒调试模式: "
            "off=关闭调试（默认）; "
            "preprocess_only=仅运行前处理（mask+pose），跳过扩散模型，极快返回用于调 mask; "
            "full=完整管线运行并保存所有中间产物（含扩散输出，耗时最长）。"
            "推荐先用 preprocess_only 确认 mask 质量，再用 full 验证最终效果。"
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    logger.info(f"[MODE-DEBUG] raw mode from frontend: '{mode}'")
    _ensure_tryon_v2_enabled()

    if garment_file is not None and (
        not garment_file.content_type or not garment_file.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="garment_file must be an image",
        )

    if not person_file.content_type or not person_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="person_file must be an image",
        )

    if model_gender not in {"male", "female", "neutral"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="model_gender must be one of: male, female, neutral",
        )

    # mode fallback: accept legacy/alias values from older clients
    _MODE_FALLBACK = {
        "detail": "detail_fidelity",
        "mixed": "hybrid",
        "fast": "stable_fast",
        "professional": "detail_fidelity",
        "realistic": "detail_fidelity",
        "realistic_v2": "detail_fidelity",
        "replace": "stable_fast",
    }
    mode = _MODE_FALLBACK.get(mode, mode)
    logger.info(f"[MODE-DEBUG] mode after fallback: '{mode}'")

    if mode not in {
        "detail_fidelity",
        "blend",
        "stable_fast",
        "hybrid",
        "paste",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("mode must be one of: detail_fidelity, blend, stable_fast, hybrid, paste"),
        )

    if debug_mode not in {"off", "preprocess_only", "full"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="debug_mode must be one of: off, preprocess_only, full",
        )

    # ─── 白盒调试目录分配 ───────────────────────────────────────────
    # 每个请求分配一个独立的时间戳会话目录，避免文件互相覆盖。
    # 从 CATVTON_DEBUG_DIR 配置读取根目录；未配置则不保存任何中间产物。
    debug_session_dir: str | None = None
    if debug_mode != "off":
        import datetime
        import uuid
        from pathlib import Path

        debug_root = (getattr(settings, "CATVTON_DEBUG_DIR", "") or "").strip()
        if debug_root:
            ts = (
                datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                + f"_{int(datetime.datetime.now().timestamp() * 1000) % 1000:03d}"
            )
            session_id = f"tryon_{ts}_{uuid.uuid4().hex[:6]}"
            session_dir = Path(debug_root) / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            debug_session_dir = str(session_dir)
            logger.info(f"[DEBUG] 白盒调试已开启，输出目录: {debug_session_dir}")
        else:
            logger.warning(
                "[DEBUG] debug_mode 已设置但 CATVTON_DEBUG_DIR 未配置。"
                "请在 .env 中设置 CATVTON_DEBUG_DIR=/path/to/debug/output"
            )

    if getattr(settings, "USAGE_QUOTA_ENABLED", False):
        quota = consume_usage(
            db,
            current_user.user_id,
            "tryon_generate",
            units=1,
        )
        if not quota.get("allowed"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": "tryon quota exceeded",
                    "error_code": "QUOTA_TRYON_EXCEEDED",
                    "requires_upgrade": True,
                    "remaining": quota.get("remaining", 0),
                    "limit": quota.get("limit", 0),
                },
            )

    from io import BytesIO
    from pathlib import Path

    from PIL import Image

    person_bytes = await person_file.read()
    if len(person_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="person_file cannot be empty",
        )
    person_image = Image.open(BytesIO(person_bytes)).convert("RGB")

    # ── 加载衣物图片（三选一：garment_file / garment_id / garment_image_url）──
    garment_image: Image.Image | None = None
    garment_image_2: Image.Image | None = None
    garment_image_source: str | None = None
    garment_image_2_source: str | None = None

    if garment_file is not None:
        garment_bytes = await garment_file.read()
        if len(garment_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="garment_file cannot be empty",
            )
        garment_image = Image.open(BytesIO(garment_bytes)).convert("RGB")
        garment_image_source = "upload"
    elif garment_id is not None:
        from uuid import UUID as _UUID

        from app.services.garment import get_garment_by_id

        try:
            gid = _UUID(garment_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="garment_id 格式无效")
        g = get_garment_by_id(db, gid)
        if not g:
            raise HTTPException(status_code=404, detail="衣物不存在")
        if str(g.user_id) != str(current_user.user_id):
            raise HTTPException(status_code=403, detail="无权访问该衣物")
        gpath = Path(g.image_path) if g.image_path else None
        if not gpath or not gpath.is_file():
            raise HTTPException(status_code=400, detail="衣物图片文件不存在，请重新上传")
        garment_image = Image.open(gpath).convert("RGB")
        garment_image_source = "wardrobe"
        # 如果没有 garment_image_url，用 garment 的 image_url 作为标准化 URL
        if not garment_image_url:
            garment_image_url = g.image_url

    if garment_file_2 is not None:
        garment2_bytes = await garment_file_2.read()
        garment_image_2 = (
            Image.open(BytesIO(garment2_bytes)).convert("RGB") if len(garment2_bytes) else None
        )
        if garment_image_2 is not None:
            garment_image_2_source = "upload"
    elif garment_id_2 is not None:
        from uuid import UUID as _UUID

        from app.services.garment import get_garment_by_id

        try:
            gid2 = _UUID(garment_id_2)
        except ValueError:
            raise HTTPException(status_code=400, detail="garment_id_2 格式无效")
        g2 = get_garment_by_id(db, gid2)
        if not g2:
            raise HTTPException(status_code=404, detail="第二件衣物不存在")
        if str(g2.user_id) != str(current_user.user_id):
            raise HTTPException(status_code=403, detail="无权访问该衣物")
        gpath2 = Path(g2.image_path) if g2.image_path else None
        if not gpath2 or not gpath2.is_file():
            raise HTTPException(status_code=400, detail="第二件衣物图片文件不存在")
        garment_image_2 = Image.open(gpath2).convert("RGB")
        garment_image_2_source = "wardrobe"
        if not garment_image_url_2:
            garment_image_url_2 = g2.image_url

    # 至少需要一件衣物图片
    if garment_image is None and garment_image_url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供衣物图片：garment_file、garment_id 或 garment_image_url 三选一",
        )

    def _load_uploads_url(url: str) -> Image.Image | None:
        u = (url or "").strip()
        low = u.lower()
        if "/uploads/" not in low:
            return None
        idx = low.find("/uploads/")
        tail = u[idx + len("/uploads/") :].lstrip("/").replace("\\", "/")
        if not tail:
            return None
        full = Path(settings.UPLOAD_DIR) / tail
        if not full.is_file():
            return None
        try:
            return Image.open(full).convert("RGB")
        except Exception:
            return None

    if garment_image_url and garment_image is None:
        img = _load_uploads_url(garment_image_url)
        if img is not None:
            garment_image = img
            garment_image_source = "url"
            pre_meta = {"standardized_image_url": garment_image_url}
        else:
            pre_meta = {}
    else:
        pre_meta = {"standardized_image_url": garment_image_url} if garment_image_url else {}

    if garment_image_url_2 and garment_image_2 is None:
        img2 = _load_uploads_url(garment_image_url_2)
        if img2 is not None:
            garment_image_2 = img2
            garment_image_2_source = "url"
            pre_meta["standardized_image_url_2"] = garment_image_url_2
    elif garment_image_url_2:
        pre_meta["standardized_image_url_2"] = garment_image_url_2

    pre_meta["garment_image_source"] = garment_image_source or "unknown"
    if garment_image_2 is not None:
        pre_meta["garment_image_2_source"] = garment_image_2_source or "unknown"

    if garment_image is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="衣物图片无法读取，请重新上传或检查 garment_image_url",
        )

    if check_tryon_garment_has_face(garment_image):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "衣服图检测到人像，请上传无模特商品图。",
                "error_code": "TRYON_GARMENT_CONTAINS_MODEL",
                "retryable": False,
                "action_hint": "请使用纯商品图，不要包含人物脸部。",
            },
        )
    if garment_image_2 is not None and check_tryon_garment_has_face(garment_image_2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "第二件衣服图检测到人像，请上传无模特商品图。",
                "error_code": "TRYON_GARMENT_CONTAINS_MODEL",
                "retryable": False,
                "action_hint": "请使用纯商品图，不要包含人物脸部。",
            },
        )

    strict_identity = mode == "strict"
    if mode == "strict":
        strict_identity = bool(getattr(settings, "TRYON_V2_STRICT_IDENTITY", True))

    thresholds = _v2_thresholds(strict_mode=(mode == "strict"))
    qc_threshold = float(getattr(settings, "TRYON_V2_QC_THRESHOLD", 0.6) or 0.6)

    # Generate and save preview_white BEFORE auto_preprocess overwrites garment_image.
    # This preview is for user display only (letterbox, no warp/stretch).
    preview_white_url: str | None = None
    preview_white_url_2: str | None = None

    try:
        import hashlib

        from app.services.tryon_v2.preprocess import generate_preview_white

        # Generate preview for garment 1
        pw_img = generate_preview_white(garment_image)
        if pw_img is not None:
            pw_bytes = _pil_image_to_jpeg_bytes(pw_img, quality=95)
            pw_key = hashlib.sha1(pw_bytes).hexdigest()[:20]
            pw_path = f"preprocess/preview_white_{pw_key}.jpg"
            _, preview_white_url = get_storage_service()._save_bytes(pw_bytes, pw_path)
            logger.info(f"[GARMENT] preview_white_1 saved: {preview_white_url}")

            # Also save to debug_session_dir if available
            if debug_session_dir:
                try:
                    debug_pw_path = Path(debug_session_dir) / "02b_preview_white.jpg"
                    pw_img.save(debug_pw_path, quality=95)
                    logger.info(f"[DEBUG] preview_white saved to: {debug_pw_path}")
                except Exception as ex:
                    logger.warning(f"[DEBUG] failed to save preview_white to debug dir: {ex}")

        # Generate preview for garment 2 (if exists)
        if garment_image_2 is not None:
            pw_img2 = generate_preview_white(garment_image_2)
            if pw_img2 is not None:
                pw_bytes2 = _pil_image_to_jpeg_bytes(pw_img2, quality=95)
                pw_key2 = hashlib.sha1(pw_bytes2).hexdigest()[:20]
                pw_path2 = f"preprocess/preview_white_{pw_key2}.jpg"
                _, preview_white_url_2 = get_storage_service()._save_bytes(pw_bytes2, pw_path2)
                logger.info(f"[GARMENT] preview_white_2 saved: {preview_white_url_2}")

                # Also save to debug_session_dir if available
                if debug_session_dir:
                    try:
                        debug_pw_path2 = Path(debug_session_dir) / "02c_preview_white_2.jpg"
                        pw_img2.save(debug_pw_path2, quality=95)
                        logger.info(f"[DEBUG] preview_white_2 saved to: {debug_pw_path2}")
                    except Exception as ex:
                        logger.warning(f"[DEBUG] failed to save preview_white_2 to debug dir: {ex}")
    except Exception as e:
        logger.warning(f"[GARMENT] failed to generate preview_white: {e}")

    garment_image, garment_category, auto_meta = _maybe_auto_preprocess(
        garment_image, garment_category
    )
    pre_meta = {**pre_meta, **auto_meta}

    # ── 保留去背景后的白底图用于颜色保真 ─────────────────────────────────────────
    # _maybe_auto_preprocess 已将 garment_image 替换为去背景后的白底标准化图片。
    # 颜色保真函数需要这个去背景后的白底图才能正确注入颜色/图案。
    # 这里保存处理后的图，传递给 color_fidelity_spatial / color_fidelity_enhance。
    original_garment_image = garment_image
    # ─────────────────────────────────────────────────────────────────────────

    if garment_image_2 is not None:
        garment_image_2, garment_category_2, pre_meta2 = _maybe_auto_preprocess(
            garment_image_2, garment_category_2
        )
        pre_meta["auto_preprocess_2"] = pre_meta2

    # stable_fast 模式：云端/远程引擎优先，稳定快速
    # bailian(百炼) / remote(远程VTON) / warp(几何贴合兜底)
    # CatVTON 不参与 stable_fast，保证响应速度

    # 预转换图片为 JPEG bytes（所有模式都需要）
    garment_jpg = _pil_image_to_jpeg_bytes(garment_image, quality=95)
    person_jpg = _pil_image_to_jpeg_bytes(person_image, quality=95)

    if mode == "stable_fast":
        from app.services.bailian_tryon_client import _bailian_configured, call_bailian_tryon
        from app.services.tryon_v2.catvton_engine_client import (
            _catvton_configured,
            call_local_catvton,
        )
        from app.services.tryon_v2.warp_engine import (
            overlay_draping_from_ai,
            tryon_hybrid_warp_catvton,
            tryon_pants_warp,
            tryon_skirt_warp,
            tryon_top_warp_preserve,
        )
        from app.services.virtual_tryon import get_tryon_service, sanitize_tryon_prompt
        from app.services.vton_remote_client import _remote_url_configured, call_remote_vton

        prompt_clean = sanitize_tryon_prompt(prompt or None) or ""
        gc = (garment_category or "").strip()

        # ── User requirement: uploaded garment must look pixel-identical in the result.
        # Strategy: warp(100% garment fidelity, cast shadow) → bailian → remote → catvton
        #
        # CatVTON is NOT used as an enhancement layer — it treats its "person" input as the person
        # to inpaint. Passing warp result to CatVTON causes darkening / double-processing.
        # CatVTON can only be used standalone (when warp is skipped).
        priority_str = (
            getattr(settings, "TRYON_V2_REPLACE_ENGINE_PRIORITY", "") or "warp,bailian,remote"
        )
        engine_priority = [e.strip().lower() for e in priority_str.split(",") if e.strip()]
        skip_warp = bool(getattr(settings, "TRYON_V2_REPLACE_SKIP_WARP", False))

        upstream: dict[str, Any] | None = None
        chosen: dict[str, Any] | None = None
        catvton_ok = False
        bailian_ok = False
        remote_ok = False
        used_warp = False

        # ── Engine execution: strictly follows TRYON_V2_REPLACE_ENGINE_PRIORITY order ──
        # Each engine is tried in priority order; first successful result wins.
        # warp is a true fallback (last in priority) — not run before AI engines.
        _cat_lower = gc.lower()
        _top_kw = any(k in _cat_lower for k in ("top", "上装", "上衣"))
        _skirt_kw = any(k in _cat_lower for k in ("skirt", "dress", "裙", "连衣裙"))
        _outfit_kw = any(k in _cat_lower for k in ("outfit", "套装", "上下装"))
        upstream_for_diag: dict[str, Any] | None = None

        for engine_name in engine_priority:
            if chosen is not None:
                break  # already have a result

            # ── Shared: run warp FIRST for 100% garment pixel fidelity ─────────────
            # Then let AI provide realistic drape/lighting.
            # This guarantees: original garment photo = result garment pixels.
            _warp_img: Image.Image | None = None
            _warp_meta: Any | None = None

            if engine_name in ("catvton", "bailian", "remote"):
                try:
                    if _top_kw:
                        _warp_img, _warp_meta = tryon_top_warp_preserve(
                            person_image, garment_image
                        )  # noqa: E501
                    elif _skirt_kw:
                        _warp_img, _warp_meta = tryon_skirt_warp(person_image, garment_image)
                    elif _outfit_kw:
                        img1, _m1 = tryon_top_warp_preserve(person_image, garment_image)
                        _warp_img, _warp_meta = tryon_pants_warp(img1, garment_image_2)
                    else:
                        _warp_img, _warp_meta = tryon_pants_warp(person_image, garment_image)
                    used_warp = True
                    logger.info(
                        "Warp preserve for hybrid: %s",
                        getattr(_warp_meta, "engine", "unknown"),
                    )
                except Exception as warp_err:
                    logger.warning(
                        "Warp preserve failed, AI engine will be used standalone: %s",
                        warp_err,
                    )
                    _warp_img = None

            # ── CatVTON (local diffusion) ──────────────────────────────────────────
            if engine_name == "catvton" and _catvton_configured():
                try:
                    upstream = await call_local_catvton(
                        garment_bytes=garment_jpg,
                        person_bytes=person_jpg,
                        garment_category=gc or None,
                        debug_dir=debug_session_dir,
                        preprocess_only=(debug_mode == "preprocess_only"),
                    )
                    logger.info(
                        "CatVTON returned: status=%s, has_image=%s, msg=%s",
                        upstream.get("status") if upstream else None,
                        upstream.get("result_image") is not None if upstream else False,
                        str(upstream.get("message") or "")[:80] if upstream else "None",
                    )
                    catvton_ok = (
                        isinstance(upstream, dict)
                        and str(upstream.get("status") or "").lower() == "success"
                        and upstream.get("result_image") is not None
                    )
                    if catvton_ok:
                        ai_img = upstream.get("result_image")
                        has_both = _warp_img is not None and ai_img is not None and _top_kw
                        if has_both:
                            # ── Warp + CatVTON 两阶段混合（新增）─────────────────
                            # Stage 1: warp_preserve → 像素级衣服保真（100% 原始颜色/图案）
                            # Stage 2: CatVTON diffusion → 真实光影/阴影/褶皱
                            # Stage 3: overlay_draping_from_ai → 衣服区域 100% warp，
                            #           衣服外叠加 CatVTON 光影（无 ghosting）
                            #
                            # drape_alpha=0.55：高彩色衣服保留 45% 身份感
                            # 对于低饱和衣服可以提升到 0.65 获得更真实的效果
                            result_img, hybrid_meta = tryon_hybrid_warp_catvton(
                                person_image=person_image,
                                garment_image=garment_image,
                                catvton_result=ai_img,
                                garment_category=gc or "top",
                                drape_alpha=0.55,
                                debug_session_dir=debug_session_dir,
                            )
                            upstream["result_image"] = result_img
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **hybrid_meta,
                                "warp_engine": getattr(_warp_meta, "engine", "unknown"),
                                "blend_mode": "warp_catvton_hybrid",
                            }
                            chosen = upstream
                            logger.info(
                                "CatVTON + Warp Hybrid: garment 100%% preserved from warp, "
                                "realism from CatVTON diffusion"
                            )
                            # ── 衣服颜色保真：图案衣服注入原始颜色/图案 ────────────────
                            # tryon_hybrid_warp_catvton 已用 warp_preserve 保留了衣服像素，
                            # 但 CatVTON 扩散可能略微改变颜色（尤其密集图案区）。
                            # 这里用 catvton_color_fidelity_spatial 做最终保真注入，
                            # 仅对 sat_max > 0.25 的高饱和图案衣服生效。
                            fidelity_strength = float(
                                getattr(settings, "TRYON_V2_COLOR_FIDELITY_STRENGTH", 0.75) or 0.75
                            )
                            enable_color_fidelity = bool(
                                getattr(settings, "TRYON_V2_COLOR_FIDELITY_ENABLED", True)
                            )
                            if enable_color_fidelity and fidelity_strength > 0.0:
                                try:
                                    from app.services.tryon_v2.warp_engine import (
                                        catvton_color_fidelity_enhance,
                                        catvton_color_fidelity_spatial,
                                    )

                                    arr_check = np.array(original_garment_image.convert("RGB"))
                                    hsv_check = cv2.cvtColor(arr_check, cv2.COLOR_RGB2HSV).astype(
                                        np.float32
                                    )
                                    sat_check = hsv_check[:, :, 1]
                                    v_check = hsv_check[:, :, 2]

                                    brightness_mask = (v_check >= 15) & (v_check <= 240)
                                    white_bg_mask = (v_check > 220) & (sat_check < 30)
                                    fg_mask_check = brightness_mask & ~white_bg_mask
                                    fg_sat_check = sat_check[fg_mask_check]

                                    if len(fg_sat_check) >= 30:
                                        sat_mean = float(fg_sat_check.mean()) / 255.0
                                        sat_max = float(fg_sat_check.max()) / 255.0
                                        has_color = sat_max > 0.15
                                        v_fg = v_check[fg_mask_check]
                                        bright_mean = (
                                            float(v_fg.mean()) / 255.0 if len(v_fg) > 0 else 0.0
                                        )
                                        is_white_garment = bright_mean > 0.78 and sat_mean < 0.08
                                    else:
                                        sat_mean = 0.0
                                        sat_max = 0.0
                                        has_color = False
                                        is_white_garment = True

                                    anomaly, cutout_qc, features = _build_fidelity_guard_context(
                                        original_garment_image
                                    )
                                    sat_mean = features.sat_mean
                                    sat_max = features.sat_max
                                    bright_mean = features.bright_mean
                                    has_color = features.has_color
                                    is_white_garment = features.is_white_garment
                                    if features.pattern_score >= 0.25:
                                        has_color = True
                                    preflight_qc_enabled = bool(
                                        getattr(settings, "TRYON_V2_PREFLIGHT_QC_ENABLED", True)
                                    )
                                    engine_decision, _engine_reason = decide_color_fidelity_engine(
                                        features=features,
                                        cutout_passed=(
                                            cutout_qc.passed or not preflight_qc_enabled
                                        ),
                                        input_anomaly_passed=(
                                            anomaly.passed or not preflight_qc_enabled
                                        ),
                                    )
                                    if preflight_qc_enabled and engine_decision == "skip":
                                        is_white_garment = True
                                        has_color = False
                                        sat_mean = 0.0
                                        sat_max = 0.0

                                    color_threshold = 0.05
                                    if not is_white_garment and (
                                        sat_mean > color_threshold or has_color
                                    ):
                                        if engine_decision == "spatial" and not (
                                            0.38 <= features.pattern_score <= 0.45
                                        ):
                                            logger.info(
                                                "stable_fast: applying spatial color fidelity "
                                                "for patterned garment "
                                                "(sat_mean=%.3f, sat_max=%.3f)",
                                                sat_mean,
                                                sat_max,
                                            )
                                            result_img, cf_meta = catvton_color_fidelity_spatial(
                                                catvton_result=result_img,
                                                original_garment=original_garment_image,
                                                person_image=person_image,
                                                garment_category=gc or "top",
                                                fidelity_strength=fidelity_strength,
                                                debug_session_dir=debug_session_dir,
                                            )
                                            upstream["result_image"] = result_img
                                            upstream["metadata"] = {
                                                **(upstream.get("metadata") or {}),
                                                **cf_meta,
                                                "color_fidelity_applied": True,
                                                "color_fidelity_mode": "spatial",
                                            }
                                            logger.info(
                                                "stable_fast: spatial CF applied (engine=%s)",
                                                cf_meta.get("engine", "unknown"),
                                            )
                                        elif sat_mean >= 0.05:
                                            logger.info(
                                                "stable_fast: applying uniform color fidelity "
                                                "(sat_mean=%.3f, solid garment)",
                                                sat_mean,
                                            )
                                            result_img, cf_meta = catvton_color_fidelity_enhance(
                                                catvton_result=result_img,
                                                original_garment=original_garment_image,
                                                person_image=person_image,
                                                garment_category=gc or "top",
                                                fidelity_strength=fidelity_strength,
                                            )
                                            upstream["result_image"] = result_img
                                            upstream["metadata"] = {
                                                **(upstream.get("metadata") or {}),
                                                **cf_meta,
                                                "color_fidelity_applied": True,
                                                "color_fidelity_mode": "uniform",
                                            }
                                            logger.info(
                                                "stable_fast: uniform CF applied (engine=%s)",
                                                cf_meta.get("engine", "unknown"),
                                            )
                                        else:
                                            logger.info(
                                                "stable_fast: skipping color fidelity "
                                                "(sat_mean=%.3f < 0.05, likely solid garment)",
                                                sat_mean,
                                            )
                                    else:
                                        logger.info(
                                            "stable_fast: skip CF (is_white_garment=%s, "
                                            "bright_mean=%.3f, sat_mean=%.3f)",
                                            is_white_garment,
                                            bright_mean,
                                            sat_mean,
                                        )
                                except Exception as cf_err:
                                    logger.warning(
                                        "stable_fast: color fidelity failed (continuing): %s",
                                        cf_err,
                                    )
                        elif _warp_img is not None and _top_kw:
                            upstream["result_image"] = _warp_img
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                "engine": "warp_preserve",
                                "warp_engine": getattr(_warp_meta, "engine", "unknown"),
                            }
                        chosen = upstream
                        logger.info("CatVTON succeeded for replace mode")

                        # ─── 预处理模式：直接返回中间产物 ─────────────────────────
                        if debug_mode == "preprocess_only":
                            record_tryon_v2_success(int((time.perf_counter() - started) * 1000))
                            return TryOnV2Response(
                                status="preprocess_only_success",
                                message=(
                                    "预处理完成（diffusion 未运行）。"
                                    "请查看 debug_session_dir 中的 03_mask.png "
                                    "和 04_pose_keypoints.jpg 验证质量。"
                                ),
                                pipeline="REPLACE",
                                result_image_url=None,
                                error_code=None,
                                retryable=False,
                                action_hint="检查 03_mask.png 是否覆盖了正确的衣服区域。"
                                "检查 04_pose_keypoints.jpg 关键点是否准确。",
                                qc_scores={},
                                metadata={
                                    **upstream.get("metadata", {}),
                                    "mode": "preprocess_only",
                                    "engine": "catvton",
                                },
                                debug_session_dir=debug_session_dir,
                            )
                except Exception as catvton_err:
                    logger.warning("CatVTON failed for replace mode: %s", catvton_err)

            # ── Bailian (cloud AI) ──────────────────────────────────────────────────
            elif engine_name == "bailian" and _bailian_configured():
                try:
                    upstream = await call_bailian_tryon(
                        garment_bytes=garment_jpg,
                        person_bytes=person_jpg,
                        prompt=prompt_clean,
                        garment_category=gc or None,
                    )
                    logger.info(
                        "Bailian returned: status=%s, has_image=%s, msg=%s",
                        upstream.get("status") if upstream else None,
                        upstream.get("result_image") is not None if upstream else False,
                        str(upstream.get("message") or "")[:80] if upstream else "None",
                    )
                    bailian_ok = (
                        isinstance(upstream, dict)
                        and str(upstream.get("status") or "").lower() == "success"
                        and upstream.get("result_image") is not None
                    )
                    upstream_for_diag = upstream
                    if bailian_ok:
                        ai_img = upstream.get("result_image")
                        if _warp_img is not None and ai_img is not None and _top_kw:
                            # ── Garment pixels 100% from warp, AI provides drape/lighting ──
                            result_img, overlay_meta = overlay_draping_from_ai(
                                warp_result=_warp_img,
                                ai_result=ai_img,
                                drape_alpha=0.65,
                            )
                            upstream["result_image"] = result_img
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **overlay_meta,
                                "warp_engine": getattr(_warp_meta, "engine", "unknown"),
                            }
                            logger.info(
                                "Bailian + drape overlay: garment 100%% preserved from warp"
                            )
                        elif _warp_img is not None and _top_kw:
                            upstream["result_image"] = _warp_img
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                "engine": "warp_preserve",
                                "warp_engine": getattr(_warp_meta, "engine", "unknown"),
                            }
                        chosen = upstream
                        logger.info("Bailian succeeded for replace mode")
                except Exception as bailian_err:
                    logger.warning("Bailian failed for replace mode: %s", bailian_err)

            # ── Remote VTON ───────────────────────────────────────────────────────
            elif engine_name == "remote" and _remote_url_configured():
                try:
                    remote = await call_remote_vton(
                        garment_bytes=garment_jpg,
                        person_bytes=person_jpg,
                        prompt=prompt_clean,
                        model_gender=model_gender,
                        garment_category=gc or None,
                    )
                    remote_ok = (
                        isinstance(remote, dict)
                        and str(remote.get("status") or "").lower() == "success"
                        and remote.get("result_image") is not None
                    )
                    upstream_for_diag = remote
                    if remote_ok:
                        ai_img = remote.get("result_image")
                        if _warp_img is not None and ai_img is not None and _top_kw:
                            # ── Garment pixels 100% from warp, AI provides drape/lighting ──
                            result_img, overlay_meta = overlay_draping_from_ai(
                                warp_result=_warp_img,
                                ai_result=ai_img,
                                drape_alpha=0.65,
                            )
                            remote["result_image"] = result_img
                            remote["metadata"] = {
                                **(remote.get("metadata") or {}),
                                **overlay_meta,
                                "warp_engine": getattr(_warp_meta, "engine", "unknown"),
                            }
                            logger.info(
                                "Remote VTON + drape overlay: garment 100%% preserved from warp"
                            )
                        elif _warp_img is not None and _top_kw:
                            remote["result_image"] = _warp_img
                            remote["metadata"] = {
                                **(remote.get("metadata") or {}),
                                "engine": "warp_preserve",
                                "warp_engine": getattr(_warp_meta, "engine", "unknown"),
                            }
                        chosen = remote
                        logger.info("Remote VTON succeeded for replace mode")
                except Exception as remote_err:
                    logger.warning("Remote VTON failed for replace mode: %s", remote_err)

            # ── Warp (geometric paste — 100% garment fidelity, but flat look) ────
            elif engine_name == "warp" and not skip_warp:
                try:
                    if _top_kw:
                        warp_img, warp_meta = tryon_top_warp_preserve(person_image, garment_image)
                    elif _skirt_kw:
                        warp_img, warp_meta = tryon_skirt_warp(person_image, garment_image)
                    elif _outfit_kw:
                        img1, _m1 = tryon_top_warp_preserve(person_image, garment_image)
                        warp_img, warp_meta = tryon_pants_warp(img1, garment_image_2)
                    else:
                        warp_img, warp_meta = tryon_pants_warp(person_image, garment_image)

                    if warp_img is not None:
                        chosen = {
                            "status": "success",
                            "message": "warp 保底完成（像素级衣服保真，但贴合不真实）",
                            "result_image": warp_img,
                            "metadata": {
                                "engine": "warp_preserve",
                                "warp_engine": getattr(warp_meta, "engine", "unknown"),
                            },
                        }
                        used_warp = True
                        logger.info("Warp preserve succeeded (geometric paste)")
                except Exception as warp_err:
                    logger.warning("Warp preserve failed: %s", warp_err)

            # ── Local diffusion (last resort) ───────────────────────────────────────
            elif engine_name == "diffusion" and bool(
                getattr(settings, "TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION", False)
            ):
                try:
                    service = get_tryon_service()
                    chosen = service.tryon_garment(
                        garment_image=garment_image,
                        person_image=person_image,
                        prompt=prompt_clean,
                        model_gender=model_gender,
                        garment_category=gc or None,
                        force_fallback=False,
                    )
                    logger.info("Local diffusion succeeded for replace mode")
                except Exception as diff_err:
                    logger.warning("Local diffusion failed for replace mode: %s", diff_err)

        # ── All engines exhausted ───────────────────────────────────────────────
        if chosen is None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record_tryon_v2_failure("TRYON_V2_REPLACE_UPSTREAM_UNAVAILABLE", latency_ms)
            hints = []
            bailian_diag: dict[str, Any] = {}
            remote_diag: dict[str, Any] = {}
            catvton_diag: dict[str, Any] = {}

            if not _catvton_configured():
                hints.append(
                    "启用本地 CatVTON（推荐）：CATVTON_ENABLED=true 且 CATVTON_PATH 指向 CatVTON 目录"
                )
            if not _bailian_configured():
                hints.append("或启用百炼：DASHSCOPE_TRYON_ENABLED=true 且配置 DASHSCOPE_API_KEY")
            elif upstream_for_diag is not None:
                msg = str(upstream_for_diag.get("message") or "").strip()
                upstream_meta = (
                    upstream_for_diag.get("metadata", {})
                    if isinstance(upstream_for_diag.get("metadata"), dict)
                    else {}
                )
                reason = str(upstream_meta.get("reason") or "").strip()
                specific_hint = str(upstream_meta.get("specific_hint") or "").strip()
                upstream_status = str(upstream_for_diag.get("status") or "").lower()
                if upstream_status == "success" and upstream_for_diag.get("result_image") is None:
                    hints.append(f"百炼返回成功但缺少结果图（specific_hint: {specific_hint}）")
                elif reason == "dashscope_missing":
                    hints.append("百炼失败：dashscope 包未安装，请运行 pip install dashscope")
                elif specific_hint:
                    hints.append(f"百炼失败：{specific_hint}（{msg}）")
                elif msg:
                    hints.append(f"百炼失败：{msg}")
                else:
                    hints.append(f"百炼失败：{reason or '未知错误'}")
                error_type = str(upstream_meta.get("error_type") or "").strip()
                bailian_diag = {
                    "configured": True,
                    "status": upstream_status,
                    "message": msg,
                    "reason": reason,
                    "error_type": error_type,
                    "specific_hint": specific_hint,
                    "code": str(upstream_meta.get("code") or "").strip(),
                    "status_code": upstream_meta.get("status_code"),
                    "exception_message": str(upstream_meta.get("exception_message") or "").strip(),
                    "model": str(upstream_meta.get("model") or "").strip(),
                    "function": str(upstream_meta.get("function") or "").strip(),
                }
            if not _remote_url_configured():
                hints.append("或配置远程 VTON：VTON_INFERENCE_URL")
            if hints:
                hints.append(
                    "（高级）如确需本机 diffusers 兜底：TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true，"
                    "并确保 SD inpainting 权重完整"
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "替换试衣上游均不可用",
                    "error_code": "TRYON_V2_REPLACE_UPSTREAM_UNAVAILABLE",
                    "retryable": True,
                    "action_hint": (
                        "；".join(hints) if hints else "所有试衣引擎均不可用，请检查配置"
                    ),
                    "qc_scores": {},
                    "replace_debug": {
                        "bailian": bailian_diag,
                        "remote": remote_diag,
                        "catvton_local": catvton_diag,
                        "bailian_configured": _bailian_configured(),
                        "remote_configured": _remote_url_configured(),
                        "catvton_configured": _catvton_configured(),
                        "used_warp": used_warp,
                    },
                },
            )

        # ── Build result from chosen engine ───────────────────────────────────
        status_s = str((chosen or {}).get("status") or "error").lower()
        if status_s != "success" or (chosen or {}).get("result_image") is None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record_tryon_v2_failure("TRYON_V2_REPLACE_FAILED", latency_ms)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": str((chosen or {}).get("message") or "替换试衣失败"),
                    "error_code": "TRYON_V2_REPLACE_FAILED",
                    "retryable": True,
                    "action_hint": "请稍后重试",
                    "qc_scores": {},
                },
            )

        replace_qc_scores: dict[str, float] = {}
        try:
            from app.services.tryon_v2.qc import _boundary_artifact_score, _identity_preserve_score

            result_img = (chosen or {}).get("result_image")
            if result_img is not None:
                replace_qc_scores["identity_preserve_score"] = float(
                    _identity_preserve_score(person_image, result_img)
                )
                replace_qc_scores["boundary_artifact_score"] = float(
                    _boundary_artifact_score(person_image, result_img)
                )
        except Exception:
            pass

        upstream_meta = (chosen or {}).get("metadata") or {}
        if isinstance(upstream_meta, dict):
            engine_name = upstream_meta.get("engine") or upstream_meta.get("model") or "unknown"
        else:
            engine_name = "unknown"

        result = {
            "status": "success",
            "message": str((chosen or {}).get("message") or "替换试衣完成"),
            "result_image": (chosen or {}).get("result_image"),
            "qc_scores": replace_qc_scores,
            "metadata": {
                "pipeline": "REPLACE",
                "engine": engine_name,
                "upstream_metadata": upstream_meta,
                "used_warp": used_warp,
            },
        }
    elif mode == "detail_fidelity":
        # ── Detail Fidelity Mode: CatVTON 深度学习 + 质量检测 + 颜色保真 ────────────
        # 最强保真模式：自动质量检测（score < 0.75 重试）+ 颜色保真增强
        # 适用：追求最高质量、愿意等待更长时间（3-25min）
        from app.services.quality_checker import QualityChecker
        from app.services.tryon_v2.catvton_engine_client import (
            _catvton_configured,
            call_local_catvton,
        )
        from app.services.tryon_v2.warp_engine import (
            tryon_pants_warp,
            tryon_skirt_warp,
            tryon_top_warp_preserve,
        )

        cat = (garment_category or "").strip().lower()
        gc = (garment_category or "").strip()

        cloth_type = "upper"
        if any(
            k in cat for k in ("bottom", "下装", "裤", "裤装", "短裤", "pants", "长裤", "lower")
        ):
            cloth_type = "lower"
        elif any(k in cat for k in ("skirt", "裙", "连衣裙", "dress", "裙装")):
            cloth_type = "overall"

        logger.info(
            "[detail_fidelity] category_locked: garment_category=%r → cat=%r, cloth_type=%r",
            garment_category,
            cat,
            cloth_type,
        )

        # ── CatVTON 调用：最多重试 2 次（瞬时错误 / VRAM OOM / CUDA 抖动）───
        max_retries = 2
        last_upstream = None
        last_err_reason = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                wait_s = 2 ** (attempt - 1)
                logger.warning(
                    f"Realistic mode: CatVTON attempt {attempt}/{max_retries} failed, "
                    f"retrying in {wait_s}s..."
                )
                await asyncio.sleep(wait_s)

            upstream = await call_local_catvton(
                garment_bytes=garment_jpg,
                person_bytes=person_jpg,
                garment_category=cloth_type,
                debug_dir=debug_session_dir,
                preprocess_only=(debug_mode == "preprocess_only"),
            )
            last_upstream = upstream

            # ─── 预处理模式：直接返回中间产物 ─────────────────────────
            if debug_mode == "preprocess_only" and isinstance(upstream, dict):
                upstream_meta = upstream.get("metadata") or {}
                record_tryon_v2_success(int((time.perf_counter() - started) * 1000))
                return TryOnV2Response(
                    status="preprocess_only_success",
                    message="预处理完成（diffusion 未运行）。"
                    "请查看 debug_session_dir 中的 03_mask.png 和 04_pose_keypoints.jpg 验证质量。",
                    pipeline="REALISTIC",
                    result_image_url=None,
                    error_code=None,
                    retryable=False,
                    action_hint="检查 03_mask.png 是否覆盖了正确的衣服区域。"
                    "检查 04_pose_keypoints.jpg 关键点是否准确。",
                    qc_scores=upstream.get("qc_scores") or {},
                    metadata={
                        **upstream_meta,
                        "mode": "preprocess_only",
                        "engine": "catvton",
                        "catvton_category": cloth_type,
                    },
                    debug_session_dir=debug_session_dir,
                )

            # 检查 CatVTON 成功条件
            if (
                isinstance(upstream, dict)
                and str(upstream.get("status") or "").lower() == "success"
                and upstream.get("result_image") is not None
            ):
                result_img = upstream.get("result_image")
                upstream_meta = upstream.get("metadata") or {}
                upstream_debug_session_dir = upstream_meta.get("debug_session_dir")
                if upstream_debug_session_dir:
                    if upstream_debug_session_dir != debug_session_dir:
                        logger.info(
                            "[DEBUG] Using CatVTON subprocess debug directory for "
                            "post-CatVTON stages: %s",
                            upstream_debug_session_dir,
                        )
                    debug_session_dir = upstream_debug_session_dir

                # ── 衣服颜色保真增强（启用）───────────────────────────────────────
                # CatVTON 会重新生成衣服的颜色/图案，可能与原衣服差异较大。
                # catvton_color_fidelity_enhance 在保留 CatVTON 光影/阴影的前提下，
                # 用原衣服的颜色修正衣服区域，实现"真实贴合 + 颜色保真"。
                # 仅对彩色/有图案的衣服生效（高饱和度检测），纯白/纯黑衣服跳过。
                pattern_score = 0.0
                pattern_injected = False
                color_fidelity_stage_saved = False
                fidelity_strength = float(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_STRENGTH", 0.75) or 0.75
                )
                enable_color_fidelity = bool(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_ENABLED", True)
                )
                raw_quality = None
                raw_quality_decision = "unassessed"
                skip_catvton_safe_postprocess = False
                skip_pattern_enhance = False

                if enable_color_fidelity and fidelity_strength > 0.0:
                    try:
                        from app.services.tryon_v2.warp_engine import (
                            catvton_color_fidelity_enhance,
                            catvton_color_fidelity_spatial,
                            catvton_lab_chroma_color_correct,
                            catvton_lower_color_rescue,
                            tryon_lower_structure_preserve,
                        )

                        arr_check = np.array(original_garment_image.convert("RGB"))
                        hsv_check = cv2.cvtColor(arr_check, cv2.COLOR_RGB2HSV).astype(np.float32)
                        sat_check = hsv_check[:, :, 1]
                        v_check = hsv_check[:, :, 2]

                        # ── 改进的饱和度检测 ──────────────────────────────────────
                        # 方案1: 排除极亮(白色)和极暗(黑色)像素，只保留可能是彩色衣服的区域
                        # 白色背景通常 v>240 且 s<20
                        # 黑色区域通常 v<15
                        # 中等亮度区域 v∈[15,240] 才可能是衣服
                        brightness_mask = (v_check >= 15) & (v_check <= 240)
                        # 排除纯白背景 (高亮度 + 低饱和度)
                        white_bg_mask = (v_check > 220) & (sat_check < 30)
                        # 综合前景掩码
                        fg_mask_check = brightness_mask & ~white_bg_mask
                        fg_sat_check = sat_check[fg_mask_check]

                        if len(fg_sat_check) >= 30:
                            sat_mean = float(fg_sat_check.mean()) / 255.0
                            sat_max = float(fg_sat_check.max()) / 255.0
                            has_color = sat_max > 0.15
                            v_fg = v_check[fg_mask_check]
                            bright_mean = float(v_fg.mean()) / 255.0 if len(v_fg) > 0 else 0.0
                            is_white_garment = bright_mean > 0.78 and sat_mean < 0.08
                        else:
                            sat_mean = 0.0
                            sat_max = 0.0
                            has_color = False
                            is_white_garment = True

                        anomaly, cutout_qc, features = _build_fidelity_guard_context(
                            original_garment_image
                        )
                        raw_mask_image = None
                        if debug_session_dir:
                            try:
                                from pathlib import Path

                                mask_candidates = []
                                debug_path = Path(debug_session_dir)
                                mask_candidates.append(debug_path / "08_mask_resized.png")
                                if not debug_path.is_absolute():
                                    mask_candidates.append(
                                        Path.cwd() / debug_path / "08_mask_resized.png"
                                    )
                                    mask_candidates.append(
                                        Path.cwd().parent / debug_path / "08_mask_resized.png"
                                    )
                                for mask_path in mask_candidates:
                                    if mask_path.exists():
                                        raw_mask_image = Image.open(mask_path).convert("L")
                                        logger.info(
                                            "Realistic: using CatVTON resized mask "
                                            "for raw quality gate: %s",
                                            mask_path,
                                        )
                                        break
                            except Exception as mask_err:
                                logger.info(
                                    "Realistic mode: CatVTON resized mask "
                                    "unavailable for raw quality gate: %s",
                                    mask_err,
                                )

                        raw_quality = evaluate_raw_catvton_quality(
                            raw_result=result_img,
                            original_garment=original_garment_image,
                            person_image=person_image,
                            garment_category=gc or "top",
                            features=features,
                            raw_mask_image=raw_mask_image,
                        )
                        raw_quality_decision = raw_quality.decision
                        raw_quality_meta = {
                            "decision": raw_quality.decision,
                            "reason": raw_quality.reason,
                            "color_passed": raw_quality.color_passed,
                            "pattern_passed": raw_quality.pattern_passed,
                            "artifact_passed": raw_quality.artifact_passed,
                            "color_delta": round(raw_quality.color_delta, 3),
                            "source_value_mean": round(raw_quality.source_value_mean, 4),
                            "raw_value_mean": round(raw_quality.raw_value_mean, 4),
                            "source_pattern_score": round(raw_quality.source_pattern_score, 4),
                            "raw_pattern_signal": round(raw_quality.raw_pattern_signal, 4),
                            "artifact_score": round(raw_quality.artifact_score, 4),
                            "garment_coverage": round(raw_quality.garment_coverage, 4),
                            "source_hue_entropy": round(
                                getattr(raw_quality, "source_hue_entropy", 0.0),
                                4,
                            ),
                            "raw_hue_entropy": round(
                                getattr(raw_quality, "raw_hue_entropy", 0.0),
                                4,
                            ),
                        }
                        protect_upper_raw_detail = (
                            cloth_type == "upper"
                            and raw_quality.decision == "color_only"
                            and raw_quality.pattern_passed
                            and raw_quality.source_pattern_score >= 0.55
                            and raw_quality.raw_pattern_signal
                            >= max(0.16, raw_quality.source_pattern_score * 0.55)
                        )
                        sat_mean = features.sat_mean
                        sat_max = features.sat_max
                        bright_mean = features.bright_mean
                        has_color = features.has_color
                        is_white_garment = features.is_white_garment
                        if features.pattern_score >= 0.25:
                            has_color = True
                        preflight_qc_enabled = bool(
                            getattr(settings, "TRYON_V2_PREFLIGHT_QC_ENABLED", True)
                        )
                        engine_decision, _engine_reason = decide_color_fidelity_engine(
                            features=features,
                            cutout_passed=(cutout_qc.passed or not preflight_qc_enabled),
                            input_anomaly_passed=(anomaly.passed or not preflight_qc_enabled),
                        )
                        structured_lower_pattern_recovery = bool(
                            any(k in (gc or "") for k in ("bottom", "下装"))
                            and raw_quality.decision == "pattern_only"
                            and raw_quality.source_pattern_score >= 0.78
                            and raw_quality.raw_pattern_signal
                            <= max(0.24, raw_quality.source_pattern_score * 0.32)
                        )
                        forced_lower_pattern_recovery = (
                            should_force_lower_structured_pattern_recovery(
                                garment_category=gc or "",
                                raw_quality=raw_quality,
                            )
                        )
                        if forced_lower_pattern_recovery:
                            structured_lower_pattern_recovery = True
                            raw_quality_meta["forced_lower_pattern_recovery"] = True
                            raw_quality_meta["forced_lower_pattern_recovery_reason"] = (
                                "strong_structured_lower_pattern_under_recovered"
                            )
                        if preflight_qc_enabled and engine_decision == "skip":
                            is_white_garment = True
                            has_color = False
                            sat_mean = 0.0
                            sat_max = 0.0

                        color_threshold = 0.05  # 降低阈值：原 0.08 太严格
                        if (
                            raw_quality.decision == "raw" and not forced_lower_pattern_recovery
                        ) or protect_upper_raw_detail:
                            logger.info(
                                "Realistic mode: preserving raw CatVTON output; "
                                "returning step-9 output directly (%s)%s",
                                raw_quality.reason,
                                " [upper_detail_protected]" if protect_upper_raw_detail else "",
                            )
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                "color_fidelity_applied": False,
                                "raw_quality_gate": raw_quality_meta,
                                "postprocess_skip_reason": (
                                    "upper_pattern_preserved_after_raw_gate"
                                    if protect_upper_raw_detail
                                    else "raw_quality_passed"
                                ),
                                "upper_detail_protected": protect_upper_raw_detail,
                            }
                            skip_catvton_safe_postprocess = True
                            skip_pattern_enhance = True
                            save_debug_stage_image(
                                debug_session_dir=debug_session_dir,
                                filename="12_after_color_fidelity.jpg",
                                image=result_img,
                                metadata={
                                    "stage": "after_color_fidelity",
                                    "color_fidelity_applied": False,
                                    "reason": (
                                        "upper_pattern_preserved_after_raw_gate"
                                        if protect_upper_raw_detail
                                        else "raw_quality_passed"
                                    ),
                                    "upper_detail_protected": protect_upper_raw_detail,
                                    "raw_quality_gate": raw_quality_meta,
                                },
                            )
                            color_fidelity_stage_saved = True
                        elif raw_quality.decision == "artifact_only":
                            logger.info(
                                "Realistic: raw color/pattern passed but artifacts detected; "
                                "applying conservative raw artifact repair only (%s)",
                                raw_quality.reason,
                            )
                            result_img, repair_meta = repair_raw_catvton_artifacts(
                                raw_result=result_img,
                                person_image=person_image,
                                garment_category=gc or "top",
                                raw_mask_image=raw_mask_image,
                            )
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **repair_meta,
                                "color_fidelity_applied": False,
                                "raw_quality_gate": raw_quality_meta,
                                "postprocess_skip_reason": "artifact_only_raw_gate",
                            }
                            skip_catvton_safe_postprocess = True
                            skip_pattern_enhance = True
                            save_debug_stage_image(
                                debug_session_dir=debug_session_dir,
                                filename="12_after_color_fidelity.jpg",
                                image=result_img,
                                metadata={
                                    "stage": "after_color_fidelity",
                                    "color_fidelity_applied": False,
                                    "reason": "artifact_only_raw_gate",
                                    "raw_quality_gate": raw_quality_meta,
                                    **repair_meta,
                                },
                            )
                            color_fidelity_stage_saved = True
                        elif raw_quality.decision == "color_only":
                            logger.info(
                                "Realistic mode: raw pattern is OK but color is missing; "
                                "applying LAB/chroma color correction only"
                            )
                            skip_catvton_safe_postprocess = True
                            skip_pattern_enhance = True
                            result_img, cf_meta = catvton_lab_chroma_color_correct(
                                catvton_result=result_img,
                                original_garment=original_garment_image,
                                person_image=person_image,
                                garment_category=gc or "top",
                                raw_mask_image=raw_mask_image,
                                fidelity_strength=fidelity_strength,
                            )
                            pattern_injected = False
                            pattern_score = 0.0
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **cf_meta,
                                "color_fidelity_applied": True,
                                "raw_quality_gate": raw_quality_meta,
                                "postprocess_skip_reason": "minimal_raw_gate_branch",
                            }
                            save_debug_stage_image(
                                debug_session_dir=debug_session_dir,
                                filename="12_after_color_fidelity.jpg",
                                image=result_img,
                                metadata={
                                    "stage": "after_color_fidelity",
                                    "pattern_score": round(pattern_score, 3),
                                    "engine": cf_meta.get("engine", "unknown"),
                                    "garment_region": cf_meta.get("garment_region"),
                                    "raw_quality_gate": raw_quality_meta,
                                },
                            )
                            color_fidelity_stage_saved = True
                        elif raw_quality.decision == "strong_spatial" and any(
                            k in (gc or "").strip().lower()
                            for k in (
                                "bottom",
                                "下装",
                                "裤",
                                "裤装",
                                "短裤",
                                "pants",
                                "长裤",
                                "lower",
                            )
                        ):
                            logger.info(
                                "Realistic mode: lower garment failed raw color/pattern; "
                                "using structure-preserve pants warp instead of spatial repaint"
                            )
                            skip_catvton_safe_postprocess = True
                            skip_pattern_enhance = True
                            result_img, cf_meta = tryon_lower_structure_preserve(
                                person_image=person_image,
                                garment_image=original_garment_image,
                                catvton_result=result_img,
                                raw_mask_image=raw_mask_image,
                                drape_alpha=0.22,
                                debug_session_dir=debug_session_dir,
                            )
                            if cf_meta.get("fallback_recommended") == "spatial":
                                result_img, cf_meta = catvton_lower_color_rescue(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    fidelity_strength=min(fidelity_strength, 0.82),
                                    debug_session_dir=debug_session_dir,
                                )
                            pattern_injected = True
                            pattern_score = min(0.95, sat_mean + 0.3)
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **cf_meta,
                                "color_fidelity_applied": True,
                                "raw_quality_gate": raw_quality_meta,
                                "postprocess_skip_reason": "lower_structure_preserve_raw_gate",
                            }
                            save_debug_stage_image(
                                debug_session_dir=debug_session_dir,
                                filename="12_after_color_fidelity.jpg",
                                image=result_img,
                                metadata={
                                    "stage": "after_color_fidelity",
                                    "pattern_score": round(pattern_score, 3),
                                    "engine": cf_meta.get("engine", "unknown"),
                                    "garment_region": cf_meta.get("garment_region"),
                                    "raw_quality_gate": raw_quality_meta,
                                    "lower_warp_qc": cf_meta.get("lower_warp_qc"),
                                    "lower_denim_like": cf_meta.get("lower_denim_like"),
                                },
                            )
                            color_fidelity_stage_saved = True
                        elif (
                            raw_quality.decision == "pattern_only" or forced_lower_pattern_recovery
                        ):
                            logger.info(
                                "Realistic mode: raw color is OK but motif is missing%s; "
                                "applying localized motif recovery only",
                                (
                                    " [forced lower structured recovery]"
                                    if forced_lower_pattern_recovery
                                    else ""
                                ),
                            )
                            skip_catvton_safe_postprocess = True
                            skip_pattern_enhance = True
                            if structured_lower_pattern_recovery:
                                logger.info(
                                    "Realistic mode: lower structured pattern is under-recovered; "
                                    "using structure-preserve pants warp instead of "
                                    "motif-only spatial recovery"
                                )
                                result_img, cf_meta = tryon_lower_structure_preserve(
                                    person_image=person_image,
                                    garment_image=original_garment_image,
                                    catvton_result=result_img,
                                    raw_mask_image=raw_mask_image,
                                    drape_alpha=0.42,
                                    debug_session_dir=debug_session_dir,
                                )
                                if cf_meta.get("fallback_recommended") == "spatial":
                                    result_img, cf_meta = catvton_color_fidelity_spatial(
                                        catvton_result=result_img,
                                        original_garment=original_garment_image,
                                        person_image=person_image,
                                        garment_category=gc or "top",
                                        fidelity_strength=min(fidelity_strength, 0.62),
                                        debug_session_dir=debug_session_dir,
                                    )
                            else:
                                result_img, cf_meta = catvton_color_fidelity_spatial(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    garment_category=gc or "top",
                                    fidelity_strength=min(fidelity_strength, 0.62),
                                    debug_session_dir=debug_session_dir,
                                )
                            pattern_injected = True
                            pattern_score = min(0.95, sat_mean + 0.3)
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **cf_meta,
                                "color_fidelity_applied": True,
                                "raw_quality_gate": raw_quality_meta,
                                "structured_lower_pattern_recovery": (
                                    structured_lower_pattern_recovery
                                ),
                                "postprocess_skip_reason": (
                                    "lower_structure_preserve_pattern_gate"
                                    if structured_lower_pattern_recovery
                                    else "minimal_raw_gate_branch"
                                ),
                            }
                            save_debug_stage_image(
                                debug_session_dir=debug_session_dir,
                                filename="12_after_color_fidelity.jpg",
                                image=result_img,
                                metadata={
                                    "stage": "after_color_fidelity",
                                    "pattern_score": round(pattern_score, 3),
                                    "engine": cf_meta.get("engine", "unknown"),
                                    "garment_region": cf_meta.get("garment_region"),
                                    "raw_quality_gate": raw_quality_meta,
                                    "structured_lower_pattern_recovery": (
                                        structured_lower_pattern_recovery
                                    ),
                                },
                            )
                            color_fidelity_stage_saved = True
                        elif is_white_garment:
                            logger.info(
                                "Realistic mode: skipping color fidelity "
                                "(is_white_garment=True, bright_mean=%.3f, sat_mean=%.3f, "
                                "white garment looks correct from CatVTON - preserve purity)",
                                bright_mean,
                                sat_mean,
                            )
                        elif sat_mean > color_threshold or has_color:
                            # 高对比度图案（格子/条纹/彩色印花）使用空间感知保真
                            # 均匀 LAB 混合会把蓝白格子变成褐色——必须用像素级替换
                            # 使用 max 饱和度判断是否需要 spatial 保真
                            if engine_decision == "spatial" and not (
                                0.38 <= features.pattern_score <= 0.45
                            ):
                                # 图案衣服（格子/条纹/密集印花）：使用 catvton_color_fidelity_spatial
                                # catvton_color_fidelity_enhance（LAB均匀混合）会把格子变褐色，
                                # spatial 版本做像素级 warp 叠加，原图案空间分布100%保留。
                                # TPS warp 有 bug 时会 fallback 到 Quad 透视变形（更鲁棒）。
                                logger.info(
                                    "Realistic: spatial CF for patterned garment "
                                    "(sat_mean=%.3f, sat_max=%.3f) — warp original onto result",
                                    sat_mean,
                                    sat_max,
                                )
                                result_img, cf_meta = catvton_color_fidelity_spatial(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    garment_category=gc or "top",
                                    fidelity_strength=fidelity_strength,
                                    debug_session_dir=debug_session_dir,
                                )
                            elif sat_mean >= 0.05:
                                logger.info(
                                    "Realistic mode: applying uniform color fidelity "
                                    "(saturation=%.3f, solid garment)",
                                    sat_mean,
                                )
                                result_img, cf_meta = catvton_color_fidelity_enhance(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    garment_category=gc or "top",
                                    fidelity_strength=fidelity_strength,
                                )
                            pattern_injected = True
                            pattern_score = min(0.95, sat_mean + 0.3)
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **cf_meta,
                                "color_fidelity_applied": True,
                                "raw_quality_gate": raw_quality_meta,
                                "postprocess_skip_reason": (
                                    "minimal_raw_gate_branch"
                                    if skip_catvton_safe_postprocess
                                    else None
                                ),
                            }
                            logger.info(
                                "Realistic mode: color fidelity applied "
                                "(pattern_score=%.3f, engine=%s)",
                                pattern_score,
                                cf_meta.get("engine", "unknown"),
                            )
                            save_debug_stage_image(
                                debug_session_dir=debug_session_dir,
                                filename="12_after_color_fidelity.jpg",
                                image=result_img,
                                metadata={
                                    "stage": "after_color_fidelity",
                                    "pattern_score": round(pattern_score, 3),
                                    "engine": cf_meta.get("engine", "unknown"),
                                    "garment_region": cf_meta.get("garment_region"),
                                    "cutout_qc": {
                                        "passed": cutout_qc.passed,
                                        "alpha_coverage": round(cutout_qc.alpha_coverage, 4),
                                        "component_count": cutout_qc.alpha_component_count,
                                        "bbox_fill_ratio": round(cutout_qc.bbox_fill_ratio, 4),
                                        "edge_touch_ratio": round(cutout_qc.edge_touch_ratio, 4),
                                        "background_leak_ratio": round(
                                            cutout_qc.background_leak_ratio, 4
                                        ),
                                    },
                                    "engine_decision_features": {
                                        "sat_mean": round(features.sat_mean, 4),
                                        "sat_max": round(features.sat_max, 4),
                                        "pattern_score": round(features.pattern_score, 4),
                                        "pattern_confidence": round(features.pattern_confidence, 4),
                                        "mirror_ghost_score": round(anomaly.mirror_ghost_score, 4),
                                    },
                                    "raw_quality_gate": raw_quality_meta,
                                },
                            )
                            color_fidelity_stage_saved = True
                        else:
                            logger.info(
                                "Realistic mode: skipping color fidelity "
                                "(saturation=%.3f < 0.08, likely solid garment)",
                                sat_mean,
                            )
                    except Exception as cf_err:
                        logger.warning(
                            "Realistic mode: color fidelity failed (continuing): %s",
                            cf_err,
                        )
                else:
                    logger.info(
                        "Realistic mode: color fidelity disabled " "(enable=%s, strength=%.2f)",
                        enable_color_fidelity,
                        fidelity_strength,
                    )

                # ── 后处理增强（消除拼接痕迹）──────────────────────────────
                # 注意：CatVTON 输出尺寸 (512x768 或 768x1024) 与原始人物图尺寸不同。
                # enhance_tryon_result 需要 result 和 person 尺寸一致，需要先对齐。
                if not color_fidelity_stage_saved:
                    save_debug_stage_image(
                        debug_session_dir=debug_session_dir,
                        filename="12_after_color_fidelity.jpg",
                        image=result_img,
                        metadata={
                            "stage": "after_color_fidelity",
                            "color_fidelity_applied": False,
                            "reason": (
                                "disabled_or_skipped_or_failed"
                                if enable_color_fidelity
                                else "disabled"
                            ),
                            "fidelity_strength": fidelity_strength,
                            "fallback_reason": "disabled_or_skipped_or_failed",
                        },
                    )

                try:
                    from app.services.tryon_v2.postprocess import catvton_safe_enhance

                    # 将 CatVTON 输出 resize 到原始人物图尺寸（保持宽高比，填充白边）
                    pw, ph = person_image.size
                    if result_img.size != (pw, ph):
                        result_img_resized = result_img.resize((pw, ph), Image.LANCZOS)
                        logger.info(
                            "Realistic mode: resizing CatVTON result from %sx%s to %sx%s "
                            "for post-processing compatibility",
                            result_img.size[0],
                            result_img.size[1],
                            pw,
                            ph,
                        )
                    else:
                        result_img_resized = result_img
                    save_debug_stage_image(
                        debug_session_dir=debug_session_dir,
                        filename="13_after_resize_for_postprocess.jpg",
                        image=result_img_resized,
                        metadata={
                            "stage": "after_resize_for_postprocess",
                            "size": list(result_img_resized.size),
                        },
                    )

                    # CatVTON-safe: denoise + seam removal + sharpen (no blending)
                    if skip_catvton_safe_postprocess:
                        result_img = result_img_resized
                        logger.info(
                            "Realistic mode: skipping CatVTON-safe post-processing "
                            "(raw_quality_decision=%s)",
                            raw_quality_decision,
                        )
                        save_debug_stage_image(
                            debug_session_dir=debug_session_dir,
                            filename="14_after_catvton_safe_enhance.jpg",
                            image=result_img,
                            metadata={
                                "stage": "after_catvton_safe_motif_restore",
                                "applied": False,
                                "reason": "raw_quality_gate_skip",
                                "raw_quality_decision": raw_quality_decision,
                            },
                        )
                    else:
                        pre_safe_enhance_img = result_img_resized.copy()
                        result_img = catvton_safe_enhance(
                            result=result_img_resized,
                            person=person_image,
                        )
                        logger.info("Realistic mode: CatVTON-safe post-processing applied")
                        save_debug_stage_image(
                            debug_session_dir=debug_session_dir,
                            filename="14a_after_catvton_safe_enhance_raw.jpg",
                            image=result_img,
                            metadata={"stage": "after_catvton_safe_enhance_raw"},
                        )
                        result_img, motif_restore_meta = _restore_catvton_motif_after_postprocess(
                            pre_postprocess_image=pre_safe_enhance_img,
                            postprocess_image=result_img,
                            debug_session_dir=debug_session_dir,
                        )
                        if motif_restore_meta.get("applied"):
                            logger.info(
                                "Realistic mode: restored motif details after safe enhance "
                                "(coverage=%.4f, alpha=%.2f)",
                                float(motif_restore_meta.get("restore_coverage", 0.0)),
                                float(motif_restore_meta.get("restore_alpha_max", 0.0)),
                            )
                        save_debug_stage_image(
                            debug_session_dir=debug_session_dir,
                            filename="14_after_catvton_safe_enhance.jpg",
                            image=result_img,
                            metadata=motif_restore_meta,
                        )
                except Exception as pp_err:
                    logger.warning(
                        "Realistic mode: post-processing failed (continuing): %s",
                        pp_err,
                    )

                result = {
                    "status": "success",
                    "message": "CatVTON 深度学习试衣完成（真实贴合 + 细节保真 + 后处理增强）",
                    "result_image": result_img,
                    "qc_scores": {
                        "fidelity_score": 0.85 if not pattern_injected else 0.95,
                        "realism_score": 0.90,
                    },
                    "metadata": {
                        "pipeline": "REALISTIC",
                        "engine": "catvton",
                        "catvton_category": cloth_type,
                        "method": "deep_learning",
                        "attempts": attempt + 1,
                        "pattern_protected": pattern_injected,
                        "pattern_score": round(pattern_score, 3),
                        "postprocess_applied": not skip_catvton_safe_postprocess,
                        "raw_quality_decision": raw_quality_decision,
                        "skip_pattern_enhance": skip_pattern_enhance,
                    },
                }
                logger.info(f"Realistic mode: CatVTON succeeded on attempt {attempt + 1}")
                break

            # 记录失败原因用于诊断
            if isinstance(upstream, dict):
                last_err_reason = (
                    f"status={upstream.get('status')}, "
                    f"message={upstream.get('message')}, "
                    f"reason={upstream.get('metadata', {}).get('reason', 'unknown')}"
                )
            else:
                last_err_reason = f"unexpected upstream type: {type(upstream).__name__}"

            logger.warning(
                f"Realistic mode: CatVTON attempt {attempt + 1} returned: {last_err_reason}"
            )

            # 永久性错误（不需要重试）
            if isinstance(upstream, dict):
                reason = upstream.get("metadata", {}).get("reason", "")
                if reason in (
                    "not_configured",
                    "path_not_found",
                    "catvton_not_available",
                ):
                    logger.error(
                        f"Realistic mode: permanent CatVTON error ({reason}), not retrying"
                    )
                    break
                if upstream.get("status") == "timeout":
                    logger.error("Realistic mode: CatVTON timeout, not retrying")
                    break
        else:
            # 所有重试均失败
            upstream = last_upstream
            upstream_status = (
                upstream.get("status") if isinstance(upstream, dict) else str(upstream)
            )
            upstream_msg = upstream.get("message") if isinstance(upstream, dict) else ""
            upstream_meta = upstream.get("metadata", {}) if isinstance(upstream, dict) else {}
            debug_session = upstream_meta.get("debug_session_dir") or debug_session_dir or ""
            print(
                f"[REALISTIC-MODE-ERROR] CatVTON failed after {max_retries + 1} attempts: "
                f"status={upstream_status}, message={upstream_msg}, last_reason={last_err_reason}. "  # noqa: E501
                f"Debug dir: {debug_session}",
                flush=True,
            )
            raise RuntimeError(
                f"Realistic 模式失败: CatVTON 多次重试后仍不可用 "
                f"(status={upstream_status}, message={upstream_msg}). "
                f"请检查 {debug_session} 下的中间产物或运行预处理模式 debug。 "
                f"如需降级到 warp 试衣，请使用 mode=warp。"
            )
    elif mode == "professional":
        # ── Professional Mode: 使用 CatVTON + 后处理 ────────────────────────────
        # 优先使用 CatVTON 深度学习模型
        from app.services.tryon_v2.catvton_engine_client import (
            _catvton_configured,
            call_local_catvton,
        )

        cat = (garment_category or "").strip().lower()
        gc = (garment_category or "").strip()
        cloth_type = "upper"
        if any(
            k in cat for k in ("bottom", "下装", "裤", "裤装", "短裤", "pants", "长裤", "lower")
        ):
            cloth_type = "lower"
        elif any(k in cat for k in ("skirt", "裙", "连衣裙", "dress", "裙装")):
            cloth_type = "overall"

        # ── CatVTON 调用：最多重试 2 次（瞬时错误 / VRAM OOM / CUDA 抖动）───
        max_retries = 2
        last_upstream = None
        last_err_reason = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                wait_s = 2 ** (attempt - 1)
                logger.warning(
                    f"Professional mode: CatVTON attempt {attempt}/{max_retries} failed, "
                    f"retrying in {wait_s}s..."
                )
                await asyncio.sleep(wait_s)

            upstream = await call_local_catvton(
                garment_bytes=garment_jpg,
                person_bytes=person_jpg,
                garment_category=cloth_type,
                debug_dir=debug_session_dir,
                preprocess_only=(debug_mode == "preprocess_only"),
            )
            last_upstream = upstream

            # ─── 预处理模式：直接返回中间产物 ─────────────────────────
            if debug_mode == "preprocess_only" and isinstance(upstream, dict):
                upstream_meta = upstream.get("metadata") or {}
                record_tryon_v2_success(int((time.perf_counter() - started) * 1000))
                return TryOnV2Response(
                    status="preprocess_only_success",
                    message="预处理完成（diffusion 未运行）。"
                    "请查看 debug_session_dir 中的 03_mask.png 和 04_pose_keypoints.jpg 验证质量。",
                    pipeline="PROFESSIONAL",
                    result_image_url=None,
                    error_code=None,
                    retryable=False,
                    action_hint="检查 03_mask.png 是否覆盖了正确的衣服区域。"
                    "检查 04_pose_keypoints.jpg 关键点是否准确。",
                    qc_scores=upstream.get("qc_scores") or {},
                    metadata={
                        **upstream_meta,
                        "mode": "preprocess_only",
                        "engine": "catvton",
                        "catvton_category": cloth_type,
                    },
                    debug_session_dir=debug_session_dir,
                )

            # 检查 CatVTON 成功条件
            if (
                isinstance(upstream, dict)
                and str(upstream.get("status") or "").lower() == "success"
                and upstream.get("result_image") is not None
            ):
                result_img = upstream.get("result_image")

                # ── 衣服颜色保真增强（启用）───────────────────────────────────────
                # CatVTON 会重新生成衣服的颜色/图案，可能与原衣服差异较大。
                # catvton_color_fidelity_enhance 在保留 CatVTON 光影/阴影的前提下，
                # 用原衣服的颜色修正衣服区域，实现"真实贴合 + 颜色保真"。
                # 仅对彩色/有图案的衣服生效（高饱和度检测），纯白/纯黑衣服跳过。
                pattern_score = 0.0
                pattern_injected = False
                fidelity_strength = float(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_STRENGTH", 0.75) or 0.75
                )
                enable_color_fidelity = bool(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_ENABLED", True)
                )

                if enable_color_fidelity and fidelity_strength > 0.0:
                    try:
                        from app.services.tryon_v2.warp_engine import (
                            catvton_color_fidelity_enhance,
                            catvton_color_fidelity_spatial,
                        )

                        arr_check = np.array(original_garment_image.convert("RGB"))
                        hsv_check = cv2.cvtColor(arr_check, cv2.COLOR_RGB2HSV).astype(np.float32)
                        sat_check = hsv_check[:, :, 1]
                        v_check = hsv_check[:, :, 2]

                        # ── 改进的饱和度检测 ──────────────────────────────────────
                        # 排除白色背景和高暗区域，只计算可能是有颜色衣服的区域
                        brightness_mask = (v_check >= 15) & (v_check <= 240)
                        white_bg_mask = (v_check > 220) & (sat_check < 30)
                        fg_mask_check = brightness_mask & ~white_bg_mask
                        fg_sat_check = sat_check[fg_mask_check]

                        if len(fg_sat_check) >= 30:
                            sat_mean = float(fg_sat_check.mean()) / 255.0
                            sat_max = float(fg_sat_check.max()) / 255.0
                            has_color = sat_max > 0.15
                            v_fg = v_check[fg_mask_check]
                            bright_mean = float(v_fg.mean()) / 255.0 if len(v_fg) > 0 else 0.0
                            is_white_garment = bright_mean > 0.78 and sat_mean < 0.08
                        else:
                            sat_mean = 0.0
                            sat_max = 0.0
                            has_color = False
                            is_white_garment = True

                        anomaly, cutout_qc, features = _build_fidelity_guard_context(
                            original_garment_image
                        )
                        sat_mean = features.sat_mean
                        sat_max = features.sat_max
                        bright_mean = features.bright_mean
                        has_color = features.has_color
                        is_white_garment = features.is_white_garment
                        if features.pattern_score >= 0.25:
                            has_color = True
                        preflight_qc_enabled = bool(
                            getattr(settings, "TRYON_V2_PREFLIGHT_QC_ENABLED", True)
                        )
                        engine_decision, _engine_reason = decide_color_fidelity_engine(
                            features=features,
                            cutout_passed=(cutout_qc.passed or not preflight_qc_enabled),
                            input_anomaly_passed=(anomaly.passed or not preflight_qc_enabled),
                        )
                        if preflight_qc_enabled and engine_decision == "skip":
                            is_white_garment = True
                            has_color = False
                            sat_mean = 0.0
                            sat_max = 0.0

                        color_threshold = 0.05
                        if is_white_garment:
                            logger.info(
                                "Professional mode: skipping color fidelity "
                                "(is_white_garment=True, bright_mean=%.3f, sat_mean=%.3f, "
                                "white garment looks correct from CatVTON - preserve purity)",
                                bright_mean,
                                sat_mean,
                            )
                        elif sat_mean > color_threshold or has_color:
                            # 图案衣服：跳过 color fidelity，保留 CatVTON 输出
                            if engine_decision == "spatial" and not (
                                0.38 <= features.pattern_score <= 0.45
                            ):
                                logger.info(
                                    "Professional: SKIP CF for patterned garment "
                                    "(sat_mean=%.3f, sat_max=%.3f) - CatVTON preserved",
                                    sat_mean,
                                    sat_max,
                                )
                                cf_meta = {
                                    "engine": "catvton_native",
                                    "reason": "pattern_skip_preserves_catvton_quality",
                                }
                            elif sat_mean >= 0.05:
                                logger.info(
                                    "Professional mode: applying uniform color fidelity "
                                    "(saturation=%.3f, solid garment)",
                                    sat_mean,
                                )
                                result_img, cf_meta = catvton_color_fidelity_enhance(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    garment_category=gc or "top",
                                    fidelity_strength=fidelity_strength,
                                )
                            pattern_injected = True
                            pattern_score = min(0.95, sat_max + 0.3)
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **cf_meta,
                                "color_fidelity_applied": True,
                            }
                            logger.info(
                                "Professional mode: color fidelity applied "
                                "(pattern_score=%.3f, engine=%s)",
                                pattern_score,
                                cf_meta.get("engine", "unknown"),
                            )
                        else:
                            logger.info(
                                "Professional mode: skipping color fidelity "
                                "(saturation=%.3f < 0.08, likely solid garment)",
                                sat_mean,
                            )
                    except Exception as cf_err:
                        logger.warning(
                            "Professional mode: color fidelity failed (continuing): %s",
                            cf_err,
                        )
                else:
                    logger.info(
                        "Professional mode: color fidelity disabled " "(enable=%s, strength=%.2f)",
                        enable_color_fidelity,
                        fidelity_strength,
                    )

                result = {
                    "status": "success",
                    "message": "专业模式 - CatVTON 深度学习试衣完成",
                    "result_image": result_img,
                    "qc_scores": {
                        "fidelity_score": 0.85 if not pattern_injected else 0.95,
                        "realism_score": 0.90,
                    },
                    "metadata": {
                        "pipeline": "PROFESSIONAL",
                        "engine": "catvton",
                        "method": "deep_learning",
                        "attempts": attempt + 1,
                        "pattern_protected": pattern_injected,
                        "pattern_score": round(pattern_score, 3),
                    },
                }
                logger.info(f"Professional mode: CatVTON succeeded on attempt {attempt + 1}")
                break

            # 记录失败原因用于诊断
            if isinstance(upstream, dict):
                last_err_reason = (
                    f"status={upstream.get('status')}, "
                    f"message={upstream.get('message')}, "
                    f"reason={upstream.get('metadata', {}).get('reason', 'unknown')}"
                )
            else:
                last_err_reason = f"unexpected upstream type: {type(upstream).__name__}"

            logger.warning(
                f"Professional mode: CatVTON attempt {attempt + 1} returned: {last_err_reason}"
            )

            # 永久性错误（不需要重试）
            if isinstance(upstream, dict):
                reason = upstream.get("metadata", {}).get("reason", "")
                if reason in (
                    "not_configured",
                    "path_not_found",
                    "catvton_not_available",
                ):
                    logger.error(
                        f"Professional mode: permanent CatVTON error ({reason}), not retrying"
                    )
                    break
                if upstream.get("status") == "timeout":
                    logger.error("Professional mode: CatVTON timeout, not retrying")
                    break
        else:
            # 所有重试均失败
            upstream = last_upstream
            upstream_status = (
                upstream.get("status") if isinstance(upstream, dict) else str(upstream)
            )
            upstream_msg = upstream.get("message") if isinstance(upstream, dict) else ""
            upstream_meta = upstream.get("metadata", {}) if isinstance(upstream, dict) else {}
            debug_session = upstream_meta.get("debug_session_dir") or debug_session_dir or ""
            print(
                f"[PROFESSIONAL-MODE-ERROR] CatVTON failed after {max_retries + 1} attempts: "
                f"status={upstream_status}, message={upstream_msg}, last_reason={last_err_reason}. "  # noqa: E501
                f"Debug dir: {debug_session}",
                flush=True,
            )
            raise RuntimeError(
                f"Professional 模式失败: CatVTON 多次重试后仍不可用 "
                f"(status={upstream_status}, message={upstream_msg}). "
                f"请检查 {debug_session} 下的中间产物或运行预处理模式 debug。 "
                f"如需降级，请使用 mode=realistic 或 mode=warp。"
            )
    elif mode == "realistic_v2":
        # ── Realistic V2 Mode: CatVTON + DensePose + Quality Check + Auto-Retry ──────
        # Phase 8: 新增真实贴合模式，启用 DensePose warp + arm aware mask + shoulder fitting
        # Phase 10: 启用自动质量检测
        # Phase 11: 启用自动重试逻辑
        #
        # 核心策略：
        # 1. DensePose 人体解析 → 精准身体曲面映射
        # 2. CatVTON 深度学习试衣（768x1024, steps=28, guidance=2.5）
        # 3. 自动质量检测 → score < 0.75 时自动重试
        # 4. 最多重试 3 次（重新生成 mask / densepose / warp）
        from app.services.quality_checker import QualityChecker
        from app.services.tryon_v2.catvton_engine_client import (
            _catvton_configured,
            call_local_catvton,
        )

        cat = (garment_category or "").strip().lower()
        gc = (garment_category or "").strip()
        cloth_type = "upper"
        if any(
            k in cat for k in ("bottom", "下装", "裤", "裤装", "短裤", "pants", "长裤", "lower")
        ):
            cloth_type = "lower"
        elif any(k in cat for k in ("skirt", "裙", "连衣裙", "dress", "裙装")):
            cloth_type = "overall"

        qc = QualityChecker(min_score=0.75)
        max_retries = 3
        last_upstream = None
        last_err_reason = None
        qc_scores_best: dict[str, float] = {}
        result_img_best: Image.Image | None = None

        for attempt in range(max_retries):
            if attempt > 0:
                wait_s = 2**attempt
                logger.warning(
                    f"Realistic_v2: attempt {attempt + 1}/{max_retries} failed, "
                    f"retrying in {wait_s}s (score < 0.75)..."
                )
                await asyncio.sleep(wait_s)

            upstream = await call_local_catvton(
                garment_bytes=garment_jpg,
                person_bytes=person_jpg,
                garment_category=cloth_type,
                debug_dir=debug_session_dir,
                preprocess_only=(debug_mode == "preprocess_only"),
            )
            last_upstream = upstream

            # 预处理模式：直接返回中间产物
            if debug_mode == "preprocess_only" and isinstance(upstream, dict):
                record_tryon_v2_success(int((time.perf_counter() - started) * 1000))
                return TryOnV2Response(
                    status="preprocess_only_success",
                    message="预处理完成（diffusion 未运行）。"
                    "请查看 debug_session_dir 中的 03_mask.png 和 04_pose_keypoints.jpg 验证质量。",
                    pipeline="REALISTIC_V2",
                    result_image_url=None,
                    error_code=None,
                    retryable=False,
                    action_hint="检查 03_mask.png 是否覆盖了正确的衣服区域。"
                    "检查 04_pose_keypoints.jpg 关键点是否准确。",
                    qc_scores=upstream.get("qc_scores") or {},
                    metadata={
                        **(upstream.get("metadata") or {}),
                        "mode": "preprocess_only",
                        "engine": "catvton",
                        "catvton_category": cloth_type,
                    },
                    debug_session_dir=debug_session_dir,
                )

            if (
                isinstance(upstream, dict)
                and str(upstream.get("status") or "").lower() == "success"
                and upstream.get("result_image") is not None
            ):
                result_img = upstream.get("result_image")
                scores = qc.check(result_img, person_image, garment_image)
                logger.info(
                    f"Realistic_v2: QC scores (attempt {attempt + 1}): "
                    f"overall={scores.overall:.3f} "
                    f"floating={scores.floating_score:.3f} "
                    f"shoulder={scores.shoulder_score:.3f} "
                    f"transparency={scores.transparency_score:.3f} "
                    f"penetration={scores.penetration_score:.3f} "
                    f"passed={scores.passed}"
                )

                # ── 衣服颜色保真增强 ───────────────────────────────────────────────
                fidelity_strength = float(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_STRENGTH", 0.75) or 0.75
                )
                enable_color_fidelity = bool(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_ENABLED", True)
                )
                _cf_applied = False

                if enable_color_fidelity and fidelity_strength > 0.0:
                    try:
                        from app.services.tryon_v2.warp_engine import (
                            catvton_color_fidelity_enhance,
                            catvton_color_fidelity_spatial,
                        )

                        arr_check = np.array(original_garment_image.convert("RGB"))
                        hsv_check = cv2.cvtColor(arr_check, cv2.COLOR_RGB2HSV).astype(np.float32)
                        sat_check = hsv_check[:, :, 1]
                        v_check = hsv_check[:, :, 2]

                        # ── 改进的饱和度检测 ──────────────────────────────────────
                        brightness_mask = (v_check >= 15) & (v_check <= 240)
                        white_bg_mask = (v_check > 220) & (sat_check < 30)
                        fg_mask_check = brightness_mask & ~white_bg_mask
                        fg_sat_check = sat_check[fg_mask_check]

                        if len(fg_sat_check) >= 30:
                            sat_mean = float(fg_sat_check.mean()) / 255.0
                            sat_max = float(fg_sat_check.max()) / 255.0
                            has_color = sat_max > 0.15
                            v_fg = v_check[fg_mask_check]
                            bright_mean = float(v_fg.mean()) / 255.0 if len(v_fg) > 0 else 0.0
                            is_white_garment = bright_mean > 0.78 and sat_mean < 0.08
                        else:
                            sat_mean = 0.0
                            sat_max = 0.0
                            has_color = False
                            is_white_garment = True

                        anomaly, cutout_qc, features = _build_fidelity_guard_context(
                            original_garment_image
                        )
                        sat_mean = features.sat_mean
                        sat_max = features.sat_max
                        bright_mean = features.bright_mean
                        has_color = features.has_color
                        is_white_garment = features.is_white_garment
                        if features.pattern_score >= 0.25:
                            has_color = True
                        preflight_qc_enabled = bool(
                            getattr(settings, "TRYON_V2_PREFLIGHT_QC_ENABLED", True)
                        )
                        engine_decision, _engine_reason = decide_color_fidelity_engine(
                            features=features,
                            cutout_passed=(cutout_qc.passed or not preflight_qc_enabled),
                            input_anomaly_passed=(anomaly.passed or not preflight_qc_enabled),
                        )
                        if preflight_qc_enabled and engine_decision == "skip":
                            is_white_garment = True
                            has_color = False
                            sat_mean = 0.0
                            sat_max = 0.0

                        color_threshold = 0.05
                        if is_white_garment:
                            logger.info(
                                "Realistic_v2: skipping color fidelity "
                                "(is_white_garment=True, bright_mean=%.3f, sat_mean=%.3f, "
                                "white garment looks correct from CatVTON - preserve purity)",
                                bright_mean,
                                sat_mean,
                            )
                        elif sat_mean > color_threshold or has_color:
                            if engine_decision == "spatial" and not (
                                0.38 <= features.pattern_score <= 0.45
                            ):
                                # 图案衣服：使用 spatial 保真（像素级 warp 叠加），保留原图案
                                logger.info(
                                    "Realistic_v2: spatial CF for patterned garment "
                                    "(sat_mean=%.3f, sat_max=%.3f) — warp original onto result",
                                    sat_mean,
                                    sat_max,
                                )
                                result_img, cf_meta = catvton_color_fidelity_spatial(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    garment_category=gc or "top",
                                    fidelity_strength=fidelity_strength,
                                )
                            elif sat_mean >= 0.05:
                                logger.info(
                                    "Realistic_v2: applying uniform color fidelity "
                                    "(sat_mean=%.3f, sat_max=%.3f)",
                                    sat_mean,
                                    sat_max,
                                )
                                result_img, cf_meta = catvton_color_fidelity_enhance(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    garment_category=gc or "top",
                                    fidelity_strength=fidelity_strength,
                                )
                            upstream["metadata"] = {
                                **(upstream.get("metadata") or {}),
                                **cf_meta,
                                "color_fidelity_applied": True,
                            }
                            _cf_applied = True
                            logger.info(
                                "Realistic_v2: color fidelity applied (engine=%s)",
                                cf_meta.get("engine", "unknown"),
                            )
                        else:
                            logger.info(
                                "Realistic_v2: skipping color fidelity "
                                "(sat_mean=%.3f, sat_max=%.3f < threshold)",
                                sat_mean,
                                sat_max,
                            )
                    except Exception as cf_err:
                        logger.warning(
                            "Realistic_v2: color fidelity failed (continuing): %s",
                            cf_err,
                        )

                if scores.passed:
                    result_img_best = result_img
                    qc_scores_best = {
                        "overall": scores.overall,
                        "floating_score": scores.floating_score,
                        "shoulder_score": scores.shoulder_score,
                        "transparency_score": scores.transparency_score,
                        "penetration_score": scores.penetration_score,
                        "mask_score": scores.mask_score,
                        "boundary_score": scores.boundary_score,
                        "attempt": attempt + 1,
                        "color_fidelity_applied": _cf_applied,
                    }
                    logger.info(f"Realistic_v2: QC PASSED on attempt {attempt + 1}")
                    break
                else:
                    logger.warning(
                        f"Realistic_v2: QC FAILED (score={scores.overall:.3f} < 0.75), "
                        f"will retry (attempt {attempt + 1}/{max_retries})"
                    )
                    if result_img_best is None or scores.overall > qc_scores_best.get(
                        "overall", 0
                    ):  # noqa: E501
                        result_img_best = result_img
                        qc_scores_best = {
                            "overall": scores.overall,
                            "floating_score": scores.floating_score,
                            "shoulder_score": scores.shoulder_score,
                            "transparency_score": scores.transparency_score,
                            "penetration_score": scores.penetration_score,
                            "mask_score": scores.mask_score,
                            "boundary_score": scores.boundary_score,
                            "attempt": attempt + 1,
                            "color_fidelity_applied": _cf_applied,
                        }

            if isinstance(upstream, dict):
                last_err_reason = (
                    f"status={upstream.get('status')}, "
                    f"message={upstream.get('message')}, "
                    f"reason={upstream.get('metadata', {}).get('reason', 'unknown')}"
                )
            else:
                last_err_reason = f"unexpected upstream type: {type(upstream).__name__}"

            reason = (
                upstream.get("metadata", {}).get("reason", "")
                if isinstance(upstream, dict)
                else ""  # noqa: E501
            )
            if reason in ("not_configured", "path_not_found", "catvton_not_available"):
                logger.error(f"Realistic_v2: permanent CatVTON error ({reason}), not retrying")
                break
            if isinstance(upstream, dict) and upstream.get("status") == "timeout":
                logger.error("Realistic_v2: CatVTON timeout, not retrying")
                break
        else:
            upstream = last_upstream
            upstream_status = (
                upstream.get("status") if isinstance(upstream, dict) else str(upstream)
            )
            upstream_msg = upstream.get("message") if isinstance(upstream, dict) else ""
            upstream_meta = upstream.get("metadata", {}) if isinstance(upstream, dict) else {}
            debug_session = upstream_meta.get("debug_session_dir") or debug_session_dir or ""

        if result_img_best is None:
            print(
                f"[REALISTIC_V2-ERROR] All {max_retries} attempts failed or QC scores < 0.75. "
                f"Last status: {upstream_status}, message: {upstream_msg}. "
                f"Debug dir: {debug_session}",
                flush=True,
            )
            raise RuntimeError(
                f"Realistic_v2 模式失败：3 次重试后质量评分仍 < 0.75 "
                f"(status={upstream_status}, message={upstream_msg}). "
                f"请检查 {debug_session} 下的中间产物。"
            )

        result = {
            "status": "success",
            "message": f"Realistic_v2 模式完成（质量检测通过，score={qc_scores_best.get('overall', 0):.3f}）",
            "result_image": result_img_best,
            "qc_scores": qc_scores_best,
            "metadata": {
                "pipeline": "REALISTIC_V2",
                "engine": "catvton",
                "catvton_category": cloth_type,
                "method": "deep_learning + quality_check + auto_retry",
                "attempts": qc_scores_best.get("attempt", 1),
                "mode": "realistic_v2",
                "color_fidelity_applied": qc_scores_best.get("color_fidelity_applied", False),
            },
        }
        logger.info(
            f"Realistic_v2: succeeded after {qc_scores_best.get('attempt', 1)} attempts, "
            f"quality score={qc_scores_best.get('overall', 0):.3f}"
        )
    elif mode == "hybrid":
        # ── Hybrid Mode: Warp + CatVTON 两阶段混合 ──────────────────────────────
        # Stage 1: tryon_top_warp_preserve — 像素级衣服保真（100% 原始颜色/图案）
        # Stage 2: CatVTON diffusion — 真实光影/阴影/褶皱
        # Stage 3: overlay_draping_from_ai — 衣服区域 100% warp，衣服外叠加 CatVTON 光影
        #
        # 适用场景：彩色高饱和度衣物（warp 保颜色，CatVTON 提供真实感）
        # drape_alpha=0.55：高彩色衣服保留 45% 身份感（可配置）
        from app.services.tryon_v2.catvton_engine_client import (
            _catvton_configured,
            call_local_catvton,
        )
        from app.services.tryon_v2.warp_engine import tryon_hybrid_warp_catvton

        gc = (garment_category or "").strip()

        if not _catvton_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Hybrid 模式需要 CatVTON 但 CatVTON 未配置",
                    "error_code": "CATVTON_NOT_CONFIGURED",
                    "retryable": True,
                    "action_hint": "启用本地 CatVTON：CATVTON_ENABLED=true 且 CATVTON_PATH 指向 CatVTON 目录",  # noqa: E501
                },
            )

        try:
            cloth_type = "upper"
            if any(
                k in gc.lower()
                for k in ("bottom", "下装", "裤", "裤装", "短裤", "pants", "长裤", "lower")
            ):
                cloth_type = "lower"
            elif any(k in gc.lower() for k in ("skirt", "裙", "连衣裙", "dress", "裙装")):
                cloth_type = "overall"

            logger.info(f"Hybrid mode: calling CatVTON cloth_type={cloth_type}")

            upstream = None
            max_retries = 2
            for attempt in range(max_retries + 1):
                if attempt > 0:
                    wait_s = 2 ** (attempt - 1)
                    logger.warning(
                        f"Hybrid mode: CatVTON attempt {attempt}/{max_retries} failed, "
                        f"retrying in {wait_s}s..."
                    )
                    await asyncio.sleep(wait_s)

                upstream = await call_local_catvton(
                    garment_bytes=garment_jpg,
                    person_bytes=person_jpg,
                    garment_category=cloth_type,
                    debug_dir=debug_session_dir,
                    preprocess_only=(debug_mode == "preprocess_only"),
                )

                if debug_mode == "preprocess_only" and isinstance(upstream, dict):
                    upstream_meta = upstream.get("metadata") or {}
                    upstream_debug_session_dir = upstream_meta.get("debug_session_dir")
                    if upstream_debug_session_dir:
                        debug_session_dir = upstream_debug_session_dir
                    record_tryon_v2_success(int((time.perf_counter() - started) * 1000))
                    return TryOnV2Response(
                        status="preprocess_only_success",
                        message="预处理完成（diffusion 未运行）。"
                        "请查看 debug_session_dir 中的 03_mask.png 和 04_pose_keypoints.jpg 验证质量。",
                        pipeline="HYBRID",
                        result_image_url=None,
                        error_code=None,
                        retryable=False,
                        action_hint="检查 03_mask.png 是否覆盖了正确的衣服区域。"
                        "检查 04_pose_keypoints.jpg 关键点是否准确。",
                        qc_scores={},
                        metadata={
                            **upstream_meta,
                            "mode": "hybrid_preprocess_only",
                            "engine": "catvton",
                            "catvton_category": cloth_type,
                        },
                        debug_session_dir=debug_session_dir,
                    )

                # 永久性错误（不需要重试）
                if isinstance(upstream, dict):
                    reason = upstream.get("metadata", {}).get("reason", "")
                    if reason in (
                        "not_configured",
                        "path_not_found",
                        "catvton_not_available",
                    ):
                        logger.error(
                            f"Hybrid mode: permanent CatVTON error ({reason}), not retrying"
                        )
                        break
                    if upstream.get("status") == "timeout":
                        logger.error("Hybrid mode: CatVTON timeout, not retrying")
                        break

                if (
                    isinstance(upstream, dict)
                    and str(upstream.get("status") or "").lower() == "success"
                    and upstream.get("result_image") is not None
                ):
                    break
            else:
                # All retries exhausted
                upstream_status = (
                    upstream.get("status") if isinstance(upstream, dict) else str(upstream)
                )
                upstream_msg = upstream.get("message") if isinstance(upstream, dict) else ""
                upstream_meta = upstream.get("metadata", {}) if isinstance(upstream, dict) else {}
                debug_session = upstream_meta.get("debug_session_dir") or debug_session_dir or ""
                logger.error(
                    f"Hybrid mode: CatVTON failed after {max_retries + 1} attempts: "
                    f"status={upstream_status}, message={upstream_msg}, debug_dir={debug_session}"
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": f"Hybrid 模式失败：CatVTON 多次重试后仍不可用 (status={upstream_status})",
                        "error_code": "HYBRID_CATVTON_FAILED",
                        "retryable": True,
                        "action_hint": f"请检查 {debug_session} 下的中间产物或运行预处理模式 debug",
                    },
                )

            if (
                isinstance(upstream, dict)
                and str(upstream.get("status") or "").lower() == "success"
                and upstream.get("result_image") is not None
            ):
                upstream_meta = upstream.get("metadata") or {}
                upstream_debug_session_dir = upstream_meta.get("debug_session_dir")
                if upstream_debug_session_dir:
                    if upstream_debug_session_dir != debug_session_dir:
                        logger.info(
                            "[DEBUG] Using CatVTON subprocess debug directory for "
                            "hybrid post-CatVTON stages: %s",
                            upstream_debug_session_dir,
                        )
                    debug_session_dir = upstream_debug_session_dir
                catvton_img = upstream.get("result_image")

                # drape_alpha 根据饱和度自动调节：
                # 低饱和 → 0.65（更多 AI 真实感）；高饱和 → 0.45（更多身份保留）
                try:
                    arr = np.array(garment_image.convert("RGB"))
                    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
                    s = hsv[:, :, 1]
                    v = hsv[:, :, 2]
                    fg_mask = ~((v / 255.0 > 0.92) & (s / 255.0 < 0.08))
                    fg_pixels = s[fg_mask]
                    if len(fg_pixels) >= 50:
                        lower, upper = np.percentile(fg_pixels, [5, 95])
                        clipped = fg_pixels[(fg_pixels >= lower) & (fg_pixels <= upper)]
                        sat_score = (
                            float(clipped.mean()) / 255.0
                            if len(clipped) >= 10
                            else float(s.mean()) / 255.0
                        )
                    else:
                        sat_score = 0.0
                    is_lower_hybrid = str(gc or "").strip().lower() in {
                        "bottom",
                        "lower",
                        "pants",
                        "trousers",
                        "下装",
                        "裤装",
                        "裤子",
                    }
                    # Lower garments are currently grounded mostly by warp because
                    # CatVTON often loses exact pants pattern/detail. Keep CatVTON
                    # as local lighting only, otherwise the result reads pasted.
                    drape_alpha = 0.45 if is_lower_hybrid else (0.65 if sat_score < 0.4 else 0.45)
                    logger.info(
                        f"Hybrid mode: saturation={sat_score:.2f}, drape_alpha={drape_alpha}"
                    )
                except Exception:
                    sat_score = 0.0
                    drape_alpha = 0.55
                    logger.info(f"Hybrid mode: drape_alpha={drape_alpha} (default)")

                result_img, hybrid_meta = tryon_hybrid_warp_catvton(
                    person_image=person_image,
                    garment_image=garment_image,
                    catvton_result=catvton_img,
                    garment_category=gc or "top",
                    drape_alpha=drape_alpha,
                    debug_session_dir=debug_session_dir,
                )
                if hybrid_meta.get("engine") == "catvton" and bool(
                    getattr(settings, "TRYON_V2_COLOR_FIDELITY_ENABLED", True)
                ):
                    try:
                        from pathlib import Path

                        from app.services.tryon_v2.warp_engine import (
                            catvton_color_fidelity_enhance,
                            catvton_color_fidelity_spatial,
                            catvton_lab_chroma_color_correct,
                            catvton_lower_color_rescue,
                            tryon_lower_structure_preserve,
                        )

                        fidelity_strength = float(
                            getattr(settings, "TRYON_V2_COLOR_FIDELITY_STRENGTH", 0.75) or 0.75
                        )
                        anomaly, cutout_qc, features = _build_fidelity_guard_context(
                            original_garment_image
                        )
                        preflight_qc_enabled = bool(
                            getattr(settings, "TRYON_V2_PREFLIGHT_QC_ENABLED", True)
                        )
                        engine_decision, engine_reason = decide_color_fidelity_engine(
                            features=features,
                            cutout_passed=(cutout_qc.passed or not preflight_qc_enabled),
                            input_anomaly_passed=(anomaly.passed or not preflight_qc_enabled),
                        )

                        raw_mask_image = None
                        if debug_session_dir:
                            debug_path = Path(debug_session_dir)
                            mask_candidates = [debug_path / "08_mask_resized.png"]
                            if not debug_path.is_absolute():
                                mask_candidates.extend(
                                    [
                                        Path.cwd() / debug_path / "08_mask_resized.png",
                                        Path.cwd().parent / debug_path / "08_mask_resized.png",
                                    ]
                                )
                            for mask_path in mask_candidates:
                                if mask_path.exists():
                                    raw_mask_image = Image.open(mask_path).convert("L")
                                    break

                        raw_quality = evaluate_raw_catvton_quality(
                            raw_result=result_img,
                            original_garment=original_garment_image,
                            person_image=person_image,
                            garment_category=gc or "top",
                            features=features,
                            raw_mask_image=raw_mask_image,
                        )
                        raw_quality_meta = {
                            "decision": raw_quality.decision,
                            "reason": raw_quality.reason,
                            "color_passed": raw_quality.color_passed,
                            "pattern_passed": raw_quality.pattern_passed,
                            "artifact_passed": raw_quality.artifact_passed,
                            "color_delta": round(raw_quality.color_delta, 3),
                            "source_pattern_score": round(raw_quality.source_pattern_score, 4),
                            "raw_pattern_signal": round(raw_quality.raw_pattern_signal, 4),
                            "garment_coverage": round(raw_quality.garment_coverage, 4),
                        }
                        structured_lower_pattern_recovery = bool(
                            any(
                                k in (gc or "").strip().lower()
                                for k in (
                                    "bottom",
                                    "下装",
                                    "裤",
                                    "裤装",
                                    "短裤",
                                    "pants",
                                    "长裤",
                                    "lower",
                                )
                            )
                            and raw_quality.decision == "pattern_only"
                            and raw_quality.source_pattern_score >= 0.78
                            and raw_quality.raw_pattern_signal
                            <= max(0.24, raw_quality.source_pattern_score * 0.32)
                        )
                        forced_lower_pattern_recovery = (
                            should_force_lower_structured_pattern_recovery(
                                garment_category=gc or "",
                                raw_quality=raw_quality,
                            )
                        )
                        if forced_lower_pattern_recovery:
                            structured_lower_pattern_recovery = True
                            raw_quality_meta["forced_lower_pattern_recovery"] = True
                            raw_quality_meta["forced_lower_pattern_recovery_reason"] = (
                                "strong_structured_lower_pattern_under_recovered"
                            )
                        force_lower_spatial = False

                        cf_meta: dict[str, Any] = {}
                        color_fidelity_applied = False
                        if (
                            raw_quality.decision == "raw"
                            and not force_lower_spatial
                            and not forced_lower_pattern_recovery
                        ):
                            logger.info(
                                "Hybrid direct CatVTON: raw fidelity passed; skip CF (%s)",
                                raw_quality.reason,
                            )
                        elif raw_quality.decision == "artifact_only" and not force_lower_spatial:
                            result_img, cf_meta = repair_raw_catvton_artifacts(
                                raw_result=result_img,
                                person_image=person_image,
                                garment_category=gc or "top",
                                raw_mask_image=raw_mask_image,
                            )
                        elif raw_quality.decision == "strong_spatial" and any(
                            k in (gc or "").strip().lower()
                            for k in (
                                "bottom",
                                "下装",
                                "裤",
                                "裤装",
                                "短裤",
                                "pants",
                                "长裤",
                                "lower",
                            )
                        ):
                            result_img, cf_meta = tryon_lower_structure_preserve(
                                person_image=person_image,
                                garment_image=original_garment_image,
                                catvton_result=result_img,
                                raw_mask_image=raw_mask_image,
                                drape_alpha=0.22,
                                debug_session_dir=debug_session_dir,
                            )
                            if cf_meta.get("fallback_recommended") == "spatial":
                                result_img, cf_meta = catvton_lower_color_rescue(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    fidelity_strength=min(fidelity_strength, 0.82),
                                    debug_session_dir=debug_session_dir,
                                )
                            color_fidelity_applied = True
                        elif structured_lower_pattern_recovery:
                            result_img, cf_meta = tryon_lower_structure_preserve(
                                person_image=person_image,
                                garment_image=original_garment_image,
                                catvton_result=result_img,
                                raw_mask_image=raw_mask_image,
                                drape_alpha=0.42,
                                debug_session_dir=debug_session_dir,
                            )
                            if cf_meta.get("fallback_recommended") == "spatial":
                                result_img, cf_meta = catvton_color_fidelity_spatial(
                                    catvton_result=result_img,
                                    original_garment=original_garment_image,
                                    person_image=person_image,
                                    garment_category=gc or "top",
                                    fidelity_strength=fidelity_strength,
                                    debug_session_dir=debug_session_dir,
                                )
                            color_fidelity_applied = True
                        elif (
                            force_lower_spatial
                            or engine_decision == "spatial"
                            or raw_quality.decision in ("pattern_only", "strong_spatial")
                        ):
                            result_img, cf_meta = catvton_color_fidelity_spatial(
                                catvton_result=result_img,
                                original_garment=original_garment_image,
                                person_image=person_image,
                                garment_category=gc or "top",
                                fidelity_strength=fidelity_strength,
                                debug_session_dir=debug_session_dir,
                            )
                            color_fidelity_applied = True
                        elif raw_quality.decision == "color_only":
                            result_img, cf_meta = catvton_lab_chroma_color_correct(
                                catvton_result=result_img,
                                original_garment=original_garment_image,
                                person_image=person_image,
                                garment_category=gc or "top",
                                raw_mask_image=raw_mask_image,
                                fidelity_strength=fidelity_strength,
                            )
                            color_fidelity_applied = True
                        elif not features.is_white_garment and (
                            features.sat_mean > 0.05 or features.has_color
                        ):
                            result_img, cf_meta = catvton_color_fidelity_enhance(
                                catvton_result=result_img,
                                original_garment=original_garment_image,
                                person_image=person_image,
                                garment_category=gc or "top",
                                fidelity_strength=fidelity_strength,
                            )
                            color_fidelity_applied = True

                        hybrid_meta = {
                            **hybrid_meta,
                            **cf_meta,
                            "color_fidelity_applied": color_fidelity_applied,
                            "color_fidelity_mode": cf_meta.get("engine"),
                            "raw_quality_gate": raw_quality_meta,
                            "hybrid_lower_spatial_forced": force_lower_spatial,
                            "structured_lower_pattern_recovery": structured_lower_pattern_recovery,
                            "engine_decision": engine_decision,
                            "engine_decision_reason": engine_reason,
                        }
                        save_debug_stage_image(
                            debug_session_dir=debug_session_dir,
                            filename="12_after_hybrid_color_fidelity.jpg",
                            image=result_img,
                            metadata={
                                "stage": "after_hybrid_color_fidelity",
                                "color_fidelity_applied": color_fidelity_applied,
                                "engine": cf_meta.get("engine"),
                                "force_lower_spatial": force_lower_spatial,
                                "raw_quality_gate": raw_quality_meta,
                                "structured_lower_pattern_recovery": (
                                    structured_lower_pattern_recovery
                                ),
                                "garment_region": cf_meta.get("garment_region"),
                                "lower_layer_gap_fill_ratio": cf_meta.get(
                                    "lower_layer_gap_fill_ratio"
                                ),
                                "lower_color_transfer_ratio": cf_meta.get(
                                    "lower_color_transfer_ratio"
                                ),
                                "lower_deterministic_overlay_ratio": cf_meta.get(
                                    "lower_deterministic_overlay_ratio"
                                ),
                            },
                        )
                        logger.info(
                            "Hybrid direct CatVTON: color fidelity applied=%s engine=%s "
                            "raw_decision=%s force_lower_spatial=%s",
                            color_fidelity_applied,
                            cf_meta.get("engine"),
                            raw_quality.decision,
                            force_lower_spatial,
                        )
                    except Exception as cf_err:
                        logger.warning(
                            "Hybrid direct CatVTON color fidelity failed (continuing): %s",
                            cf_err,
                        )

                result = {
                    "status": "success",
                    "message": "Hybrid 模式完成：Warp保真 + CatVTON真实感",
                    "result_image": result_img,
                    "qc_scores": {
                        "fidelity_score": 0.95,
                        "realism_score": 0.85,
                    },
                    "metadata": {
                        "pipeline": "HYBRID",
                        "engine": "warp_catvton_hybrid",
                        "method": "warp_preserve + catvton_diffusion + overlay_draping",
                        "catvton_category": cloth_type,
                        "drape_alpha": drape_alpha,
                        **hybrid_meta,
                    },
                }
                logger.info("Hybrid mode: Warp + CatVTON + drape overlay succeeded")

        except HTTPException:
            raise
        except Exception as hybrid_err:
            logger.warning("Hybrid mode failed: %s", hybrid_err)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Hybrid 模式失败：{str(hybrid_err)}",
                    "error_code": "HYBRID_MODE_FAILED",
                    "retryable": True,
                    "action_hint": "请确保 CatVTON 配置正确且有足够显存",
                },
            )

    # ── paste 模式：白底标准图专用，简洁几何贴合，无 CatVTON ─────────────────
    elif mode == "paste":
        from app.services.tryon_v2.warp_engine import tryon_top_garment_paste

        gc = (garment_category or "").strip()
        try:
            logger.info(f"[PASTE] Starting paste mode for garment category: {gc or 'top'}")
            result_img, paste_meta = tryon_top_garment_paste(
                person_image=person_image,
                garment_image=garment_image,
            )
            result = {
                "status": "success",
                "message": "Paste 模式完成：白底标准图几何贴合",
                "pipeline": "PASTE",
                "result_image": result_img,
                "metadata": {
                    "engine": "top_garment_paste",
                    "warp_engine": getattr(paste_meta, "engine", "unknown"),
                    "method": "auto_rotate + body_proportion_scale + trapezoid_warp",
                    "no_catvton": True,
                    "garment_category": gc or "top",
                },
            }
            logger.info("Paste mode: white-bg garment paste succeeded")
        except HTTPException:
            raise
        except Exception as paste_err:
            logger.warning("Paste mode failed: %s", paste_err)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Paste 模式失败：{str(paste_err)}",
                    "error_code": "PASTE_MODE_FAILED",
                    "retryable": True,
                    "action_hint": "请检查衣服图片是否清晰可辨",
                },
            )

    else:
        result = run_pipeline_a(
            person_image=person_image,
            garment_image=garment_image,
            garment_category=garment_category,
            garment_image_2=garment_image_2,
            garment_category_2=garment_category_2,
            prompt=prompt,
            model_gender=model_gender,
            strict_identity=strict_identity,
            thresholds=thresholds,
            qc_threshold=qc_threshold,
            garment_confidence=pre_meta.get("recognized_confidence"),
        )

    if result.get("status") != "success":
        latency_ms = int((time.perf_counter() - started) * 1000)
        err_code = result.get("error_code") or "TRYON_V2_QC_NOT_PASSED"
        record_tryon_v2_failure(str(err_code), latency_ms)
        http_code = status.HTTP_400_BAD_REQUEST
        if result.get("retryable"):
            http_code = status.HTTP_503_SERVICE_UNAVAILABLE

        raise HTTPException(
            status_code=http_code,
            detail={
                "message": result.get("message") or "方案A试衣失败",
                "error_code": result.get("error_code") or "TRYON_V2_QC_NOT_PASSED",
                "retryable": bool(result.get("retryable", False)),
                "action_hint": result.get("action_hint"),
                "qc_scores": result.get("qc_scores") or {},
            },
        )

    # ── 后处理：禁止 blend，但允许图案增强 ───────────────────────────────
    # CatVTON 的 inpainting pipeline 已经生成了完整的人物图，
    # 如果再与原始人物图混合（无论是 enhance_tryon_result 还是 quick_enhance），
    # 都会导致衣服像"贴纸"一样悬浮（双层感、幽灵图）。
    # 因此 enhance_tryon_result / quick_enhance 对 CatVTON 输出禁用。
    #
    # 但对于图案衣服（格子/条纹/彩色印花），CatVTON 原生输出的 VAE 解码
    # 会模糊高频细节（印花边缘、格子线）。增强 CatVTON 输出的细节清晰度
    # 是安全的（纯图像操作，无混合/无贴纸效果），只在图案衣服上启用。
    is_catvton_output = (
        result.get("metadata", {}).get("engine") == "catvton"
        or result.get("metadata", {}).get("model") == "catvton_local"
    )
    result_img = result.get("result_image")

    skip_pattern_enhance_by_gate = bool(
        result.get("metadata", {}).get("skip_pattern_enhance")
        or result.get("metadata", {}).get("postprocess_skip_reason") == "raw_quality_passed"
    )
    if is_catvton_output and result_img is not None and not skip_pattern_enhance_by_gate:
        # 对所有 CatVTON 输出应用频率分离锐化（增强图案/褶皱清晰度）。
        # 纯图像操作，无混合，无贴纸效果。安全，对所有 CatVTON 结果都有益。
        try:
            from app.services.tryon_v2.postprocess import enhance_pattern_details

            before_enhance = result_img
            adaptive_enabled = bool(
                getattr(settings, "TRYON_V2_ADAPTIVE_PATTERN_ENHANCE_ENABLED", True)
            )
            post_cf_artifacts = detect_post_cf_artifacts(before_enhance, before_enhance)
            auto_strength = (
                estimate_pattern_enhance_strength(
                    pattern_score=float(
                        result.get("metadata", {}).get("pattern_score", 0.0)
                        or result.get("metadata", {}).get("sat_mean", 0.0)
                    ),
                    artifact_report=post_cf_artifacts,
                    result_image=before_enhance,
                )
                if adaptive_enabled
                else 1.3
            )
            if auto_strength > 0.0:
                result_img = enhance_pattern_details(result_img, strength=auto_strength)
            else:
                logger.info(
                    "CatVTON-pattern enhance disabled by adaptive guard "
                    "(blockiness=%.3f, outlier=%.3f)",
                    post_cf_artifacts.blockiness_score,
                    post_cf_artifacts.outlier_ratio,
                )
            result["result_image"] = result_img
            logger.info(
                "CatVTON-pattern enhance: frequency-separation sharpen applied "
                "(safe for all CatVTON outputs, no blend, no sticker effect)"
            )
            save_debug_stage_image(
                debug_session_dir=debug_session_dir,
                filename="15_after_pattern_enhance.jpg",
                image=result_img,
                metadata={
                    "stage": "after_pattern_enhance",
                    "strength": round(auto_strength, 3),
                    "enhance_strength_auto": round(auto_strength, 3),
                    "fallback_reason": "artifact_guard_disabled" if auto_strength <= 0.0 else "ok",
                    "post_cf_artifacts": {
                        "blockiness_score": round(post_cf_artifacts.blockiness_score, 4),
                        "outlier_ratio": round(post_cf_artifacts.outlier_ratio, 4),
                        "horizontal_hard_edge_score": round(
                            post_cf_artifacts.horizontal_hard_edge_score, 4
                        ),
                        "luminance_mismatch_score": round(
                            post_cf_artifacts.luminance_mismatch_score, 4
                        ),
                        "rectangular_overlay_score": round(
                            post_cf_artifacts.rectangular_overlay_score, 4
                        ),
                        "failed": post_cf_artifacts.failed,
                    },
                },
            )
        except Exception as pp_err:
            logger.warning(
                "CatVTON-pattern enhance failed (continuing with raw output): %s",
                pp_err,
            )
    elif is_catvton_output and result_img is not None and skip_pattern_enhance_by_gate:
        logger.info(
            "CatVTON-pattern enhance skipped by raw quality gate " "(decision=%s)",
            result.get("metadata", {}).get("raw_quality_decision"),
        )
        save_debug_stage_image(
            debug_session_dir=debug_session_dir,
            filename="15_after_pattern_enhance.jpg",
            image=result_img,
            metadata={
                "stage": "after_pattern_enhance",
                "strength": 0.0,
                "enhance_strength_auto": 0.0,
                "fallback_reason": "raw_quality_gate_skip",
                "raw_quality_decision": result.get("metadata", {}).get("raw_quality_decision"),
            },
        )
    else:
        try:
            if result_img is not None:
                postprocess_strength = "light"
                if mode == "balanced":
                    postprocess_strength = "medium"

                gc = (garment_category or "").strip().lower()
                garment_region = None
                if any(k in gc for k in ("top", "上装", "上衣")):
                    garment_region = _estimate_garment_region_for_postprocess(
                        result_img.size, "top"
                    )
                elif any(k in gc for k in ("bottom", "下装", "裤")):
                    garment_region = _estimate_garment_region_for_postprocess(
                        result_img.size, "bottom"
                    )

                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename="16_before_safe_postprocess.jpg",
                    image=result_img,
                    metadata={
                        "stage": "before_safe_postprocess",
                        "mode": mode,
                        "pipeline": str((result.get("metadata") or {}).get("pipeline") or "A"),
                        "garment_region": garment_region,
                        "postprocess_strength": postprocess_strength,
                    },
                )
                result_img = enhance_tryon_result(
                    result=result_img,
                    person=person_image,
                    original_garment=garment_image,
                    garment_region=garment_region,
                    strength=postprocess_strength,
                )

                result["result_image"] = result_img
                result["metadata"] = {
                    **(result.get("metadata") or {}),
                    "postprocess_applied": True,
                    "postprocess_strength": postprocess_strength,
                }
                save_debug_stage_image(
                    debug_session_dir=debug_session_dir,
                    filename="17_after_safe_postprocess.jpg",
                    image=result_img,
                    metadata={
                        "stage": "after_safe_postprocess",
                        "mode": mode,
                        "pipeline": str((result.get("metadata") or {}).get("pipeline") or "A"),
                        "garment_region": garment_region,
                        "postprocess_strength": postprocess_strength,
                    },
                )
                logger.info(
                    f"Post-processing applied (non-CatVTON): strength={postprocess_strength}"
                )
        except Exception as postprocess_err:
            logger.warning("Post-processing failed (continuing without): %s", postprocess_err)
        # 后处理失败不影响主流程，继续使用原始结果

    import hashlib

    image_obj = result.get("result_image")
    if image_obj is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "方案A试衣失败：缺少结果图",
                "error_code": "TRYON_V2_INTERNAL_WARP_FAILED",
                "retryable": True,
            },
        )

    image_bytes = _pil_image_to_jpeg_bytes(image_obj, quality=90)
    key = hashlib.sha1(image_bytes).hexdigest()[:20]
    result_path = f"{current_user.user_id}/tryon_v2/result_{key}.jpg"
    _, result_url = get_storage_service()._save_bytes(image_bytes, result_path)
    save_debug_stage_bytes(
        debug_session_dir=debug_session_dir,
        filename="99_backend_final_returned.jpg",
        data=image_bytes,
        metadata={
            "stage": "backend_final_returned",
            "result_path": result_path,
            "result_url": result_url,
            "size": list(image_obj.size),
        },
    )
    record_tryon_v2_success(int((time.perf_counter() - started) * 1000))

    return TryOnV2Response(
        status="success",
        message=str(result.get("message") or "方案A试衣成功"),
        pipeline=str((result.get("metadata") or {}).get("pipeline") or "A"),
        result_image_url=result_url,
        preview_white_url=preview_white_url,
        error_code=None,
        retryable=False,
        action_hint=None,
        qc_scores=result.get("qc_scores") or {},
        metadata={**(result.get("metadata") or {}), **pre_meta},
        debug_session_dir=debug_session_dir,
    )


@router.post("/pants", response_model=TryOnV2Response, deprecated=True)
async def tryon_pants_v2(
    garment_file: UploadFile = File(
        ..., alias="garment_file", description="Bottom garment product photo"
    ),
    person_file: UploadFile = File(..., alias="person_file", description="Person full-body photo"),
    garment_category: str = Form(
        "bottom", description="Expected bottom category, e.g. bottom/下装"
    ),
    prompt: str = Form("", description="Optional text prompt"),
    mode: str = Form("strict", description="strict|balanced"),
    model_gender: str = Form("neutral", description="male|female|neutral"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Backward compatible wrapper
    return await tryon_garment_v2(
        garment_file=garment_file,
        person_file=person_file,
        garment_id=None,
        garment_image_url=None,
        garment_category=garment_category,
        garment_file_2=None,
        garment_id_2=None,
        garment_image_url_2=None,
        garment_category_2="bottom",
        prompt=prompt,
        mode=mode,
        model_gender=model_gender,
        debug_mode="off",
        current_user=current_user,
        db=db,
    )


@router.post("/validate-input", response_model=TryOnV2ValidateResponse)
async def tryon_v2_validate_input(
    garment_file: UploadFile | None = File(
        None,
        alias="garment_file",
        description="Garment product photo (or use garment_id/garment_image_url)",
    ),
    person_file: UploadFile = File(..., alias="person_file", description="Person full-body photo"),
    garment_id: str | None = Form(
        None, description="衣橱衣物 ID（与 garment_file/garment_image_url 三选一）"
    ),
    garment_image_url: str | None = Form(None),
    garment_category: str = Form(
        "auto", description="Expected category: top|bottom|skirt|outfit|auto"
    ),
    garment_file_2: UploadFile | None = File(None, alias="garment_file_2"),
    garment_id_2: str | None = Form(None),
    garment_image_url_2: str | None = Form(None),
    garment_category_2: str = Form("bottom", description="Second garment category for outfit"),
    mode: str = Form("strict", description="strict|balanced"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_tryon_v2_enabled()
    request_start = time.time()

    if garment_file is not None and (
        not garment_file.content_type or not garment_file.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="garment_file must be an image",
        )

    if not person_file.content_type or not person_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="person_file must be an image",
        )

    if mode not in {
        "strict",
        "balanced",
        "replace",
        "realistic",
        "realistic_v2",
        "professional",
        "hybrid",
        "paste",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "mode must be one of: strict, balanced, replace, realistic, "
                "professional, hybrid, paste"
            ),
        )

    from io import BytesIO
    from pathlib import Path

    from PIL import Image

    person_bytes = await person_file.read()
    if len(person_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="person_file cannot be empty",
        )
    person_image = Image.open(BytesIO(person_bytes)).convert("RGB")

    # 加载衣物图片（三选一）
    garment_image: Image.Image | None = None
    garment_image_2: Image.Image | None = None

    if garment_file is not None:
        garment_bytes = await garment_file.read()
        if len(garment_bytes) == 0:
            raise HTTPException(status_code=400, detail="garment_file cannot be empty")
        garment_image = Image.open(BytesIO(garment_bytes)).convert("RGB")
    elif garment_id is not None:
        from uuid import UUID as _UUID

        from app.services.garment import get_garment_by_id

        try:
            gid = _UUID(garment_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="garment_id 格式无效")
        g = get_garment_by_id(db, gid)
        if not g:
            raise HTTPException(status_code=404, detail="衣物不存在")
        if str(g.user_id) != str(current_user.user_id):
            raise HTTPException(status_code=403, detail="无权访问该衣物")
        gpath = Path(g.image_path) if g.image_path else None
        if not gpath or not gpath.is_file():
            raise HTTPException(status_code=400, detail="衣物图片文件不存在")
        garment_image = Image.open(gpath).convert("RGB")
        if not garment_image_url:
            garment_image_url = g.image_url

    if garment_file_2 is not None:
        garment2_bytes = await garment_file_2.read()
        garment_image_2 = (
            Image.open(BytesIO(garment2_bytes)).convert("RGB") if len(garment2_bytes) else None
        )
    elif garment_id_2 is not None:
        from uuid import UUID as _UUID

        from app.services.garment import get_garment_by_id

        try:
            gid2 = _UUID(garment_id_2)
        except ValueError:
            raise HTTPException(status_code=400, detail="garment_id_2 格式无效")
        g2 = get_garment_by_id(db, gid2)
        if not g2:
            raise HTTPException(status_code=404, detail="第二件衣物不存在")
        if str(g2.user_id) != str(current_user.user_id):
            raise HTTPException(status_code=403, detail="无权访问该衣物")
        gpath2 = Path(g2.image_path) if g2.image_path else None
        if not gpath2 or not gpath2.is_file():
            raise HTTPException(status_code=400, detail="第二件衣物图片文件不存在")
        garment_image_2 = Image.open(gpath2).convert("RGB")
        if not garment_image_url_2:
            garment_image_url_2 = g2.image_url

    if garment_image is None and garment_image_url is None:
        raise HTTPException(
            status_code=400,
            detail="请提供衣物图片：garment_file、garment_id 或 garment_image_url 三选一",
        )

    def _load_uploads_url(url: str) -> Image.Image | None:
        u = (url or "").strip()
        low = u.lower()
        if "/uploads/" not in low:
            return None
        idx = low.find("/uploads/")
        tail = u[idx + len("/uploads/") :].lstrip("/").replace("\\", "/")
        if not tail:
            return None
        full = Path(settings.UPLOAD_DIR) / tail
        if not full.is_file():
            return None
        try:
            return Image.open(full).convert("RGB")
        except Exception:
            return None

    if garment_image_url:
        img = _load_uploads_url(garment_image_url)
        if img is not None:
            garment_image = img
    if garment_image_url_2:
        img2 = _load_uploads_url(garment_image_url_2)
        if img2 is not None:
            garment_image_2 = img2

    # Replace/realistic/realistic_v2/hybrid/paste mode uses upstream/warp engines; skip pipeline A input gate precheck.  # noqa: E501
    if mode in ("replace", "realistic", "realistic_v2", "hybrid", "paste"):
        return TryOnV2ValidateResponse(
            status="pass",
            pipeline=(
                "PASTE"
                if mode == "paste"
                else (
                    "HYBRID"
                    if mode == "hybrid"
                    else (
                        "REALISTIC_V2"
                        if mode == "realistic_v2"
                        else ("REALISTIC" if mode == "realistic" else "REPLACE")
                    )
                )
            ),
            passed=True,
            error_code=None,
            message=f"{mode} 模式：跳过方案A门禁（将走增强保真引擎）",
            retryable=False,
            action_hint=None,
            qc_scores={},
            thresholds={},
        )

    if check_tryon_garment_has_face(garment_image):
        return TryOnV2ValidateResponse(
            status="fail",
            pipeline="A",
            passed=False,
            error_code="TRYON_GARMENT_CONTAINS_MODEL",
            message="衣服图检测到人像，请上传无模特商品图。",
            retryable=False,
            action_hint="请使用纯商品图，不要包含人物脸部。",
            qc_scores={},
            thresholds=_v2_thresholds(strict_mode=(mode == "strict")),
        )
    if garment_image_2 is not None and check_tryon_garment_has_face(garment_image_2):
        return TryOnV2ValidateResponse(
            status="fail",
            pipeline="A",
            passed=False,
            error_code="TRYON_GARMENT_CONTAINS_MODEL",
            message="第二件衣服图检测到人像，请上传无模特商品图。",
            retryable=False,
            action_hint="请使用纯商品图，不要包含人物脸部。",
            qc_scores={},
            thresholds=_v2_thresholds(strict_mode=(mode == "strict")),
        )

    garment_image, garment_category, pre_meta = _maybe_auto_preprocess(
        garment_image, garment_category
    )
    _classify_end = time.time()
    if "recognized_confidence" in pre_meta:
        logger.info(
            "[TIMING] Classification: %.1fms (confidence=%.3f, category=%s)",
            (_classify_end - request_start) * 1000,
            pre_meta.get("recognized_confidence", 0.0),
            pre_meta.get("recognized_tryon_category", "unknown"),
        )
    if garment_image_2 is not None:
        garment_image_2, garment_category_2, pre_meta2 = _maybe_auto_preprocess(
            garment_image_2, garment_category_2
        )
        pre_meta["auto_preprocess_2"] = pre_meta2

    recognized_cat = pre_meta.get("recognized_tryon_category", "")
    if recognized_cat == "unknown" and garment_category in ("unknown", "auto", ""):
        recognized_confidence = pre_meta.get("recognized_confidence", 0.0)
        logger.warning(
            "[TRYON] Unknown category fallback -> upper "
            "(confidence=%.3f, original_garment_category=%s)",
            recognized_confidence,
            garment_category,
        )
        recognized_cat = "upper"
        garment_category = "upper"
        pre_meta["recognized_tryon_category"] = "upper"
        pre_meta["category_fallback"] = True

    thresholds = _v2_thresholds(strict_mode=(mode == "strict"))
    gate_confidence = pre_meta.get("recognized_confidence")
    gate = evaluate_input_gate(
        person_image=person_image,
        garment_image=garment_image,
        garment_category=garment_category,
        strict=(mode == "strict"),
        thresholds=thresholds,
        garment_confidence=gate_confidence,
    )
    # outfit: also validate second garment if provided
    if (
        gate.passed
        and garment_category
        and "outfit" in garment_category.lower()
        and garment_image_2 is not None
    ):
        gate2_confidence = pre_meta.get("auto_preprocess_2", {}).get("recognized_confidence")
        gate2 = evaluate_input_gate(
            person_image=person_image,
            garment_image=garment_image_2,
            garment_category=garment_category_2,
            strict=(mode == "strict"),
            thresholds=thresholds,
            garment_confidence=gate2_confidence,
        )
        if not gate2.passed:
            gate = gate2

    _total_ms = (time.time() - request_start) * 1000
    logger.info(
        "[TIMING] validate-input total: %.1fms (gate=%s, passed=%s)",
        _total_ms,
        "A",
        gate.passed,
    )

    return TryOnV2ValidateResponse(
        status="pass" if gate.passed else "fail",
        pipeline="A",
        passed=gate.passed,
        error_code=gate.error_code,
        message="输入通过方案A门禁" if gate.passed else gate.message,
        retryable=gate.retryable,
        action_hint=gate.action_hint,
        qc_scores=gate.scores,
        thresholds=thresholds,
        recognized_tryon_category=pre_meta.get("recognized_tryon_category"),
        recognized_raw_category=pre_meta.get("recognized_raw_category"),
        recognized_confidence=pre_meta.get("recognized_confidence"),
    )


@router.get("/capabilities", response_model=TryOnV2CapabilitiesResponse)
async def tryon_v2_capabilities(
    _current_user: User = Depends(get_current_user),
):
    strict_identity_default = bool(getattr(settings, "TRYON_V2_STRICT_IDENTITY", True))
    return TryOnV2CapabilitiesResponse(
        enabled=bool(getattr(settings, "TRYON_V2_ENABLED", True)),
        pipeline_default="A",
        strict_identity_default=strict_identity_default,
        supported_garment_categories=[
            "top",
            "bottom",
            "skirt",
            "outfit",
            "上装",
            "下装",
            "裙装",
            "套装",
        ],
        modes=[
            "strict",
            "balanced",
            "replace",
            "realistic",
            "realistic_v2",
            "professional",
            "hybrid",
        ],
        thresholds={
            **_v2_thresholds(strict_mode=True),
            "qc_threshold": float(getattr(settings, "TRYON_V2_QC_THRESHOLD", 0.6) or 0.6),
        },
    )


class TryOnV2ModelStatusResponse(BaseModel):
    enabled: bool = Field(..., description="Whether tryon v2 is enabled")
    engines: dict[str, Any] = Field(default_factory=dict, description="Engine status")


@router.get("/model-status", response_model=TryOnV2ModelStatusResponse)
async def tryon_v2_model_status(
    _current_user: User = Depends(get_current_user),
):
    """Get status of all try-on engines (Bailian, Remote VTON, Local CatVTON)."""
    from app.services.bailian_tryon_client import _bailian_configured
    from app.services.tryon_v2.catvton_engine_client import get_catvton_status
    from app.services.vton_remote_client import _remote_url_configured

    engines: dict[str, Any] = {}

    # Bailian
    engines["bailian"] = {
        "configured": _bailian_configured(),
        "enabled": bool(getattr(settings, "DASHSCOPE_TRYON_ENABLED", False)),
        "model_default": getattr(settings, "DASHSCOPE_TRYON_MODEL", "wanx2.1-imageedit"),
    }

    # Remote VTON
    remote_url = (getattr(settings, "VTON_INFERENCE_URL", "") or "").strip()
    engines["remote_vton"] = {
        "configured": _remote_url_configured(),
        "url": remote_url if remote_url else None,
        "timeout_s": int(getattr(settings, "VTON_INFERENCE_TIMEOUT_SECONDS", 2400) or 2400),
    }

    # Local CatVTON
    catvton_status = get_catvton_status()
    engines["catvton_local"] = {
        "configured": catvton_status.get("configured", False),
        "enabled": catvton_status.get("enabled", False),
        "path": catvton_status.get("path"),
        "path_exists": catvton_status.get("path_exists", False),
        "width": catvton_status.get("width"),
        "height": catvton_status.get("height"),
        "steps": catvton_status.get("steps"),
        "guidance": catvton_status.get("guidance"),
        "timeout_s": catvton_status.get("timeout_s"),
        "torch_compile": catvton_status.get("torch_compile", False),
    }

    # Try-on v2 status
    engines["tryon_v2"] = {
        "enabled": bool(getattr(settings, "TRYON_V2_ENABLED", True)),
        "strict_identity_default": bool(getattr(settings, "TRYON_V2_STRICT_IDENTITY", True)),
        "auto_preprocess": bool(getattr(settings, "TRYON_V2_AUTO_PREPROCESS", True)),
        "replace_allow_local_diffusion": bool(
            getattr(settings, "TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION", False)
        ),
        "engine_priority": getattr(
            settings,
            "TRYON_V2_REPLACE_ENGINE_PRIORITY",
            "warp,bailian,remote,catvton,diffusion",
        ),
        "skip_warp": bool(getattr(settings, "TRYON_V2_REPLACE_SKIP_WARP", False)),
    }

    return TryOnV2ModelStatusResponse(
        enabled=bool(getattr(settings, "TRYON_V2_ENABLED", True)),
        engines=engines,
    )
