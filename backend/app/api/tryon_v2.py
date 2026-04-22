"""Try-on v2 API endpoints (pipeline A MVP)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.observability.tryon_v2_metrics import record_tryon_v2_failure, record_tryon_v2_success
from app.services.storage import get_storage_service
from app.services.subscription_billing import consume_usage
from app.services.tryon_v2 import run_pipeline_a
from app.services.tryon_v2.input_gate import evaluate_input_gate
from app.services.tryon_v2.preprocess import preprocess_garment_image
from app.services.virtual_tryon import check_tryon_garment_has_face

router = APIRouter(prefix="/tryon", tags=["Virtual Try-On v2"])


class TryOnV2Response(BaseModel):
    status: str = Field(..., description="Status: success/error")
    message: str = Field(..., description="Human-readable status message")
    pipeline: str = Field("A", description="Pipeline identifier")
    result_image_url: str | None = Field(None, description="URL of the try-on result image")
    error_code: str | None = Field(None, description="Stable error code")
    retryable: bool = Field(False, description="Whether client can retry later")
    action_hint: str | None = Field(None, description="Action guidance for UI")
    qc_scores: dict[str, float] = Field(default_factory=dict, description="Input/QC scores")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Processing metadata")


class TryOnV2ValidateResponse(BaseModel):
    status: str = Field(..., description="Status: pass/fail")
    pipeline: str = Field("A", description="Pipeline identifier")
    passed: bool = Field(..., description="Whether input gate passed")
    error_code: str | None = Field(None, description="Stable error code when failed")
    message: str = Field(..., description="Validation message")
    retryable: bool = Field(False, description="Whether client can retry later")
    action_hint: str | None = Field(None, description="Action guidance for UI")
    qc_scores: dict[str, float] = Field(default_factory=dict, description="Input quality scores")
    thresholds: dict[str, float] = Field(default_factory=dict, description="Thresholds applied")


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
    # For preprocess we accept model/poster images and try best-effort extraction.

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

    image_bytes = _pil_image_to_jpeg_bytes(r.image, quality=92)
    key = hashlib.sha1(image_bytes).hexdigest()[:20]
    path = f"preprocess/garment_{key}.jpg"
    _, url = get_storage_service()._save_bytes(image_bytes, path)

    return TryOnV2PreprocessItem(
        tryon_category=r.tryon_category,
        raw_category=r.raw_category,
        category_confidence=float(r.confidence),
        standardized_image_url=url,
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

            image_bytes = _pil_image_to_jpeg_bytes(r.image, quality=92)
            key = hashlib.sha1(image_bytes).hexdigest()[:20]
            path = f"preprocess/garment_{key}.jpg"
            _, url = get_storage_service()._save_bytes(image_bytes, path)
            out.append(
                TryOnV2PreprocessItem(
                    tryon_category=r.tryon_category,
                    raw_category=r.raw_category,
                    category_confidence=float(r.confidence),
                    standardized_image_url=url,
                    metadata=r.metadata,
                )
            )
        except Exception:
            # Skip failed items to keep batch resilient.
            continue
    return out


@router.post("/garment", response_model=TryOnV2Response)
async def tryon_garment_v2(
    garment_file: UploadFile = File(..., alias="garment_file", description="Garment product photo"),
    person_file: UploadFile = File(..., alias="person_file", description="Person full-body photo"),
    garment_image_url: str | None = Form(
        None, description="Optional /uploads/... url of standardized garment image"
    ),
    garment_category: str = Form(
        "auto", description="Expected category: top|bottom|skirt|outfit|auto"
    ),
    garment_file_2: UploadFile | None = File(
        None, alias="garment_file_2", description="Optional second garment for outfit"
    ),
    garment_image_url_2: str | None = Form(
        None, description="Optional /uploads/... url of standardized second garment image"
    ),
    garment_category_2: str = Form(
        "bottom", description="Second garment category for outfit: bottom|skirt"
    ),
    prompt: str = Form("", description="Optional text prompt"),
    mode: str = Form("strict", description="strict|balanced"),
    model_gender: str = Form("neutral", description="male|female|neutral"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    _ensure_tryon_v2_enabled()

    if not garment_file.content_type or not garment_file.content_type.startswith("image/"):
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

    if mode not in {"strict", "balanced", "replace"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be one of: strict, balanced, replace",
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

    garment_bytes = await garment_file.read()
    person_bytes = await person_file.read()
    garment2_bytes = await garment_file_2.read() if garment_file_2 is not None else b""

    if len(garment_bytes) == 0 or len(person_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded files cannot be empty",
        )

    garment_image = Image.open(BytesIO(garment_bytes)).convert("RGB")
    person_image = Image.open(BytesIO(person_bytes)).convert("RGB")
    garment_image_2 = (
        Image.open(BytesIO(garment2_bytes)).convert("RGB") if len(garment2_bytes) else None
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
            pre_meta = {"standardized_image_url": garment_image_url}
        else:
            pre_meta = {}
    else:
        pre_meta = {}

    if garment_image_url_2:
        img2 = _load_uploads_url(garment_image_url_2)
        if img2 is not None:
            garment_image_2 = img2
            pre_meta["standardized_image_url_2"] = garment_image_url_2

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

    garment_image, garment_category, auto_meta = _maybe_auto_preprocess(
        garment_image, garment_category
    )
    pre_meta = {**pre_meta, **auto_meta}
    if garment_image_2 is not None:
        garment_image_2, garment_category_2, pre_meta2 = _maybe_auto_preprocess(
            garment_image_2, garment_category_2
        )
        pre_meta["auto_preprocess_2"] = pre_meta2

    # "replace" mode: use photo-realistic try-on (Bailian -> remote VTON -> local diffusion)
    if mode == "replace":
        from app.services.bailian_tryon_client import _bailian_configured, call_bailian_tryon
        from app.services.virtual_tryon import get_tryon_service, sanitize_tryon_prompt
        from app.services.vton_remote_client import _remote_url_configured, call_remote_vton

        prompt_clean = sanitize_tryon_prompt(prompt or None) or ""
        # Use standardized garment/person bytes for upstreams.
        garment_jpg = _pil_image_to_jpeg_bytes(garment_image, quality=92)
        person_jpg = _pil_image_to_jpeg_bytes(person_image, quality=92)
        gc = (garment_category or "").strip() or None

        upstream = await call_bailian_tryon(
            garment_bytes=garment_jpg,
            person_bytes=person_jpg,
            prompt=prompt_clean,
            garment_category=gc,
        )
        bailian_ok = (
            isinstance(upstream, dict)
            and str(upstream.get("status") or "").lower() == "success"
            and upstream.get("result_image") is not None
        )

        remote = None
        if not bailian_ok:
            remote = await call_remote_vton(
                garment_bytes=garment_jpg,
                person_bytes=person_jpg,
                prompt=prompt_clean,
                model_gender=model_gender,
                garment_category=gc,
            )
        remote_ok = (
            isinstance(remote, dict)
            and str(remote.get("status") or "").lower() == "success"
            and remote.get("result_image") is not None
        )

        if bailian_ok:
            upstream = upstream
        elif remote_ok:
            upstream = remote
        elif bool(getattr(settings, "TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION", False)):
            # Local diffusion try-on (can hallucinate badly if weights/cache are incomplete).
            service = get_tryon_service()
            upstream = service.tryon_garment(
                garment_image=garment_image,
                person_image=person_image,
                prompt=prompt_clean,
                model_gender=model_gender,
                garment_category=gc,
                force_fallback=False,
            )
        else:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record_tryon_v2_failure("TRYON_V2_REPLACE_UPSTREAM_UNAVAILABLE", latency_ms)
            hints = []
            bailian_diag: dict[str, Any] = {}
            remote_diag: dict[str, Any] = {}
            if not _bailian_configured():
                hints.append("启用百炼：DASHSCOPE_TRYON_ENABLED=true 且配置 DASHSCOPE_API_KEY")
            else:
                msg = ""
                reason = ""
                if isinstance(upstream, dict):
                    msg = str(upstream.get("message") or "").strip()
                    meta = (
                        upstream.get("metadata")
                        if isinstance(upstream.get("metadata"), dict)
                        else {}
                    )
                    reason = str((meta or {}).get("reason") or "").strip()
                    bailian_diag = {
                        "configured": True,
                        "status": str(upstream.get("status") or ""),
                        "message": msg,
                        "reason": reason,
                    }
                hints.append(
                    f"百炼未成功：{msg or reason or '请检查 key/额度/模型权限/网络；查看 detail.replace_debug.bailian'}"
                )
            if not _remote_url_configured():
                hints.append("或配置远程 VTON：VTON_INFERENCE_URL")
            else:
                rmsg = ""
                rreason = ""
                if isinstance(remote, dict):
                    rmsg = str(remote.get("message") or "").strip()
                    rmeta = (
                        remote.get("metadata") if isinstance(remote.get("metadata"), dict) else {}
                    )
                    rreason = str((rmeta or {}).get("reason") or "").strip()
                    remote_diag = {
                        "configured": True,
                        "status": str(remote.get("status") or ""),
                        "message": rmsg,
                        "reason": rreason,
                    }
                hints.append(
                    f"远程 VTON 未成功：{rmsg or rreason or '请检查服务可用性与超时；查看 detail.replace_debug.remote'}"
                )
            hints.append(
                (
                    "（高级）如确需本机 diffusers 兜底："
                    "TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true，"
                    "并确保 SD inpainting 权重完整"
                )
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "替换试衣上游不可用或未成功（已禁止不稳定的本机 diffusion 兜底）",
                    "error_code": "TRYON_V2_REPLACE_UPSTREAM_UNAVAILABLE",
                    "retryable": True,
                    "action_hint": "；".join(hints),
                    "qc_scores": {},
                    "replace_debug": {
                        "bailian": bailian_diag,
                        "remote": remote_diag,
                        "bailian_configured": _bailian_configured(),
                        "remote_configured": _remote_url_configured(),
                    },
                },
            )

        status_s = str((upstream or {}).get("status") or "error").lower()
        if status_s != "success" or (upstream or {}).get("result_image") is None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record_tryon_v2_failure("TRYON_V2_REPLACE_FAILED", latency_ms)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": str((upstream or {}).get("message") or "替换试衣失败"),
                    "error_code": "TRYON_V2_REPLACE_FAILED",
                    "retryable": True,
                    "action_hint": "请稍后重试，或切换为 strict/balanced（方案A）获得更稳定结果。",
                    "qc_scores": {},
                },
            )

        result = {
            "status": "success",
            "message": str((upstream or {}).get("message") or "替换试衣完成"),
            "result_image": (upstream or {}).get("result_image"),
            "qc_scores": {},
            "metadata": {
                "pipeline": "REPLACE",
                "upstream_metadata": (upstream or {}).get("metadata") or {},
            },
        }
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
    record_tryon_v2_success(int((time.perf_counter() - started) * 1000))

    return TryOnV2Response(
        status="success",
        message=str(result.get("message") or "方案A试衣成功"),
        pipeline=str((result.get("metadata") or {}).get("pipeline") or "A"),
        result_image_url=result_url,
        error_code=None,
        retryable=False,
        action_hint=None,
        qc_scores=result.get("qc_scores") or {},
        metadata={**(result.get("metadata") or {}), **pre_meta},
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
        garment_image_url=None,
        garment_category=garment_category,
        garment_file_2=None,
        garment_image_url_2=None,
        garment_category_2="bottom",
        prompt=prompt,
        mode=mode,
        model_gender=model_gender,
        current_user=current_user,
        db=db,
    )


@router.post("/validate-input", response_model=TryOnV2ValidateResponse)
async def tryon_v2_validate_input(
    garment_file: UploadFile = File(..., alias="garment_file", description="Garment product photo"),
    person_file: UploadFile = File(..., alias="person_file", description="Person full-body photo"),
    garment_image_url: str | None = Form(None),
    garment_category: str = Form(
        "auto", description="Expected category: top|bottom|skirt|outfit|auto"
    ),
    garment_file_2: UploadFile | None = File(None, alias="garment_file_2"),
    garment_image_url_2: str | None = Form(None),
    garment_category_2: str = Form("bottom", description="Second garment category for outfit"),
    mode: str = Form("strict", description="strict|balanced"),
    current_user: User = Depends(get_current_user),
):
    _ensure_tryon_v2_enabled()

    if not garment_file.content_type or not garment_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="garment_file must be an image",
        )

    if not person_file.content_type or not person_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="person_file must be an image",
        )

    if mode not in {"strict", "balanced", "replace"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be one of: strict, balanced, replace",
        )

    from io import BytesIO
    from pathlib import Path

    from PIL import Image

    garment_bytes = await garment_file.read()
    person_bytes = await person_file.read()
    garment2_bytes = await garment_file_2.read() if garment_file_2 is not None else b""
    if len(garment_bytes) == 0 or len(person_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded files cannot be empty",
        )

    garment_image = Image.open(BytesIO(garment_bytes)).convert("RGB")
    person_image = Image.open(BytesIO(person_bytes)).convert("RGB")
    garment_image_2 = (
        Image.open(BytesIO(garment2_bytes)).convert("RGB") if len(garment2_bytes) else None
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

    # Replace mode uses upstream photo-realistic try-on; skip pipeline A input gate precheck.
    if mode == "replace":
        return TryOnV2ValidateResponse(
            status="pass",
            pipeline="REPLACE",
            passed=True,
            error_code=None,
            message="replace 模式：跳过方案A门禁（将走替换试衣上游）",
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
    if garment_image_2 is not None:
        garment_image_2, garment_category_2, pre_meta2 = _maybe_auto_preprocess(
            garment_image_2, garment_category_2
        )
        pre_meta["auto_preprocess_2"] = pre_meta2

    thresholds = _v2_thresholds(strict_mode=(mode == "strict"))
    gate = evaluate_input_gate(
        person_image=person_image,
        garment_image=garment_image,
        garment_category=garment_category,
        strict=(mode == "strict"),
        thresholds=thresholds,
    )
    # outfit: also validate second garment if provided
    if (
        gate.passed
        and garment_category
        and "outfit" in garment_category.lower()
        and garment_image_2 is not None
    ):
        gate2 = evaluate_input_gate(
            person_image=person_image,
            garment_image=garment_image_2,
            garment_category=garment_category_2,
            strict=(mode == "strict"),
            thresholds=thresholds,
        )
        if not gate2.passed:
            gate = gate2

    return TryOnV2ValidateResponse(
        status="pass" if gate.passed else "fail",
        pipeline="A",
        passed=gate.passed,
        error_code=gate.error_code,
        message="输入通过方案A门禁" if gate.passed else gate.message,
        retryable=gate.retryable,
        action_hint=gate.action_hint,
        qc_scores=gate.scores,
        thresholds={
            **thresholds,
            **{k: v for k, v in pre_meta.items() if k.startswith("recognized_")},
        },
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
        modes=["strict", "balanced", "replace"],
        thresholds={
            **_v2_thresholds(strict_mode=True),
            "qc_threshold": float(getattr(settings, "TRYON_V2_QC_THRESHOLD", 0.6) or 0.6),
        },
    )
