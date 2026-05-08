"""
Outfit Collection model for saving user-curated outfit sets
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.garment import UUID  # Import custom UUID type for consistency with User.user_id


class OutfitCollection(Base):
    """
    用户收藏/保存的套装模型

    一个套装由多件服装组成，用户可以保存推荐的套装或自己搭配的套装，
    并记录穿搭次数用于智能推荐。
    """

    __tablename__ = "outfit_collections"

    collection_id = Column(UUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(50), nullable=False)  # 套装名称
    scene = Column(String(20), nullable=False, index=True)  # 场景标签
    description = Column(Text, nullable=True)  # 套装描述/备注
    overall_score = Column(String(5), nullable=True)  # 综合评分 0-1
    worn_times = Column(String(10), default="0")  # 穿搭次数
    last_worn_at = Column(DateTime, nullable=True)  # 上次穿搭时间
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="outfit_collections")

    def __repr__(self):
        return f"<OutfitCollection(name={self.name}, scene={self.scene})>"


class OutfitCollectionItem(Base):
    """
    套装中的单件服装（关联表）
    """

    __tablename__ = "outfit_collection_items"

    item_id = Column(UUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id = Column(
        UUID(),
        ForeignKey("outfit_collections.collection_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    garment_id = Column(
        UUID(),
        ForeignKey("garments.garment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), default="other")  # top/bottom/outer/shoes/bag/other
    display_order = Column(String(5), default="0")  # 显示顺序
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships — back_populates resolved after OutfitCollection is defined below
    garment = relationship("Garment")
    collection = relationship(
        "OutfitCollection",
        back_populates="collection_items",
        foreign_keys=[collection_id],
        overlaps="items",
    )

    def __repr__(self):
        return f"<OutfitCollectionItem(collection={self.collection_id}, garment={self.garment_id})>"


# Add collection_items to OutfitCollection (must be after OutfitCollectionItem is defined)
OutfitCollection.collection_items = relationship(
    "OutfitCollectionItem",
    back_populates="collection",
    cascade="all, delete-orphan",
    overlaps="items",
)
