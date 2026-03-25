"""
Simplified wardrobe API for easier frontend integration
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.ml.image_recognizer import ImageRecognizer
from app.models.user import User
from app.schemas.garment import GarmentCreate, GarmentListResponse, GarmentResponse
from app.services.garment import (
    count_garments_by_user,
    create_garment,
    delete_garment,
    get_garment_by_id,
    get_garments_by_user,
)
from app.services.storage import get_storage_service

router = APIRouter(prefix="/wardrobe/simple", tags=["Wardrobe (Simplified)"])


@router.post("/garments", response_model=GarmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_garment_simple(
    file: UploadFile = File(...),
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload garment image with automatic recognition (simplified API)

    This endpoint:
    1. Recognizes the uploaded image
    2. Saves the image file
    3. Creates the garment record

    No manual input required - everything is automatic!
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, WebP)",
        )

    try:
        # Read image bytes
        image_bytes = await file.read()

        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        # Reset file position for storage
        await file.seek(0)

        # Step 1: Recognize image
        try:
            recognizer = ImageRecognizer()
            recognition_result = recognizer.recognize(image_bytes)
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image recognition failed: {str(e)}",
            )

        # Step 2: Save image
        try:
            storage = get_storage_service()
            image_path, image_url = await storage.save_image(file, str(current_user.user_id))
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image storage failed: {str(e)}",
            )

        # Step 3: Create garment
        try:
            garment_in = GarmentCreate(
                category=recognition_result.category,
                main_color=recognition_result.main_color,
                secondary_colors=recognition_result.secondary_colors,
                style_tags=recognition_result.style_tags,
                fit_type=(
                    recognition_result.fit_type if hasattr(recognition_result, "fit_type") else None
                ),
                image_path=image_path,
                image_url=image_url,
                feature_vector=recognition_result.feature_vector,
                notes=notes,
            )

            garment = create_garment(db, current_user.user_id, garment_in)
            return garment
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database operation failed: {str(e)}",
            )

    except HTTPException:
        raise
    except ValueError as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image processing failed: {str(e)}",
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload garment: {str(e)}",
        )


@router.get("/garments", response_model=GarmentListResponse)
def list_garments_simple(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's garments with pagination and filtering (simplified API)"""
    skip = (page - 1) * page_size
    garments = get_garments_by_user(
        db, current_user.user_id, skip=skip, limit=page_size, category=category
    )
    total = count_garments_by_user(db, current_user.user_id, category=category)

    return GarmentListResponse(total=total, page=page, page_size=page_size, items=garments)


@router.delete("/garments/{garment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_garment_simple(
    garment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete garment (simplified API)"""
    from uuid import UUID

    try:
        garment_uuid = UUID(garment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid garment ID format"
        )

    garment = get_garment_by_id(db, garment_uuid)
    if not garment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Garment not found")

    # Check ownership
    if garment.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this garment",
        )

    # Delete image file
    storage = get_storage_service()
    storage.delete_image(garment.image_path)

    # Delete garment from database
    delete_garment(db, garment_uuid)

    return None
