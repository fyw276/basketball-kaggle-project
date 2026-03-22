"""
Garment service
Handles garment CRUD operations
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.garment import Garment
from app.schemas.garment import GarmentCreate, GarmentUpdate


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


def create_garment(db: Session, user_id: UUID, garment_in: GarmentCreate) -> Garment:
    """Create a new garment"""
    db_garment = Garment(
        user_id=user_id,
        category=garment_in.category,
        main_color=garment_in.main_color.model_dump(),
        secondary_colors=[c.model_dump() for c in garment_in.secondary_colors],
        style_tags=garment_in.style_tags,
        fit_type=garment_in.fit_type,
        image_path=garment_in.image_path,
        image_url=garment_in.image_url,
        feature_vector=garment_in.feature_vector,
        notes=garment_in.notes,
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
