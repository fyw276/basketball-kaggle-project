"""
User profile model for storing user preferences and characteristics
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.garment import UUID, JSONBCompat  # Import custom types


class UserProfile(Base):
    """User profile model for personalization"""

    __tablename__ = "user_profiles"

    profile_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    height = Column(Integer, nullable=False)  # in centimeters
    body_type = Column(String(20), nullable=False)  # 偏瘦/微胖/梨形/倒三角/沙漏/矩形
    skin_tone = Column(String(20), nullable=False)  # 冷白/黄皮/小麦/深色
    style_preference = Column(JSONBCompat, nullable=False)  # List of style preferences
    budget_range = Column(String(20), nullable=False)  # 经济/中等/高端
    avoid_body_parts = Column(JSONBCompat, default=list)  # List of body parts to avoid emphasizing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"<UserProfile(profile_id={self.profile_id}, user_id={self.user_id})>"
