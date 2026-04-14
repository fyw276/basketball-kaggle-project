"""Subscription, usage quota and payment verification helpers."""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.subscription import PaymentOrder, UsageCounter, UserSubscription


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _period_key(now: Optional[datetime] = None) -> str:
    ts = now or _utcnow()
    return f"{ts.year:04d}-{ts.month:02d}"


def build_payment_signature(order_id: str, payment_id: str, secret: str) -> str:
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    key = (secret or "").encode("utf-8")
    return hmac.new(key, payload, sha256).hexdigest()


def _free_limits() -> Dict[str, int]:
    return {
        "smart_outfit_generate": int(getattr(settings, "FREE_QUOTA_SMART_OUTFIT", 60) or 60),
        "tryon_generate": int(getattr(settings, "FREE_QUOTA_TRYON", 30) or 30),
        "analysis_generate": int(getattr(settings, "FREE_QUOTA_ANALYSIS", 200) or 200),
    }


def _pro_limits() -> Dict[str, int]:
    return {
        "smart_outfit_generate": int(getattr(settings, "PRO_QUOTA_SMART_OUTFIT", 9999) or 9999),
        "tryon_generate": int(getattr(settings, "PRO_QUOTA_TRYON", 9999) or 9999),
        "analysis_generate": int(getattr(settings, "PRO_QUOTA_ANALYSIS", 9999) or 9999),
    }


def _resolve_limit(plan: str, action: str, limits_override: Optional[Dict[str, int]] = None) -> int:
    if limits_override and action in limits_override:
        return int(limits_override[action])
    action = str(action or "").strip()
    if plan == "pro":
        return _pro_limits().get(action, 9999)
    return _free_limits().get(action, 0)


def get_or_create_subscription(db: Session, user_id: UUID) -> UserSubscription:
    sub = db.query(UserSubscription).filter(UserSubscription.user_id == user_id).first()
    if not sub:
        sub = UserSubscription(user_id=user_id, plan="free", status="active", provider="local")
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    if sub.plan == "pro" and sub.valid_until and sub.valid_until < _utcnow():
        sub.plan = "free"
        sub.status = "active"
        sub.provider = "local"
        sub.valid_until = None
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


def get_usage_status(
    db: Session,
    user_id: UUID,
    action: str,
    *,
    limits_override: Optional[Dict[str, int]] = None,
) -> Dict[str, int | str | bool]:
    sub = get_or_create_subscription(db, user_id)
    period = _period_key()
    limit_count = _resolve_limit(sub.plan, action, limits_override=limits_override)
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.user_id == user_id,
            UsageCounter.action == action,
            UsageCounter.period_key == period,
        )
        .first()
    )
    used = int(row.used_count) if row else 0
    remaining = max(0, int(limit_count) - used)
    return {
        "plan": sub.plan,
        "period": period,
        "action": action,
        "used": used,
        "limit": int(limit_count),
        "remaining": remaining,
        "requires_upgrade": remaining <= 0,
    }


def consume_usage(
    db: Session,
    user_id: UUID,
    action: str,
    *,
    units: int = 1,
    limits_override: Optional[Dict[str, int]] = None,
) -> Dict[str, int | str | bool]:
    sub = get_or_create_subscription(db, user_id)
    period = _period_key()
    limit_count = _resolve_limit(sub.plan, action, limits_override=limits_override)

    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.user_id == user_id,
            UsageCounter.action == action,
            UsageCounter.period_key == period,
        )
        .first()
    )
    if not row:
        row = UsageCounter(
            user_id=user_id,
            action=action,
            period_key=period,
            used_count=0,
            limit_count=int(limit_count),
        )
        db.add(row)
        db.flush()

    used_now = int(row.used_count)
    need = max(1, int(units))
    if used_now + need > int(limit_count):
        db.commit()
        return {
            "allowed": False,
            "plan": sub.plan,
            "period": period,
            "action": action,
            "used": used_now,
            "limit": int(limit_count),
            "remaining": max(0, int(limit_count) - used_now),
            "requires_upgrade": True,
        }

    row.used_count = used_now + need
    row.limit_count = int(limit_count)
    db.add(row)
    db.commit()
    return {
        "allowed": True,
        "plan": sub.plan,
        "period": period,
        "action": action,
        "used": int(row.used_count),
        "limit": int(limit_count),
        "remaining": max(0, int(limit_count) - int(row.used_count)),
        "requires_upgrade": False,
    }


def create_subscription_order(db: Session, user_id: UUID, tier: str) -> PaymentOrder:
    tier_v = str(tier or "").strip().lower()
    if tier_v != "pro":
        raise ValueError("unsupported tier")

    amount = int(getattr(settings, "SUBSCRIPTION_PRO_MONTHLY_PRICE_CENTS", 1900) or 1900)
    currency = str(getattr(settings, "SUBSCRIPTION_CURRENCY", "CNY") or "CNY")
    order_id = f"ord_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}"

    order = PaymentOrder(
        order_id=order_id,
        user_id=user_id,
        tier=tier_v,
        amount=amount,
        currency=currency,
        provider=str(getattr(settings, "PAYMENT_PROVIDER_NAME", "local_hmac") or "local_hmac"),
        status="created",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def verify_subscription_payment(
    db: Session,
    user_id: UUID,
    *,
    order_id: str,
    payment_id: str,
    signature: str,
) -> Dict[str, str | bool]:
    order = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.order_id == order_id, PaymentOrder.user_id == user_id)
        .first()
    )
    if not order:
        return {"ok": False, "error": "order_not_found"}

    secret = str(getattr(settings, "PAYMENT_SIGNING_SECRET", "dev-secret") or "dev-secret")
    require_sig = bool(getattr(settings, "PAYMENT_REQUIRE_SIGNATURE", True))

    expected = build_payment_signature(order_id=order_id, payment_id=payment_id, secret=secret)
    if require_sig and not hmac.compare_digest(signature or "", expected):
        return {"ok": False, "error": "invalid_signature"}

    if order.status != "paid":
        order.status = "paid"
        order.payment_id = payment_id
        order.signature = signature
        order.paid_at = _utcnow()
        db.add(order)

    sub = get_or_create_subscription(db, user_id)
    days = int(getattr(settings, "SUBSCRIPTION_PRO_DURATION_DAYS", 30) or 30)
    now = _utcnow()
    base = sub.valid_until if (sub.valid_until and sub.valid_until > now) else now
    sub.plan = "pro"
    sub.status = "active"
    sub.provider = order.provider
    sub.valid_until = base + timedelta(days=days)
    db.add(sub)
    db.commit()
    db.refresh(sub)

    return {
        "ok": True,
        "plan": sub.plan,
        "valid_until": sub.valid_until.isoformat() if sub.valid_until else "",
        "order_id": order.order_id,
        "payment_id": payment_id,
    }
