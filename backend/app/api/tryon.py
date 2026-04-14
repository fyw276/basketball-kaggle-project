"""
Virtual Try-On API endpoints
"""

from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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
    garment_file: UploadFile = File(..., alias="garment_file", description="Garment product photo"),
    person_file: UploadFile = File(..., alias="person_file", description="Person photo"),
    prompt: str = "",
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
    if not garment_file.content_type or not garment_file.content_type.startswith("image/"):
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
        import os
        from io import BytesIO

        from PIL import Image

        # Load images
        garment_bytes = await garment_file.read()
        person_bytes = await person_file.read()

        if len(garment_bytes) == 0 or len(person_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded files cannot be empty"
            )

        garment_image = Image.open(BytesIO(garment_bytes)).convert("RGB")
        person_image = Image.open(BytesIO(person_bytes)).convert("RGB")

        # Run virtual try-on
        from app.services.virtual_tryon import get_tryon_service

        service = get_tryon_service()

        max_retries = max(0, int(getattr(settings, "TRYON_MAX_RETRIES", 1) or 1))
        result = None
        last_http = status.HTTP_502_BAD_GATEWAY
        last_code = "TRYON_FAILED"
        last_msg = "Virtual try-on failed"
        last_retryable = False

        for attempt in range(max_retries + 1):
            result = service.tryon_garment(
                garment_image=garment_image,
                person_image=person_image,
                prompt=prompt or None,
                model_gender=model_gender,
            )

            st = (result or {}).get("status") or ""
            if st != "error":
                break

            http_code, err_code, err_msg, retryable = _normalize_tryon_error(result or {})
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
            # Save the result
            output = BytesIO()
            result["result_image"].save(output, format="JPEG", quality=90)
            output.seek(0)

            # Use a stable, collision-resistant key so different inputs never overwrite each other.
            # NOTE: built-in `hash()` is salted per-process and the old modulo could collide easily.
            key_src = (
                garment_bytes
                + b"||"
                + person_bytes
                + b"||"
                + (prompt or "").encode("utf-8", errors="ignore")
                + b"||"
                + model_gender.encode("utf-8", errors="ignore")
            )
            key = hashlib.sha256(key_src).hexdigest()[:16]
            result_path = os.path.join(str(current_user.user_id), "tryon", f"result_{key}.jpg")

            storage_service = get_storage_service()
            saved_path, result_url = storage_service._save_bytes(output.getvalue(), result_path)
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
