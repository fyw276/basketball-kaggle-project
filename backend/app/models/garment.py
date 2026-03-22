"""
Garment model for wardrobe management
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT, JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Garment(Base):
    """Garment model for wardrobe items"""

    __tablename__ = "garments"

    garment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(20), nullable=False, index=True)  # 上衣/裤子/裙子/外套/鞋/包
    main_color = Column(JSONB, nullable=False)  # Color object as JSON
    secondary_colors = Column(JSONB, default=list)  # List of Color objects
    style_tags = Column(JSONB, default=list)  # List of style tags
    fit_type = Column(String(20))  # 修身/宽松/标准/oversized
    image_path = Column(String(500), nullable=False)
    image_url = Column(String(500), nullable=False)
    feature_vector = Column(ARRAY(FLOAT), nullable=False)  # 1280-dimensional feature vector
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="garments")

    def __repr__(self):
        return (
            f"<Garment(garment_id={self.garment_id}, "
            f"category={self.category}, user_id={self.user_id})>"
        )
