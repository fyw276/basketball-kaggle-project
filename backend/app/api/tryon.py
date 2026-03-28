"""
Virtual Try-On API endpoints
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.storage import get_storage_service

router = APIRouter(prefix="/tryon", tags=["Virtual Try-On"])


class TryOnResponse(BaseModel):
    """Virtual try-on response"""

    status: str = Field(..., description="Status: success/fallback/error")
    message: str = Field(..., description="Human-readable status message")
    result_image_url: str = Field(None, description="URL of the try-on result image")
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


@router.post("/garment", response_model=TryOnResponse)
async def try_on_garment(
    garment_file: UploadFile = File(..., alias="garment_file", description="Garment product photo"),
    person_file: UploadFile = File(..., alias="person_file", description="Person photo"),
    prompt: str = "",
    # 无性别推荐系统新增参数
    model_gender: str = "neutral",
    current_user: User = Depends(get_current_user),
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

        result = service.tryon_garment(
            garment_image=garment_image,
            person_image=person_image,
            prompt=prompt or None,
            model_gender=model_gender,
        )

        # Save result image
        if result["result_image"] is not None:
            # Save the result
            output = BytesIO()
            result["result_image"].save(output, format="JPEG", quality=90)
            output.seek(0)

            # Use a temporary UploadFile-like object for storage
            result_path = os.path.join(
                str(current_user.user_id), "tryon", f"result_{hash(garment_bytes) % 100000:05d}.jpg"
            )

            storage_service = get_storage_service()
            saved_path, result_url = storage_service._save_bytes(output.getvalue(), result_path)
            result_image_url = result_url
        else:
            result_image_url = None

        return TryOnResponse(
            status=result["status"],
            message=result["message"],
            result_image_url=result_image_url,
            metadata=result.get("metadata", {}),
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Virtual try-on failed: {str(e)}",
        )
