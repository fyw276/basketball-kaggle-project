"""
Image recognition API endpoints
"""

from typing import Any, List

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.logging import setup_logging
from app.ml.image_recognizer import RecognitionResult
from app.schemas.garment import ColorSchema
from app.services import local_inference

logger = setup_logging()

router = APIRouter(prefix="/recognition", tags=["Recognition"])

# Initialize classifiers (singleton pattern)
_category_classifier = None
_color_extractor = None
_image_recognizer = None


def get_category_classifier() -> Any:
    """Get or create category classifier instance"""
    global _category_classifier
    if _category_classifier is None:
        logger.info("Initializing CategoryClassifier")
        from app.ml.category_classifier import CategoryClassifier

        _category_classifier = CategoryClassifier()
    return _category_classifier


def get_color_extractor() -> Any:
    """Get or create color extractor instance"""
    global _color_extractor
    if _color_extractor is None:
        logger.info("Initializing ColorExtractor")
        from app.ml.color_extractor import ColorExtractor

        _color_extractor = ColorExtractor(n_colors=3)
    return _color_extractor


def get_image_recognizer() -> Any:
    """Get or create image recognizer instance"""
    global _image_recognizer
    if _image_recognizer is None:
        logger.info("Initializing ImageRecognizer")
        from app.ml.image_recognizer import ImageRecognizer

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


# ===== 微调模型端点（新增）=====


class FinetuedCategoryResponse(BaseModel):
    """微调推理模型的类别识别响应"""

    category: str = Field(..., description="识别的衣服类别")
    category_confidence: float = Field(..., ge=0, le=1, description="类别置信度")
    style_tags: List[str] = Field(default_factory=list, description="风格标签")
    fit_type: str = Field(default="regular", description="剪裁类型")
    occasions: List[str] = Field(default_factory=list, description="适合场合")
    feature_vector: List[float] = Field(default_factory=list, description="特征向量(32维)")

    class Config:
        json_schema_extra = {
            "example": {
                "category": "上衣",
                "category_confidence": 0.85,
                "style_tags": ["casual", "comfort"],
                "fit_type": "regular",
                "occasions": ["daily", "work"],
                "feature_vector": [0.1, 0.2, 0.3, 0.4],
            }
        }


@router.post(
    "/category-v2",
    response_model=FinetuedCategoryResponse,
    status_code=status.HTTP_200_OK,
    summary="识别衣服类别 (微调模型版本 v2)",
    description="""
    使用微调的 CLIP 模型识别衣服类别。

    相比 v1 版本的改进：
    - 更高的识别准确率（通过课程学习和硬案例挖掘）
    - 返回更详细的属性信息（风格标签、场合等）
    - 包含特征向量用于相似度计算

    支持的衣服类别：
    - 上衣 (Tops)
    - 裤子 (Pants)
    - 裙子 (Skirts)
    - 外套 (Outerwear)
    - 鞋 (Shoes)
    - 包 (Bags)

    **注意**: 该端点需要推理 API 服务运行在 http://127.0.0.1:9000
    """,
)
async def recognize_category_v2(
    file: UploadFile = File(..., description="衣服图片文件 (JPEG, PNG, WebP)")
):
    """
    使用微调模型识别衣服类别

    Args:
        file: 上传的图片文件

    Returns:
        FinetuedCategoryResponse: 类别和详细属性信息
    """
    # 验证文件类型
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件必须是图片 (JPEG, PNG, 或 WebP)",
        )

    try:
        # 读取图片字节
        image_bytes = await file.read()

        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="上传的文件为空",
            )

        # 使用本地推理服务（不经过 HTTP）
        result = local_inference.infer(image_bytes, hint="unknown", image_path=file.filename or "")

        logger.info(
            f"微调模型识别成功: {result.get('category')} "
            f"(置信度: {result.get('category_confidence', 0):.3f})"
        )

        return FinetuedCategoryResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"微调模型识别失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"识别失败: {str(e)}",
        )


@router.post(
    "/category-finetuned",
    response_model=FinetuedCategoryResponse,
    deprecated=False,
    status_code=status.HTTP_200_OK,
    summary="识别衣服类别 (微调模型) - 别名",
    description="与 /category-v2 功能相同",
)
async def recognize_category_finetuned(
    file: UploadFile = File(..., description="衣服图片文件 (JPEG, PNG, WebP)")
):
    """别名端点，指向 recognize_category_v2"""
    return await recognize_category_v2(file)


# ============ 批处理和缓存接口 ============


class BatchRecognitionRequest(BaseModel):
    """Batch recognition request"""

    images: List[str] = Field(..., description="Base64 encoded images or file IDs")


class CacheStatsResponse(BaseModel):
    """Cache statistics response"""

    recognition_cache: dict = Field(..., description="Recognition cache stats")
    similarity_cache: dict = Field(..., description="Similarity cache stats")


@router.post(
    "/batch-recognize",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="批量识别衣服类别",
    description="同时识别多张图片 (性能优化)",
)
async def batch_recognize_category(files: List[UploadFile] = File(...)):
    """
    批量识别多张衣服图片

    Performance:
    - Single image: ~16ms
    - Batch (N images): ~20-100ms total (parallel processing)
    - Expected speedup: 3-5x faster than sequential requests
    """
    if not files or len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image required"
        )

    if len(files) > 50:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Maximum 50 images per batch",
        )

    try:
        from app.services.batch_service import batch_processor

        # Read all file bytes
        image_bytes_list = []
        for file in files:
            content = await file.read()
            if not content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Empty file: {file.filename}"
                )
            image_bytes_list.append(content)

        # Process batch
        results = await batch_processor.process_batch(
            image_bytes_list, recognition_fn=lambda img: local_inference.infer(img)
        )

        return {
            "success": True,
            "data": {
                "batch_size": len(files),
                "results": results,
                "statistics": batch_processor.stats(),
            },
            "error": None,
            "message": f"Successfully recognized {len(results)} images",
        }

    except Exception as e:
        logger.error(f"Batch recognition error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch recognition failed: {str(e)}",
        )


@router.get(
    "/cache/stats",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="获取缓存统计",
    description="查看识别结果缓存命中率和大小",
)
async def get_cache_statistics():
    """Get recognition cache statistics"""
    try:
        from app.services.cache_service import get_cache_stats

        stats = get_cache_stats()
        return {"success": True, "data": stats, "error": None, "message": "ok"}
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cache statistics: {str(e)}",
        )


@router.post(
    "/cache/clear",
    status_code=status.HTTP_200_OK,
    summary="清空缓存",
    description="清除所有识别结果缓存",
)
async def clear_all_caches():
    """Clear all recognition caches"""
    try:
        from app.services.cache_service import clear_all_caches

        clear_all_caches()
        return {
            "success": True,
            "data": {"cleared": True},
            "error": None,
            "message": "All caches cleared",
        }
    except Exception as e:
        logger.error(f"Failed to clear caches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear caches: {str(e)}",
        )
