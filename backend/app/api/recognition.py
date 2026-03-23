"""
Image recognition API endpoints
"""

from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.logging import setup_logging
from app.ml.category_classifier import CategoryClassifier
from app.ml.color_extractor import ColorExtractor
from app.ml.image_recognizer import ImageRecognizer, RecognitionResult
from app.schemas.garment import ColorSchema

logger = setup_logging()

router = APIRouter(prefix="/recognition", tags=["Recognition"])

# Initialize classifiers (singleton pattern)
_category_classifier = None
_color_extractor = None
_image_recognizer = None


def get_category_classifier() -> CategoryClassifier:
    """Get or create category classifier instance"""
    global _category_classifier
    if _category_classifier is None:
        logger.info("Initializing CategoryClassifier")
        _category_classifier = CategoryClassifier()
    return _category_classifier


def get_color_extractor() -> ColorExtractor:
    """Get or create color extractor instance"""
    global _color_extractor
    if _color_extractor is None:
        logger.info("Initializing ColorExtractor")
        _color_extractor = ColorExtractor(n_colors=3)
    return _color_extractor


def get_image_recognizer() -> ImageRecognizer:
    """Get or create image recognizer instance"""
    global _image_recognizer
    if _image_recognizer is None:
        logger.info("Initializing ImageRecognizer")
        _image_recognizer = ImageRecognizer()
    return _image_recognizer


class CategoryRecognitionResponse(BaseModel):
    """Response model for category recognition"""

    category: str = Field(..., description="Recognized garment category")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    confidence_level: str = Field(..., description="Confidence level description")

    class Config:
        json_schema_extra = {
            "example": {
                "category": "上衣",
                "confidence": 0.85,
                "confidence_level": "高置信度",
            }
        }


@router.post(
    "/category",
    response_model=CategoryRecognitionResponse,
    status_code=status.HTTP_200_OK,
    summary="Recognize garment category from image",
    description="""
    Upload a garment image to recognize its category.

    Supported categories:
    - 上衣 (Tops)
    - 裤子 (Pants)
    - 裙子 (Skirts)
    - 外套 (Outerwear)
    - 鞋 (Shoes)
    - 包 (Bags)

    Returns the recognized category with confidence score.
    """,
)
async def recognize_category(
    file: UploadFile = File(..., description="Garment image file (JPEG, PNG, WebP)")
):
    """
    Recognize garment category from uploaded image

    Args:
        file: Uploaded image file

    Returns:
        CategoryRecognitionResponse: Category and confidence
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, or WebP)",
        )

    try:
        # Read image bytes
        image_bytes = await file.read()

        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        # Get classifier
        classifier = get_category_classifier()

        # Classify category
        category, confidence = classifier.classify_category(image_bytes)

        # Get confidence level
        confidence_level = classifier.get_confidence_level(confidence)

        logger.info(
            f"Category recognition successful: {category} "
            f"(confidence: {confidence:.3f}, level: {confidence_level})"
        )

        return CategoryRecognitionResponse(
            category=category,
            confidence=confidence,
            confidence_level=confidence_level,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Category recognition failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to recognize category: {str(e)}",
        )


@router.get(
    "/categories",
    summary="Get available garment categories",
    description="Returns the list of supported garment categories",
)
async def get_categories():
    """
    Get list of available garment categories

    Returns:
        dict: Category ID to name mapping
    """
    classifier = get_category_classifier()
    categories = classifier.get_categories()

    return {
        "categories": list(categories.values()),
        "count": len(categories),
    }


class ColorRecognitionResponse(BaseModel):
    """Response model for color recognition"""

    main_color: ColorSchema = Field(..., description="Main dominant color")
    secondary_colors: List[ColorSchema] = Field(
        default_factory=list, description="Secondary colors"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "main_color": {
                    "name": "蓝",
                    "rgb": (52, 120, 180),
                    "hsv": (210.0, 71.1, 70.6),
                    "hex_code": "#3478b4",
                },
                "secondary_colors": [
                    {
                        "name": "白",
                        "rgb": (240, 240, 240),
                        "hsv": (0.0, 0.0, 94.1),
                        "hex_code": "#f0f0f0",
                    }
                ],
            }
        }


@router.post(
    "/colors",
    response_model=ColorRecognitionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract dominant colors from garment image",
    description="""
    Upload a garment image to extract dominant colors using K-Means clustering.

    Returns:
    - Main color (most dominant)
    - Secondary colors (2nd and 3rd most dominant)

    Colors are mapped to 10 standard categories:
    红 (Red), 橙 (Orange), 黄 (Yellow), 绿 (Green), 蓝 (Blue),
    紫 (Purple), 黑 (Black), 白 (White), 灰 (Gray), 棕 (Brown)
    """,
)
async def recognize_colors(
    file: UploadFile = File(..., description="Garment image file (JPEG, PNG, WebP)")
):
    """
    Extract dominant colors from uploaded image

    Args:
        file: Uploaded image file

    Returns:
        ColorRecognitionResponse: Main and secondary colors
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, or WebP)",
        )

    try:
        # Read image bytes
        image_bytes = await file.read()

        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        # Get color extractor
        extractor = get_color_extractor()

        # Extract colors
        colors = extractor.extract_colors(image_bytes)

        # Split into main and secondary
        main_color = colors[0] if colors else None
        secondary_colors = colors[1:] if len(colors) > 1 else []

        if not main_color:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract colors from image",
            )

        logger.info(
            f"Color extraction successful: main={main_color.name}, "
            f"secondary={[c.name for c in secondary_colors]}"
        )

        return ColorRecognitionResponse(main_color=main_color, secondary_colors=secondary_colors)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Color recognition failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to recognize colors: {str(e)}",
        )


@router.post(
    "/analyze",
    response_model=RecognitionResult,
    status_code=status.HTTP_200_OK,
    summary="Complete image recognition analysis",
    description="""
    Upload a garment image for complete recognition analysis.

    This endpoint integrates all recognition modules to provide:
    - Category classification (6 categories)
    - Main and secondary color extraction
    - Style tag classification (12 styles)
    - 1280-dimensional feature vector extraction

    Performance target: < 2 seconds per image

    Supported image formats: JPEG, PNG, WebP
    """,
)
async def analyze_image(
    file: UploadFile = File(..., description="Garment image file (JPEG, PNG, WebP)")
):
    """
    Perform complete image recognition analysis

    This endpoint provides comprehensive garment analysis by integrating:
    - Category classification (上衣/裤子/裙子/外套/鞋/包)
    - Color extraction (main + secondary colors)
    - Style classification (通勤/休闲/正式/运动/街头/学院/甜美/简约/复古/朋克/民族/优雅)
    - Feature vector extraction (1280-dim for similarity analysis)

    Args:
        file: Uploaded image file

    Returns:
        RecognitionResult: Complete recognition result with all attributes

    Raises:
        HTTPException: 400 for invalid file, 500 for processing errors
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, or WebP)",
        )

    try:
        # Read image bytes
        image_bytes = await file.read()

        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        logger.info(f"Starting complete image analysis for file: {file.filename}")

        # Get image recognizer
        recognizer = get_image_recognizer()

        # Perform complete recognition
        result = recognizer.recognize(image_bytes)

        logger.info(
            f"Image analysis completed successfully: "
            f"category={result.category}, "
            f"main_color={result.main_color.name}, "
            f"styles={result.style_tags}"
        )

        return result

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Image analysis validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image data: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Image analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze image: {str(e)}",
        )
