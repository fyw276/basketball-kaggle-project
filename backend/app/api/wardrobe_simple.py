"""
Simplified wardrobe API for easier frontend integration
"""

import io
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.ml.clip_recognizer import get_clip_recognizer
from app.models.user import User
from app.schemas.garment import (
    VALID_CATEGORIES,
    GarmentCreate,
    GarmentListResponse,
    GarmentResponse,
    GarmentUpdate,
)
from app.services.cache_service import get_cache
from app.services.finetuned_infer_client import try_finetuned_infer
from app.services.garment import (
    count_garments_by_user,
    create_garment,
    delete_garment,
    get_garment_by_id,
    get_garments_by_user,
    repair_garment_image_urls_for_user,
    update_garment,
)
from app.services.garment_visual import refresh_garment_visuals
from app.services.storage import get_storage_service

router = APIRouter(prefix="/wardrobe/simple", tags=["Wardrobe (Simplified)"])

# 前端侧边栏分类名 → 后端 VALID_CATEGORIES 中的标准品类
# 只映射前端独有的分类名到后端标准分类
_SIDEBAR_TO_BACKEND_CATEGORY = {
    "下装": "裤子",
    "鞋子": "鞋",
    "包包": "包",
    # "连衣裙" 已添加到 VALID_CATEGORIES，直接接受
}

# 自动识别细分类 → 侧栏大类，避免大量结果只落在“全部”。
_AUTO_FINE_TO_BASE_CATEGORY = {
    "鞋子": "鞋",
    "包包": "包",
    "上衣(汉)": "上衣",
    "下装(汉)": "裤子",
    "马面裙": "裙子",
    "连衣裙": "裙子",
    "汉服": "裙子",
    "国风": "裙子",
}


def _normalize_auto_category(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "上衣"
    s = _AUTO_FINE_TO_BASE_CATEGORY.get(s, s)
    if s in _SIDEBAR_TO_BACKEND_CATEGORY:
        s = _SIDEBAR_TO_BACKEND_CATEGORY[s]
    if s not in VALID_CATEGORIES:
        return "上衣"
    return s


def _normalize_category_for_update(raw: str) -> str:
    s = (raw or "").strip()
    if s in _SIDEBAR_TO_BACKEND_CATEGORY:
        return _SIDEBAR_TO_BACKEND_CATEGORY[s]
    return s


def _as_recognition_dict(recognition_result: Any) -> dict[str, Any]:
    """Normalize recognizer output to dict for unified downstream logic."""
    if isinstance(recognition_result, dict):
        return recognition_result
    if hasattr(recognition_result, "model_dump"):
        return recognition_result.model_dump()
    return {
        "category": getattr(recognition_result, "category", "上衣"),
        "category_confidence": getattr(recognition_result, "category_confidence", 0.0),
        "style_tags": getattr(recognition_result, "style_tags", []),
        "feature_vector": getattr(recognition_result, "feature_vector", []),
        "fit_type": getattr(recognition_result, "fit_type", None),
    }


def _recognize_with_cache(image_bytes: bytes) -> tuple[dict[str, Any], bool]:
    """Recognize image with cache-first strategy.

    Returns:
        (recognition_result_dict, cache_hit)
    """
    cache = get_cache()
    cached = cache.get(image_bytes)
    if cached is not None:
        return _as_recognition_dict(cached), True

    recognition_result = try_finetuned_infer(image_bytes, feature="wardrobe_simple_upload")
    if recognition_result is None:
        recognizer = get_clip_recognizer()
        recognition_result = recognizer.recognize(image_bytes)

    recognition_result_dict = _as_recognition_dict(recognition_result)
    cache.set(image_bytes, recognition_result_dict)
    return recognition_result_dict, False


@router.post("/garments", response_model=GarmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_garment_simple(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
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
    try:
        # Read image bytes
        image_bytes = await file.read()

        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        # Web 端 multipart 常为 application/octet-stream，用魔数 / PIL 校验真实图片
        ct = (file.content_type or "").lower()
        if not ct.startswith("image/"):
            try:
                Image.open(io.BytesIO(image_bytes)).verify()
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File must be an image (JPEG, PNG, WebP)",
                )

        # Step 1: Recognize image using CLIP (FashionCLIP approach)
        try:
            recognition_result, _cache_hit = _recognize_with_cache(image_bytes)
        except (UnidentifiedImageError, ValueError, OSError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or unsupported image format (recommend JPEG/PNG/WebP)",
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image recognition failed: {str(e)}",
            )

        recognized_category = str(recognition_result.get("category") or "").strip()
        category_confidence = float(recognition_result.get("category_confidence") or 0.0)
        category_for_save = _normalize_auto_category(recognized_category)

        # 前端可显式传 category（手动选择或先前识别结果），优先使用并做统一规范化。
        if category is not None and category.strip():
            manual_category = _normalize_category_for_update(category.strip())
            if manual_category not in VALID_CATEGORIES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}",
                )
            category_for_save = manual_category

        # CLIP 不可用或置信度过低时，用 MobileNet 六大类兜底，保证侧栏分类可用。
        if category_confidence < 0.15:
            try:
                from app.ml.category_classifier import CategoryClassifier

                fallback_category, _ = CategoryClassifier().classify_category(image_bytes)
                category_for_save = _normalize_auto_category(fallback_category)
            except Exception:
                pass

        # Step 2: Save image
        try:
            storage = get_storage_service()
            # Reset file position for storage
            await file.seek(0)
            image_path, image_url = await storage.save_image(file, str(current_user.user_id))
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image storage failed: {str(e)}",
            )

        # Step 3: Create garment
        # CLIP feature dimension (768 for ViT-L/14, 512 for ViT-B/32)
        # Pad/truncate to 1280 for compatibility with existing schema
        clip_features = recognition_result["feature_vector"]
        feature_dim = len(clip_features)
        if feature_dim == 768:
            feature_vector = clip_features + [0.0] * 512  # Pad to 1280
        elif feature_dim == 512:
            feature_vector = clip_features + [0.0] * 768  # Pad to 1280
        else:
            feature_vector = clip_features[:1280] + [0.0] * max(0, 1280 - len(clip_features))

        try:
            from app.ml.color_extractor import ColorExtractor
            from app.schemas.garment import ColorSchema

            # Extract colors using existing ColorExtractor
            color_extractor = ColorExtractor(n_colors=3)
            colors = color_extractor.extract_colors(image_bytes)
            main_color = (
                colors[0]
                if colors
                else ColorSchema(
                    name="灰",
                    rgb=(128, 128, 128),
                    hsv=(0.0, 0.0, 50.0),
                    hex_code="#808080",
                    confidence=0.2,
                )
            )
            secondary_colors = colors[1:] if len(colors) > 1 else []

            garment_in = GarmentCreate(
                category=category_for_save,
                main_color=main_color,
                secondary_colors=secondary_colors,
                style_tags=recognition_result["style_tags"],
                fit_type=recognition_result.get("fit_type"),
                image_path=image_path,
                image_url=image_url,
                feature_vector=feature_vector,
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


@router.post("/garments/batch")
async def upload_garments_batch_simple(
    files: list[UploadFile] = File(...),
    category: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch upload garments with cache-first recognition.

    This endpoint enables production batch import flow and uses the same
    category normalization and fallback policy as single upload.
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
    if len(files) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size cannot exceed 20 files",
        )

    from app.ml.color_extractor import ColorExtractor
    from app.schemas.garment import ColorSchema

    storage = get_storage_service()
    color_extractor = ColorExtractor(n_colors=3)

    created_ids: list[int] = []
    failures: list[dict[str, str]] = []
    cache_hits = 0

    for idx, file in enumerate(files):
        filename = file.filename or f"file_{idx}"
        try:
            image_bytes = await file.read()
            if len(image_bytes) == 0:
                raise ValueError("Uploaded file is empty")

            ct = (file.content_type or "").lower()
            if not ct.startswith("image/"):
                Image.open(io.BytesIO(image_bytes)).verify()

            recognition_result, cache_hit = _recognize_with_cache(image_bytes)
            if cache_hit:
                cache_hits += 1

            recognized_category = str(recognition_result.get("category") or "").strip()
            category_confidence = float(recognition_result.get("category_confidence") or 0.0)
            category_for_save = _normalize_auto_category(recognized_category)

            if category is not None and category.strip():
                manual_category = _normalize_category_for_update(category.strip())
                if manual_category not in VALID_CATEGORIES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}"),
                    )
                category_for_save = manual_category

            if category_confidence < 0.15:
                try:
                    from app.ml.category_classifier import CategoryClassifier

                    fallback_category, _ = CategoryClassifier().classify_category(image_bytes)
                    category_for_save = _normalize_auto_category(fallback_category)
                except Exception:
                    pass

            await file.seek(0)
            image_path, image_url = await storage.save_image(file, str(current_user.user_id))

            clip_features = recognition_result.get("feature_vector") or []
            if not isinstance(clip_features, list) or len(clip_features) == 0:
                raise ValueError("Recognition feature_vector missing")

            feature_dim = len(clip_features)
            if feature_dim == 768:
                feature_vector = clip_features + [0.0] * 512
            elif feature_dim == 512:
                feature_vector = clip_features + [0.0] * 768
            else:
                feature_vector = clip_features[:1280] + [0.0] * max(0, 1280 - len(clip_features))

            colors = color_extractor.extract_colors(image_bytes)
            main_color = (
                colors[0]
                if colors
                else ColorSchema(
                    name="灰",
                    rgb=(128, 128, 128),
                    hsv=(0.0, 0.0, 50.0),
                    hex_code="#808080",
                    confidence=0.2,
                )
            )
            secondary_colors = colors[1:] if len(colors) > 1 else []

            garment_in = GarmentCreate(
                category=category_for_save,
                main_color=main_color,
                secondary_colors=secondary_colors,
                style_tags=recognition_result.get("style_tags") or [],
                fit_type=recognition_result.get("fit_type"),
                image_path=image_path,
                image_url=image_url,
                feature_vector=feature_vector,
                notes=notes,
            )

            garment = create_garment(db, current_user.user_id, garment_in)
            created_ids.append(int(garment.garment_id))
        except HTTPException as e:
            failures.append({"filename": filename, "error": str(e.detail)})
        except Exception as e:
            failures.append({"filename": filename, "error": str(e)})

    return {
        "created_count": len(created_ids),
        "failed_count": len(failures),
        "cache_hits": cache_hits,
        "created_ids": created_ids,
        "failures": failures,
    }


@router.get("/garments", response_model=GarmentListResponse)
def list_garments_simple(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's garments with pagination and filtering (simplified API)"""
    # Auto-repair legacy image_url values to reduce front-end broken image placeholders.
    repair_garment_image_urls_for_user(db, current_user.user_id)

    print(
        f"[Wardrobe] GET /garments: user={current_user.user_id}, category={category}, "
        f"page={page}, page_size={page_size}"
    )

    skip = (page - 1) * page_size
    garments = get_garments_by_user(
        db, current_user.user_id, skip=skip, limit=page_size, category=category
    )
    total = count_garments_by_user(db, current_user.user_id, category=category)

    # 打印前几件衣物的分类信息用于调试
    if garments:
        print(f"[Wardrobe] GET /garments 返回 {len(garments)} 件衣物:")
        for g in garments[:5]:
            print(f"  - {g.garment_id}: category={g.category}")

    return GarmentListResponse(total=total, page=page, page_size=page_size, items=garments)


@router.post("/garments/repair-image-urls")
def repair_garment_image_urls(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manual trigger: repair current user's broken/legacy garment image URLs."""
    stats = repair_garment_image_urls_for_user(db, current_user.user_id)
    return {
        "message": "ok",
        **stats,
    }


@router.patch("/garments/{garment_id}", response_model=GarmentResponse)
def patch_garment_simple(
    garment_id: str,
    body: GarmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新服饰（简化 API，用于拖拽改分类等）"""
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

    if garment.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this garment",
        )

    data = body.model_dump(exclude_unset=True)
    print(f"[Wardrobe] PATCH 更新衣物: garment_id={garment_id}, data={data}")

    if "category" in data and data["category"] is not None:
        normalized = _normalize_category_for_update(data["category"])
        print(f"[Wardrobe] PATCH 分类规范化: {data['category']} -> {normalized}")
        if normalized not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}",
            )
        data["category"] = normalized

    if not data:
        return garment

    update = GarmentUpdate(**data)
    result = update_garment(db, garment, update)
    print(f"[Wardrobe] PATCH 更新完成: category={result.category}")
    return result


@router.post("/garments/{garment_id}/reanalyze-visual", response_model=GarmentResponse)
def reanalyze_garment_visual_simple(
    garment_id: str,
    recategorize: bool = Query(
        False,
        description="If true, also re-run CLIP category + feature_vector from the stored image",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Re-extract colors from the saved file; optionally refresh category/features
    (same as upload pipeline).
    """
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

    if garment.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this garment",
        )

    try:
        return refresh_garment_visuals(db, garment, recategorize=recategorize)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image file missing on server; re-upload the garment or repair storage paths",
        )


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
