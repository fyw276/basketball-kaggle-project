"""Try-on v2 API endpoints (pipeline A MVP)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.storage import get_storage_service
from app.services.subscription_billing import consume_usage
from app.services.tryon_v2 import run_pipeline_a
from app.services.tryon_v2.input_gate import evaluate_input_gate
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


@router.post("/pants", response_model=TryOnV2Response)
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

    if mode not in {"strict", "balanced"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be one of: strict, balanced",
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

    from PIL import Image

    garment_bytes = await garment_file.read()
    person_bytes = await person_file.read()

    if len(garment_bytes) == 0 or len(person_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded files cannot be empty",
        )

    garment_image = Image.open(BytesIO(garment_bytes)).convert("RGB")
    person_image = Image.open(BytesIO(person_bytes)).convert("RGB")

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

    strict_identity = mode == "strict"
    if mode == "strict":
        strict_identity = bool(getattr(settings, "TRYON_V2_STRICT_IDENTITY", True))

    thresholds = _v2_thresholds(strict_mode=(mode == "strict"))

    result = run_pipeline_a(
        person_image=person_image,
        garment_image=garment_image,
        garment_category=garment_category,
        prompt=prompt,
        model_gender=model_gender,
        strict_identity=strict_identity,
        thresholds=thresholds,
    )

    if result.get("status") != "success":
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

    return TryOnV2Response(
        status="success",
        message=str(result.get("message") or "方案A试衣成功"),
        pipeline="A",
        result_image_url=result_url,
        error_code=None,
        retryable=False,
        action_hint=None,
        qc_scores=result.get("qc_scores") or {},
        metadata=result.get("metadata") or {},
    )


@router.post("/validate-input", response_model=TryOnV2ValidateResponse)
async def tryon_v2_validate_input(
    garment_file: UploadFile = File(
        ..., alias="garment_file", description="Bottom garment product photo"
    ),
    person_file: UploadFile = File(..., alias="person_file", description="Person full-body photo"),
    garment_category: str = Form(
        "bottom", description="Expected bottom category, e.g. bottom/下装"
    ),
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

    if mode not in {"strict", "balanced"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be one of: strict, balanced",
        )

    from io import BytesIO

    from PIL import Image

    garment_bytes = await garment_file.read()
    person_bytes = await person_file.read()
    if len(garment_bytes) == 0 or len(person_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded files cannot be empty",
        )

    garment_image = Image.open(BytesIO(garment_bytes)).convert("RGB")
    person_image = Image.open(BytesIO(person_bytes)).convert("RGB")

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

    thresholds = _v2_thresholds(strict_mode=(mode == "strict"))
    gate = evaluate_input_gate(
        person_image=person_image,
        garment_image=garment_image,
        garment_category=garment_category,
        strict=(mode == "strict"),
        thresholds=thresholds,
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
        supported_garment_categories=["bottom", "pants", "skirt", "下装", "裤装", "裙装"],
        modes=["strict", "balanced"],
        thresholds=_v2_thresholds(strict_mode=True),
    )
