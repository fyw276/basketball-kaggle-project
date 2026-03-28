"""
User profile model for storing user preferences and characteristics
无性别推荐系统（修正版）：gender_expression 仅对女性生效
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.garment import UUID, JSONBCompat  # Import custom types


class UserProfile(Base):
    """User profile model for personalization - 无性别推荐（修正版）

    修正规则：
    - gender_expression 仅对女性生效
    - 男性用户不使用 gender_expression，按默认中性排序
    - explore_cross_gender=True 时，男性可小比例混入 neutral_score>0.7 的女款
    """

    __tablename__ = "user_profiles"

    profile_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    # 性别：可选
    gender = Column(String(10), nullable=True)  # 男/女/其他/None(未设置)
    # 性别表达指数：仅对女性生效
    gender_expression = Column(Float, nullable=True)  # 0-1, None 表示男性/未设置
    # 跨性别探索：仅对男性生效
    explore_cross_gender = Column(Boolean, nullable=False, default=False)
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
