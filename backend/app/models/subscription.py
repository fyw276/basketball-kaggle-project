"""Subscription, usage quota, and payment order models."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.garment import UUID


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    subscription_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan = Column(String(16), nullable=False, default="free")
    status = Column(String(16), nullable=False, default="active")
    provider = Column(String(32), nullable=False, default="local")
    valid_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", backref="subscription")


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("user_id", "action", "period_key", name="uq_usage_user_action_period"),
    )

    usage_id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    action = Column(String(64), nullable=False, index=True)
    period_key = Column(String(16), nullable=False, index=True)
    used_count = Column(Integer, nullable=False, default=0)
    limit_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    order_id = Column(String(64), primary_key=True)
    user_id = Column(
        UUID(), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier = Column(String(16), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(16), nullable=False, default="CNY")
    provider = Column(String(32), nullable=False, default="local_hmac")
    status = Column(String(16), nullable=False, default="created")
    payment_id = Column(String(128), nullable=True)
    signature = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    paid_at = Column(DateTime, nullable=True)
