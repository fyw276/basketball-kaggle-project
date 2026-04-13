"""User feedback events for reranking, analytics, and data flywheel."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.garment import UUID, JSONBCompat


class FeedbackEvent(Base):
    """点赞 / 踩 / 采纳搭配 / 曝光等，用于简单重排与指标。"""

    __tablename__ = "feedback_events"

    event_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(32), nullable=False, index=True)
    source = Column(String(32), nullable=False, default="analysis_outfit")
    garment_id = Column(
        UUID(), ForeignKey("garments.garment_id", ondelete="SET NULL"), nullable=True
    )
    collection_id = Column(String(36), nullable=True)
    scene = Column(String(64), nullable=True)
    payload = Column(JSONBCompat, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", backref="feedback_events")

    def __repr__(self):
        return f"<FeedbackEvent(type={self.event_type}, user={self.user_id})>"
