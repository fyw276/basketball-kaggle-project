"""
Outfit Collection API — 套装收藏管理
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.garment import (
    OutfitCollectionCreate,
    OutfitCollectionListResponse,
    OutfitCollectionResponse,
)
from app.services import garment as garment_service
from app.services.outfit_collection import (
    create_outfit_collection,
    delete_collection,
    get_collection_by_id,
    get_collections_by_user,
    record_worn,
)

router = APIRouter(prefix="/outfits", tags=["Outfit Collections"])


def _to_uuid_str(val) -> str:
    """Convert any UUID-like value to string."""
    if isinstance(val, UUID):
        return str(val)
    return str(val)


def _build_collection_response(collection, db: Session) -> OutfitCollectionResponse:
    """将 ORM 对象转换为响应 schema"""
    from app.schemas.garment import OutfitCollectionItem

    items = []
    for item in collection.collection_items:
        gid_str = _to_uuid_str(item.garment_id)
        g = garment_service.get_garment_by_id(db, UUID(gid_str))
        if g:
            items.append(
                OutfitCollectionItem(
                    garment_id=UUID(_to_uuid_str(g.garment_id)),
                    category=g.category,
                    name=g.name,
                    image_url=g.image_url,
                    role=item.role,
                )
            )

    return OutfitCollectionResponse(
        collection_id=UUID(_to_uuid_str(collection.collection_id)),
        user_id=UUID(_to_uuid_str(collection.user_id)),
        name=collection.name,
        scene=collection.scene,
        description=collection.description,
        items=items,
        overall_score=float(collection.overall_score) if collection.overall_score else None,
        worn_times=int(collection.worn_times or "0"),
        last_worn_at=collection.last_worn_at,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


@router.post(
    "/collections", response_model=OutfitCollectionResponse, status_code=status.HTTP_201_CREATED
)
async def save_outfit_collection(
    data: OutfitCollectionCreate,
    overall_score: Optional[float] = Query(
        None, ge=0, le=1, description="可选：推荐系统给定的综合评分"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存/收藏一个套装搭配"""
    # 验证所有 garment_id 属于当前用户
    for gid in data.garment_ids:
        try:
            g = garment_service.get_garment_by_id(db, UUID(gid))
            if not g or str(g.user_id) != str(current_user.user_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"服装ID {gid} 不存在或不属于您",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的服装ID格式：{gid}",
            )

    collection = create_outfit_collection(db, current_user.user_id, data, overall_score)
    db.refresh(collection)
    return _build_collection_response(collection, db)


@router.get("/collections", response_model=OutfitCollectionListResponse)
def list_outfit_collections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    scene: Optional[str] = Query(None, description="场景过滤"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户的套装收藏列表"""
    skip = (page - 1) * page_size
    collections, total = get_collections_by_user(
        db, current_user.user_id, skip=skip, limit=page_size, scene=scene
    )
    items = [_build_collection_response(c, db) for c in collections]
    return OutfitCollectionListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/collections/{collection_id}", response_model=OutfitCollectionResponse)
def get_outfit_collection(
    collection_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单个套装详情"""
    try:
        uid = UUID(collection_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的ID格式")

    collection = get_collection_by_id(db, str(uid), current_user.user_id)
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="套装不存在")

    return _build_collection_response(collection, db)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outfit_collection(
    collection_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除套装收藏"""
    success = delete_collection(db, str(collection_id), current_user.user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="套装不存在")
    return None


@router.post("/collections/{collection_id}/wear", response_model=OutfitCollectionResponse)
def wear_outfit(
    collection_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """记录一次穿搭（增加穿搭次数）"""
    try:
        uid = UUID(collection_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的ID格式")

    # 先检查权限
    collection = get_collection_by_id(db, str(uid), current_user.user_id)
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="套装不存在")

    # 增加穿搭次数
    collection = record_worn(db, str(uid), current_user.user_id)

    # 同时增加套装中每件服装的穿搭次数
    for item in collection.collection_items:
        garment_service.increment_wearing_count(db, UUID(_to_uuid_str(item.garment_id)))

    return _build_collection_response(collection, db)
