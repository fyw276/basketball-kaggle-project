"""
Virtual Try-On API endpoints
"""

from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.observability.dependency_metrics import (
    classify_external_exception,
    record_dependency_outcome,
)
from app.services.storage import get_storage_service
from app.services.subscription_billing import consume_usage

router = APIRouter(prefix="/tryon", tags=["Virtual Try-On"])


def _is_bottom_or_skirt_category(garment_category: str | None) -> bool:
    s = (garment_category or "").strip().lower()
    if not s:
        return False
    bottom_keywords = (
        "下装",
        "裤",
        "裤装",
        "短裤",
        "牛仔",
        "裙",
        "裙装",
        "连衣裙",
        "dress",
        "skirt",
        "bottom",
        "pants",
        "jeans",
    )
    return any(k in s for k in bottom_keywords)


def _pil_image_to_jpeg_bytes(img, quality: int = 90) -> bytes:
    """
    Encode a PIL image as JPEG bytes.

    Saving directly to io.BytesIO can fail on Windows: BytesIO has no fileno(), and
    Pillow's JPEG path may fall into a buggy encoder branch (TypeError: 16 vs 17 args).
    Writing to a real temp file avoids that.
    """
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


class TryOnResponse(BaseModel):
    """Virtual try-on response"""

    status: str = Field(..., description="Status: success/fallback/error")
    message: str = Field(..., description="Human-readable status message")
    result_image_url: str = Field(None, description="URL of the try-on result image")
    error_code: str | None = Field(None, description="Normalized error code for client handling")
    retryable: bool = Field(False, description="Whether client can retry later")
    metadata: dict = Field(default_factory=dict, description="Processing metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "虚拟试穿成功完成",
                "result_image_url": "/uploads/tryon/result_abc123.jpg",
                "metadata": {
                    "model": "stabilityai/stable-diffusion-2-inpainting",
                    "steps": 25,
                    "device": "cuda",
                    "garment_count": 1,
                },
            }
        }


def _normalize_tryon_error(result: Dict[str, Any]) -> Tuple[int, str, str, bool]:
    """Map service error payload to stable HTTP/status code and retry hint."""
    metadata = result.get("metadata") if isinstance(result, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}

    message = str((result or {}).get("message") or "Virtual try-on failed").strip()
    reason = str(metadata.get("reason") or "").strip().lower()
    msg_l = message.lower()

    if reason == "garment_contains_face":
        return (
            status.HTTP_400_BAD_REQUEST,
            "TRYON_GARMENT_CONTAINS_MODEL",
            message,
            False,
        )
    if "timeout" in msg_l or "timed out" in msg_l:
        return (
            status.HTTP_504_GATEWAY_TIMEOUT,
            "TRYON_TIMEOUT",
            "虚拟试衣超时，请稍后重试。",
            True,
        )
    if "quota" in msg_l or "429" in msg_l:
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "TRYON_UPSTREAM_QUOTA",
            "试衣服务额度暂时不足，请稍后重试。",
            True,
        )
    if "loading" in msg_l or "queue" in msg_l or "cold" in msg_l:
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "TRYON_UPSTREAM_COLD_START",
            "试衣服务正在预热，请稍后重试。",
            True,
        )
    if "all tokens exhausted" in msg_l:
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "TRYON_UPSTREAM_TOKEN_EXHAUSTED",
            "试衣服务令牌已耗尽，请稍后重试。",
            True,
        )

    return (
        status.HTTP_502_BAD_GATEWAY,
        "TRYON_FAILED",
        message or "虚拟试衣失败",
        False,
    )


@router.post("/garment", response_model=TryOnResponse)
async def try_on_garment(
    garment_file: UploadFile | None = File(
        None,
        alias="garment_file",
        description="Garment product photo (or use garment_id/image_url)",
    ),
    person_file: UploadFile = File(..., alias="person_file", description="Person photo"),
    garment_id: str | None = Form(
        None, description="衣橱衣物 ID（与 garment_file/image_url 三选一）"
    ),
    image_url: str | None = Form(
        None, description="衣物图片 URL（与 garment_file/garment_id 三选一）"
    ),
    prompt: str = "",
    garment_category: str = Form(
        "",
        description="Optional wardrobe category (e.g. 下装) for better fallback paste placement",
    ),
    # 无性别推荐系统新增参数
    model_gender: str = "neutral",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Virtual try-on: Render a garment on a person's photo.

    无性别推荐系统 (Step 4):
    - model_gender 参数允许用户切换查看效果
    - 支持 male/female/neutral 三种模式
    - 同一件衣服可以分别在男女模特上生成上身图

    Requires:
    - garment_file: Clean product photo (white/neutral background preferred)
    - person_file: Full-body or half-body photo (front-facing, good lighting)
    - model_gender: "male" / "female" / "neutral" (默认 neutral)

    Returns a generated image showing the garment on the person.
    For best results, use 512x512 or higher resolution images.

    Note: GPU recommended for quality results. Falls back to composition
    mode if GPU is unavailable.
    """
    # Validate garment file
    if garment_file is not None and (
        not garment_file.content_type or not garment_file.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="garment_file must be an image"
        )

    # Validate person file
    if not person_file.content_type or not person_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="person_file must be an image"
        )

    # Validate model_gender
    if model_gender not in ["male", "female", "neutral"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="model_gender must be one of: male, female, neutral",
        )

    try:
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

        import hashlib
        from io import BytesIO
        from pathlib import Path as _Path

        from PIL import Image

        # Load images
        person_bytes = await person_file.read()
        if len(person_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="person_file cannot be empty"
            )
        person_image = Image.open(BytesIO(person_bytes)).convert("RGB")

        # 加载衣物图片（三选一：garment_file / garment_id / image_url）
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
            gpath = _Path(g.image_path) if g.image_path else None
            if not gpath or not gpath.is_file():
                raise HTTPException(status_code=400, detail="衣物图片文件不存在")
            garment_image = Image.open(gpath).convert("RGB")
        elif image_url is not None:
            from app.services.smart_outfit_generator import load_image_bytes

            _bytes = await load_image_bytes(image_url)
            garment_image = Image.open(BytesIO(_bytes)).convert("RGB")
        else:
            raise HTTPException(
                status_code=400,
                detail="请提供衣物图片：garment_file、garment_id 或 image_url 三选一",
            )

        from app.services.bailian_tryon_client import call_bailian_tryon
        from app.services.virtual_tryon import (
            check_tryon_garment_has_face,
            get_tryon_service,
            sanitize_tryon_prompt,
        )
        from app.services.vton_remote_client import call_remote_vton

        gc = (garment_category or "").strip() or None
        prompt_clean = sanitize_tryon_prompt(prompt or None) or ""
        force_identity_fallback = bool(
            getattr(settings, "TRYON_BOTTOM_FORCE_FALLBACK", True)
            and _is_bottom_or_skirt_category(gc)
        )

        if check_tryon_garment_has_face(garment_image):
            record_dependency_outcome("tryon", "failure")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "衣服图检测到人像，请上传无模特的白底商品图，否则会出现重影。",
                    "error_code": "TRYON_GARMENT_CONTAINS_MODEL",
                    "retryable": False,
                },
            )

        max_retries = max(0, int(getattr(settings, "TRYON_MAX_RETRIES", 1) or 1))
        result = None
        last_http = status.HTTP_502_BAD_GATEWAY
        last_code = "TRYON_FAILED"
        last_msg = "Virtual try-on failed"
        last_retryable = False

        used_bailian = False
        used_remote_vton = False

        bailian_result = None
        if not force_identity_fallback:
            bailian_result = await call_bailian_tryon(
                garment_bytes=garment_bytes,
                person_bytes=person_bytes,
                prompt=prompt_clean,
                garment_category=gc,
            )
        if bailian_result is not None:
            st_b = (bailian_result.get("status") or "").lower()
            if st_b in ("success", "fallback"):
                result = bailian_result
                used_bailian = True
            elif not getattr(settings, "DASHSCOPE_TRYON_FALLBACK_LOCAL", True):
                record_dependency_outcome("tryon", "failure")
                http_code, err_code, err_msg, retryable = _normalize_tryon_error(bailian_result)
                raise HTTPException(
                    status_code=http_code,
                    detail={
                        "message": err_msg,
                        "error_code": err_code,
                        "retryable": retryable,
                    },
                )

        if result is None:
            if force_identity_fallback:
                service = get_tryon_service()
                result = service.tryon_garment(
                    garment_image=garment_image,
                    person_image=person_image,
                    prompt=prompt_clean or None,
                    model_gender=model_gender,
                    garment_category=gc,
                    force_fallback=True,
                )
                st = (result or {}).get("status") or ""
                if st == "error":
                    http_code, err_code, err_msg, retryable = _normalize_tryon_error(result or {})
                    last_http, last_code, last_msg, last_retryable = (
                        http_code,
                        err_code,
                        err_msg,
                        retryable,
                    )
            else:
                try:
                    remote_result = await call_remote_vton(
                        garment_bytes=garment_bytes,
                        person_bytes=person_bytes,
                        prompt=prompt_clean,
                        model_gender=model_gender,
                        garment_category=gc,
                    )
                except Exception as e:
                    record_dependency_outcome("tryon", "failure")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={
                            "message": f"远程试衣服务不可用: {e}",
                            "error_code": "VTON_REMOTE_UNAVAILABLE",
                            "retryable": True,
                        },
                    ) from e

                if remote_result is not None:
                    result = remote_result
                    used_remote_vton = True
                else:
                    service = get_tryon_service()
                    for attempt in range(max_retries + 1):
                        result = service.tryon_garment(
                            garment_image=garment_image,
                            person_image=person_image,
                            prompt=prompt_clean or None,
                            model_gender=model_gender,
                            garment_category=gc,
                        )

                        st = (result or {}).get("status") or ""
                        if st != "error":
                            break

                        http_code, err_code, err_msg, retryable = _normalize_tryon_error(
                            result or {}
                        )
                        last_http, last_code, last_msg, last_retryable = (
                            http_code,
                            err_code,
                            err_msg,
                            retryable,
                        )
                        if not retryable or attempt >= max_retries:
                            break

        st = (result or {}).get("status") or ""
        if st == "error":
            record_dependency_outcome("tryon", "failure")
            raise HTTPException(
                status_code=last_http,
                detail={
                    "message": last_msg,
                    "error_code": last_code,
                    "retryable": last_retryable,
                },
            )

        # Save result image
        if result["result_image"] is not None:
            jpeg_bytes = _pil_image_to_jpeg_bytes(result["result_image"], quality=90)

            # Use a stable, collision-resistant key so different inputs never overwrite each other.
            # NOTE: built-in `hash()` is salted per-process and the old modulo could collide easily.
            # NOTE: include a pipeline version to avoid client-side image cache
            # when fallback processing changes but inputs stay the same.
            from app.services.virtual_tryon import FALLBACK_PIPELINE_VERSION

            gc_bytes = ((garment_category or "").strip()).encode("utf-8", errors="ignore")
            route_tag = (
                b"bailian" if used_bailian else (b"remote_vton" if used_remote_vton else b"local")
            )
            key_src = (
                garment_bytes
                + b"||"
                + person_bytes
                + b"||"
                + (prompt or "").encode("utf-8", errors="ignore")
                + b"||"
                + model_gender.encode("utf-8", errors="ignore")
                + b"||"
                + gc_bytes
                + b"||"
                + FALLBACK_PIPELINE_VERSION.encode("utf-8", errors="ignore")
                + b"||"
                + route_tag
            )
            key = hashlib.sha256(key_src).hexdigest()[:16]
            result_path = f"{current_user.user_id}/tryon/result_{key}.jpg"

            storage_service = get_storage_service()
            saved_path, result_url = storage_service._save_bytes(jpeg_bytes, result_path)
            result_image_url = result_url
        else:
            result_image_url = None

        if st == "success":
            record_dependency_outcome("tryon", "success")
        elif st == "fallback":
            record_dependency_outcome("tryon", "degraded")
        else:
            record_dependency_outcome("tryon", "degraded")

        return TryOnResponse(
            status=result["status"],
            message=result["message"],
            result_image_url=result_image_url,
            error_code=None,
            retryable=False,
            metadata=result.get("metadata", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        record_dependency_outcome("tryon", classify_external_exception(e))
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Virtual try-on failed: {str(e)}",
        )
