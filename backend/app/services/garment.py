"""
Garment service
Handles garment CRUD operations
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.garment import Garment
from app.schemas.garment import GarmentCreate, GarmentSearchQuery, GarmentUpdate


def get_garment_by_id(db: Session, garment_id: UUID) -> Optional[Garment]:
    """Get garment by ID"""
    return db.query(Garment).filter(Garment.garment_id == garment_id).first()


def get_garments_by_user(
    db: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
) -> List[Garment]:
    """Get all garments for a user with optional filtering"""
    query = db.query(Garment).filter(Garment.user_id == user_id)

    if category:
        query = query.filter(Garment.category == category)

    return query.offset(skip).limit(limit).all()


def count_garments_by_user(db: Session, user_id: UUID, category: Optional[str] = None) -> int:
    """Count garments for a user"""
    query = db.query(Garment).filter(Garment.user_id == user_id)

    if category:
        query = query.filter(Garment.category == category)

    return query.count()


def search_garments(
    db: Session,
    user_id: UUID,
    query: GarmentSearchQuery,
) -> tuple[List[Garment], int]:
    """
    高级搜索：根据多维度条件搜索服装

    支持：
    - keyword: 关键词（匹配名称/备注）
    - category: 品类过滤
    - style_tags: 风格标签（AND匹配）
    - color_name: 主颜色名称
    - is_favorite: 仅收藏的
    - min_worn: 最小穿搭次数
    - sort_by / sort_order: 排序
    """
    q = db.query(Garment).filter(Garment.user_id == user_id)

    # 关键词匹配（名称或备注）
    if query.keyword:
        kw = f"%{query.keyword}%"
        q = q.filter(
            or_(
                Garment.name.ilike(kw) if hasattr(Garment, "name") else False,
                Garment.notes.ilike(kw),
            )
        )

    # 品类过滤
    if query.category:
        q = q.filter(Garment.category == query.category)

    # 风格标签过滤（必须包含所有指定的标签）
    if query.style_tags:
        for tag in query.style_tags:
            q = q.filter(Garment.style_tags.contains(tag))

    # 颜色名称过滤
    if query.color_name:
        q = q.filter(Garment.main_color.contains(query.color_name))

    # 收藏过滤
    if query.is_favorite is not None:
        fav_val = "1" if query.is_favorite else "0"
        q = q.filter(Garment.is_favorite == fav_val)

    # 穿搭次数过滤
    if query.min_worn is not None:
        try:
            q = q.filter(Garment.wearing_count.cast(db.bind.dialect.name == "postgresql" and __import__("sqlalchemy").Integer) >= query.min_worn)
        except Exception:
            pass

    # 统计总数（排序前）
    total = q.count()

    # 排序
    sort_col = getattr(Garment, query.sort_by, Garment.created_at)
    if query.sort_order == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    items = q.all()
    return items, total


def create_garment(db: Session, user_id: UUID, garment_in: GarmentCreate) -> Garment:
    """Create a new garment"""
    db_garment = Garment(
        user_id=user_id,
        name=garment_in.name,
        category=garment_in.category,
        main_color=garment_in.main_color.model_dump(),
        secondary_colors=[c.model_dump() for c in garment_in.secondary_colors],
        style_tags=garment_in.style_tags,
        fit_type=garment_in.fit_type,
        image_path=garment_in.image_path,
        image_url=garment_in.image_url,
        feature_vector=garment_in.feature_vector,
        notes=garment_in.notes,
        is_favorite="1" if garment_in.is_favorite else "0",
        wearing_count=str(garment_in.wearing_count),
    )

    db.add(db_garment)
    db.commit()
    db.refresh(db_garment)

    return db_garment


def update_garment(db: Session, garment: Garment, garment_in: GarmentUpdate) -> Garment:
    """Update garment"""
    update_data = garment_in.model_dump(exclude_unset=True)

    # Convert color schemas to dict
    if "main_color" in update_data and update_data["main_color"]:
        update_data["main_color"] = update_data["main_color"].model_dump()

    if "secondary_colors" in update_data and update_data["secondary_colors"]:
        update_data["secondary_colors"] = [c.model_dump() for c in update_data["secondary_colors"]]

    # Convert boolean is_favorite to "0"/"1"
    if "is_favorite" in update_data and update_data["is_favorite"] is not None:
        update_data["is_favorite"] = "1" if update_data["is_favorite"] else "0"

    for field, value in update_data.items():
        setattr(garment, field, value)

    db.add(garment)
    db.commit()
    db.refresh(garment)

    return garment


def delete_garment(db: Session, garment_id: UUID) -> bool:
    """Delete garment"""
    garment = get_garment_by_id(db, garment_id)
    if garment:
        db.delete(garment)
        db.commit()
        return True
    return False


def increment_wearing_count(db: Session, garment_id: UUID) -> Optional[Garment]:
    """增加穿搭次数（用于记录实际穿搭）"""
    garment = get_garment_by_id(db, garment_id)
    if not garment:
        return None
    try:
        garment.wearing_count = str(int(garment.wearing_count or "0") + 1)
    except (ValueError, TypeError):
        garment.wearing_count = "1"
    db.commit()
    db.refresh(garment)
    return garment
