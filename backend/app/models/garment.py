"""
Garment model for wardrobe management
"""

import json
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import CHAR, JSON
from sqlalchemy.types import Text as TextType

from app.db.base import Base


# Custom UUID type that works with both PostgreSQL and SQLite
class UUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's UUID type, otherwise uses CHAR(36), storing as stringified hex values.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            else:
                return str(uuid.UUID(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if isinstance(value, uuid.UUID):
                return value
            else:
                return uuid.UUID(value)


# Custom ARRAY type that works with both PostgreSQL and SQLite
class JSONEncodedArray(TypeDecorator):
    """Represents an immutable structure as a JSON-encoded string for SQLite."""

    impl = TextType
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(FLOAT))
        else:
            return dialect.type_descriptor(TextType())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        else:
            return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        else:
            return json.loads(value)


# Custom JSONB type that works with both PostgreSQL and SQLite
class JSONBCompat(TypeDecorator):
    """Platform-independent JSONB type."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB)
        else:
            return dialect.type_descriptor(JSON)


class Garment(Base):
    """Garment model for wardrobe items"""

    __tablename__ = "garments"

    garment_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=True)  # 服装名称
    category = Column(String(20), nullable=False, index=True)  # 上衣/裤子/裙子/外套/鞋/包
    main_color = Column(JSONBCompat, nullable=False)  # Color object as JSON
    secondary_colors = Column(JSONBCompat, default=list)  # List of Color objects
    style_tags = Column(JSONBCompat, default=list)  # List of style tags
    fit_type = Column(String(20))  # 修身/宽松/标准/oversized
    image_path = Column(String(500), nullable=False)
    image_url = Column(String(500), nullable=False)
    feature_vector = Column(JSONEncodedArray, nullable=False)  # 1280-dimensional feature vector
    notes = Column(Text)
    is_favorite = Column(CHAR(1), default="0")  # 0=否, 1=是
    wearing_count = Column(String(10), default="0")  # 穿搭次数
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="garments")

    def __repr__(self):
        return (
            f"<Garment(garment_id={self.garment_id}, "
            f"category={self.category}, user_id={self.user_id})>"
        )
