"""
Wardrobe (garment) API endpoints
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
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
    GarmentSearchQuery,
    GarmentUpdate,
)
from app.services.garment import (
    count_garments_by_user,
    create_garment,
    delete_garment,
    get_garment_by_id,
    get_garments_by_user,
    search_garments,
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
    category: str = Form(..., description="服装品类"),
    main_color_name: str = Form(..., description="主颜色名称"),
    main_color_rgb: str = Form(..., description="RGB值，格式：r,g,b"),
    main_color_hsv: str = Form(..., description="HSV值，格式：h,s,v"),
    main_color_hex: str = Form(..., description="十六进制颜色码"),
    style_tags: str = Form("", description="风格标签，逗号分隔"),
    fit_type: Optional[str] = Form(None, description="版型"),
    notes: Optional[str] = Form(None, description="备注"),
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


# ─── Search endpoint ─────────────────────────────────────────────────────────


@router.post("/garments/search", response_model=GarmentListResponse)
def search_garments_endpoint(
    query_params: GarmentSearchQuery,
    page: int = Query(1, ge=1, description="页码（与body参数合并使用）"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    高级搜索服装

    支持多维度过滤：
    - keyword: 关键词（匹配名称/备注）
    - category: 品类
    - style_tags: 风格标签列表（AND匹配）
    - color_name: 颜色名称（如：蓝/红/黑）
    - is_favorite: 仅收藏的
    - season: 季节（春夏/秋冬/全年）
    - min_worn: 最小穿搭次数
    - sort_by: 排序字段（created_at/worn_times/category）
    - sort_order: 排序方向（asc/desc）
    """
    skip = (page - 1) * page_size
    items, total = search_garments(db, current_user.user_id, query_params)

    # Apply pagination
    paginated_items = items[skip : skip + page_size]

    return GarmentListResponse(total=total, page=page, page_size=page_size, items=paginated_items)


@router.patch("/garments/{garment_id}/favorite", response_model=GarmentResponse)
def toggle_favorite_endpoint(
    garment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """快速切换收藏状态"""
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Toggle favorite
    current_fav = garment.is_favorite == "1"
    garment.is_favorite = "0" if current_fav else "1"
    db.commit()
    db.refresh(garment)

    return garment


# ─── Outfit Split endpoint ──────────────────────────────────────────────────


class OutfitSplitItem(BaseModel):
    """拆分后的单个服饰"""

    garment_id: Optional[str] = None
    category: str
    image_url: str
    confidence: float = 0.5


class OutfitSplitResponse(BaseModel):
    """整套穿搭拆分响应"""

    items: List[OutfitSplitItem]
    message: str = "拆分完成"


@router.post("/split-outfit", response_model=OutfitSplitResponse)
async def split_outfit_image(
    file: UploadFile = File(...),
    # multipart 与 File 同请求时须用 Form；误用 Query 会导致客户端写在 form 里的 save 无法绑定，恒为 false、永不入库
    save: bool = Form(False, description="是否直接保存到衣橱"),
    selected_indexes: Optional[str] = Form(
        None, description="要保存的单品索引，逗号分隔，如 '0,2'"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传整套穿搭图片，自动拆分识别单品。

    参数：
    - save: 如果为 True，直接保存到衣橱数据库
    - selected_indexes: 要保存的单品索引，逗号分隔（如 '0,2'），save=True 时有效

    返回识别出的单品列表，每个单品包含：
    - garment_id: 存入衣橱后的ID（save=True时有值）
    - category: 识别出的分类
    - image_url: 裁剪后的单品图片URL
    - confidence: 识别置信度
    """
    import io

    from PIL import Image

    # 验证文件
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    # 读取图片
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file cannot be empty"
        )

    # 解析选中的索引
    selected_set = set()
    if selected_indexes:
        try:
            selected_set = set(
                int(x.strip()) for x in selected_indexes.split(",") if x.strip().isdigit()
            )
        except ValueError:
            pass  # 忽略无效格式

    # 拆分结果
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        items = []

        # 简单启发式：根据高度比例估算
        if height > width * 1.2:  # 可能是全身照
            categories = [
                (0, "上衣", 0.0, 0.4, 0.85),
                (1, "裤子", 0.35, 0.7, 0.80),
                (2, "鞋", 0.65, 1.0, 0.75),
            ]
        else:  # 可能是单件或上半身
            categories = [
                (0, "上衣", 0.0, 0.6, 0.90),
                (1, "裤子", 0.4, 1.0, 0.70),
            ]

        storage = get_storage_service()

        for idx, cat_name, top_ratio, bottom_ratio, confidence in categories:
            # 裁剪区域
            top = int(height * top_ratio)
            bottom = int(height * bottom_ratio)

            # 确保有效区域
            if bottom <= top or bottom - top < height * 0.1:
                continue

            cropped = img.crop((0, top, width, bottom))

            # 保存裁剪后的单品图
            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=85)
            buf.seek(0)

            # 生成文件名
            import hashlib
            import time

            file_hash = hashlib.md5(
                f"{file.filename}{time.time()}{idx}{cat_name}".encode()
            ).hexdigest()[:8]
            sub_path = f"{current_user.user_id}/split/{file_hash}_{idx}_{cat_name}.jpg"
            saved_path, item_url = storage._save_bytes(buf.getvalue(), sub_path)

            garment_id = None

            # 如果需要保存到数据库，且该索引被选中
            if save and (len(selected_set) == 0 or idx in selected_set):
                try:
                    from app.ml.color_extractor import ColorExtractor
                    from app.ml.split_local_features import local_split_feature_vector
                    from app.schemas.garment import ColorSchema, GarmentCreate

                    crop_bytes = buf.getvalue()
                    # 不使用 CLIP：避免 Hugging Face 下载阻塞整次请求导致前端超时（弱网/国内常见）
                    feature_vector = local_split_feature_vector(crop_bytes)

                    color_extractor = ColorExtractor(n_colors=3)
                    colors = color_extractor.extract_colors(crop_bytes)
                    default_color = ColorSchema(
                        name="灰",
                        rgb=(128, 128, 128),
                        hsv=(0.0, 0.0, 50.0),
                        hex_code="#808080",
                    )
                    main_color = colors[0] if colors else default_color
                    secondary_colors = colors[1:] if len(colors) > 1 else []

                    final_cat = cat_name.strip()
                    if final_cat not in VALID_CATEGORIES:
                        final_cat = "上衣"

                    style_tags = ["休闲"]
                    fit_type = None

                    garment_in = GarmentCreate(
                        category=final_cat,
                        main_color=main_color,
                        secondary_colors=secondary_colors,
                        style_tags=style_tags[:20],
                        fit_type=fit_type,
                        image_path=saved_path,
                        image_url=item_url,
                        feature_vector=feature_vector,
                        notes="从整套穿搭中拆分",
                    )

                    garment = create_garment(db, current_user.user_id, garment_in)
                    garment_id = str(garment.garment_id)
                except Exception as e:
                    import traceback

                    traceback.print_exc()
                    print(f"保存拆分单品失败: {e}")

            items.append(
                OutfitSplitItem(
                    category=cat_name,
                    image_url=item_url,
                    garment_id=garment_id,
                    confidence=confidence,
                )
            )

        saved_count = sum(1 for item in items if item.garment_id)
        msg = f"识别到 {len(items)} 件单品"
        if save and saved_count > 0:
            msg += f"（已保存 {saved_count} 件到衣橱）"
        elif save:
            msg += "（预览模式）"
        else:
            msg += "（预览模式）"

        return OutfitSplitResponse(items=items, message=msg)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image processing failed: {str(e)}",
        )
