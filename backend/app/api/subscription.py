"""Subscription / usage quota / payment endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.subscription_billing import (
    consume_usage,
    create_subscription_order,
    get_or_create_subscription,
    get_usage_status,
    verify_subscription_payment,
)

router = APIRouter(prefix="/subscription", tags=["Subscription"])
usage_router = APIRouter(prefix="/usage", tags=["Subscription"])


class CreateOrderRequest(BaseModel):
    tier: str = Field("pro", description="subscription tier")


class VerifyPaymentRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str


class ConsumeUsageRequest(BaseModel):
    action: str
    units: int = Field(1, ge=1, le=20)


@router.get("/status")
def get_subscription_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = get_or_create_subscription(db, current_user.user_id)
    smart = get_usage_status(db, current_user.user_id, "smart_outfit_generate")
    tryon = get_usage_status(db, current_user.user_id, "tryon_generate")
    return {
        "plan": sub.plan,
        "status": sub.status,
        "provider": sub.provider,
        "valid_until": sub.valid_until.isoformat() if sub.valid_until else "",
        "usage": {
            "smart_outfit_generate": smart,
            "tryon_generate": tryon,
        },
    }


@router.post("/order")
def create_order(
    body: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = create_subscription_order(db, current_user.user_id, body.tier)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "order_id": order.order_id,
        "tier": order.tier,
        "amount": order.amount,
        "currency": order.currency,
        "provider": order.provider,
        "status": order.status,
    }


@router.post("/verify")
def verify_order(
    body: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = verify_subscription_payment(
        db,
        current_user.user_id,
        order_id=body.order_id,
        payment_id=body.payment_id,
        signature=body.signature,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "payment verification failed",
                "error_code": str(result.get("error") or "verify_failed"),
            },
        )
    return result


@usage_router.post("/consume")
def consume_action(
    body: ConsumeUsageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    out = consume_usage(
        db,
        current_user.user_id,
        body.action,
        units=body.units,
    )
    if not out.get("allowed"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": "quota exceeded",
                "error_code": "QUOTA_EXCEEDED",
                "requires_upgrade": True,
                "action": body.action,
                "remaining": out.get("remaining", 0),
                "limit": out.get("limit", 0),
            },
        )
    return out


@usage_router.get("/status")
def usage_status(
    action: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_usage_status(db, current_user.user_id, action)
