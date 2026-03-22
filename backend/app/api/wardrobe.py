"""
Wardrobe (garment) API endpoints
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.garment import (
    VALID_CATEGORIES,
    VALID_FIT_TYPES,
    VALID_STYLE_TAGS,
    ColorSchema,
    GarmentCreate,
    GarmentListResponse,
    GarmentResponse,
    GarmentUpdate,
)
from app.services.garment import (
    count_garments_by_user,
    create_garment,
    delete_garment,
    get_garment_by_id,
    get_garments_by_user,
    update_garment,
)
from app.services.storage import get_storage_service

router = APIRouter(prefix="/wardrobe", tags=["Wardrobe"])


def validate_garment_data(garment_data):
    """Validate garment data"""
    if hasattr(garment_data, "category") and garment_data.category:
        if garment_data.category not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}",
            )

    if hasattr(garment_data, "fit_type") and garment_data.fit_type:
        if garment_data.fit_type not in VALID_FIT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid fit_type. Must be one of: {', '.join(VALID_FIT_TYPES)}",
            )

    if hasattr(garment_data, "style_tags") and garment_data.style_tags:
        invalid_tags = [t for t in garment_data.style_tags if t not in VALID_STYLE_TAGS]
        if invalid_tags:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid style tags: {', '.join(invalid_tags)}. "
                f"Must be from: {', '.join(VALID_STYLE_TAGS)}",
            )


@router.post("/garments", response_model=GarmentResponse, status_code=status.HTTP_201_CREATED)
async def add_garment(
    category: str,
    main_color_name: str,
    main_color_rgb: str,  # Format: "r,g,b"
    main_color_hsv: str,  # Format: "h,s,v"
    main_color_hex: str,
    style_tags: str = "",  # Comma-separated
    fit_type: Optional[str] = None,
    notes: Optional[str] = None,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add a new garment to wardrobe

    Note: In production, this would call image recognition service.
    For now, we accept manual input for testing.
    """
    # Validate category
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}",
        )

    # Parse color data
    try:
        rgb = tuple(map(int, main_color_rgb.split(",")))
        hsv = tuple(map(float, main_color_hsv.split(",")))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid color format. RGB should be 'r,g,b', HSV should be 'h,s,v'",
        )

    main_color = ColorSchema(name=main_color_name, rgb=rgb, hsv=hsv, hex_code=main_color_hex)

    # Parse style tags
    tags = [t.strip() for t in style_tags.split(",") if t.strip()]

    # Validate style tags
    if tags:
        invalid_tags = [t for t in tags if t not in VALID_STYLE_TAGS]
        if invalid_tags:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid style tags: {', '.join(invalid_tags)}",
            )

    # Save image
    storage = get_storage_service()
    image_path, image_url = await storage.save_image(file, str(current_user.user_id))

    # Create dummy feature vector (in production, this would come from image recognition)
    feature_vector = [0.0] * 1280

    # Create garment
    garment_in = GarmentCreate(
        category=category,
        main_color=main_color,
        secondary_colors=[],
        style_tags=tags,
        fit_type=fit_type,
        image_path=image_path,
        image_url=image_url,
        feature_vector=feature_vector,
        notes=notes,
    )

    garment = create_garment(db, current_user.user_id, garment_in)

    return garment


@router.get("/garments", response_model=GarmentListResponse)
def list_garments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's garments with pagination and filtering"""
    # Validate category if provided
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}",
        )

    skip = (page - 1) * page_size
    garments = get_garments_by_user(
        db, current_user.user_id, skip=skip, limit=page_size, category=category
    )
    total = count_garments_by_user(db, current_user.user_id, category=category)

    return GarmentListResponse(total=total, page=page, page_size=page_size, items=garments)


@router.get("/garments/{garment_id}", response_model=GarmentResponse)
def get_garment(
    garment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get garment by ID"""
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
            detail="Not authorized to access this garment",
        )

    return garment


@router.put("/garments/{garment_id}", response_model=GarmentResponse)
def update_garment_endpoint(
    garment_id: str,
    garment_in: GarmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update garment"""
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
            detail="Not authorized to update this garment",
        )

    # Validate data
    validate_garment_data(garment_in)

    # Update garment
    updated_garment = update_garment(db, garment, garment_in)

    return updated_garment


@router.delete("/garments/{garment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_garment_endpoint(
    garment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete garment"""
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
