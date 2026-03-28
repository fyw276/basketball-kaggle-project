"""
Outfit Collection Service — 套装收藏 CRUD 操作
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.outfit_collection import OutfitCollection, OutfitCollectionItem
from app.schemas.garment import OutfitCollectionCreate


def create_outfit_collection(
    db: Session,
    user_id: UUID,
    data: OutfitCollectionCreate,
    overall_score: Optional[float] = None,
) -> OutfitCollection:
    """创建套装收藏"""
    collection = OutfitCollection(
        user_id=str(user_id),
        name=data.name,
        scene=data.scene,
        description=data.description,
        overall_score=str(overall_score) if overall_score is not None else None,
        worn_times="0",
    )
    db.add(collection)
    db.flush()

    for idx, garment_id_str in enumerate(data.garment_ids):
        item = OutfitCollectionItem(
            collection_id=collection.collection_id,
            garment_id=garment_id_str,
            display_order=str(idx),
            role="other",
        )
        db.add(item)

    db.commit()
    db.refresh(collection)
    return collection


def get_collection_by_id(
    db: Session,
    collection_id: str,
    user_id: UUID,
) -> Optional[OutfitCollection]:
    """根据ID获取套装收藏"""
    return (
        db.query(OutfitCollection)
        .filter(
            OutfitCollection.collection_id == collection_id,
            OutfitCollection.user_id == str(user_id),
        )
        .first()
    )


def get_collections_by_user(
    db: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
    scene: Optional[str] = None,
) -> tuple[List[OutfitCollection], int]:
    """获取用户所有套装收藏"""
    q = db.query(OutfitCollection).filter(OutfitCollection.user_id == str(user_id))
    if scene:
        q = q.filter(OutfitCollection.scene == scene)
    total = q.count()
    items = q.order_by(OutfitCollection.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def update_collection(
    db: Session,
    collection: OutfitCollection,
    name: Optional[str] = None,
    scene: Optional[str] = None,
    description: Optional[str] = None,
) -> OutfitCollection:
    """更新套装收藏信息"""
    if name is not None:
        collection.name = name
    if scene is not None:
        collection.scene = scene
    if description is not None:
        collection.description = description
    collection.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(collection)
    return collection


def delete_collection(db: Session, collection_id: str, user_id: UUID) -> bool:
    """删除套装收藏"""
    collection = get_collection_by_id(db, collection_id, user_id)
    if not collection:
        return False
    db.delete(collection)
    db.commit()
    return True


def record_worn(db: Session, collection_id: str, user_id: UUID) -> Optional[OutfitCollection]:
    """记录一次穿搭（增加次数并更新最后穿搭时间）"""
    collection = get_collection_by_id(db, collection_id, user_id)
    if not collection:
        return None
    try:
        collection.worn_times = str(int(collection.worn_times) + 1)
    except (ValueError, TypeError):
        collection.worn_times = "1"
    collection.last_worn_at = datetime.utcnow()
    db.commit()
    db.refresh(collection)
    return collection
