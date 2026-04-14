from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user import User
from app.services.subscription_billing import (
    build_payment_signature,
    consume_usage,
    create_subscription_order,
    verify_subscription_payment,
)


def _make_db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def _seed_user(db):
    user = User(
        username="quota_user",
        email="quota_user@example.com",
        password_hash="x",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_consume_usage_blocks_when_limit_reached():
    db = _make_db_session()
    user = _seed_user(db)

    first = consume_usage(
        db,
        user.user_id,
        "smart_outfit_generate",
        limits_override={"smart_outfit_generate": 1},
    )
    second = consume_usage(
        db,
        user.user_id,
        "smart_outfit_generate",
        limits_override={"smart_outfit_generate": 1},
    )

    assert first["allowed"] is True
    assert second["allowed"] is False
    assert second["requires_upgrade"] is True


def test_verify_subscription_payment_signature_success_and_fail():
    db = _make_db_session()
    user = _seed_user(db)
    order = create_subscription_order(db, user.user_id, "pro")

    good_sig = build_payment_signature(order.order_id, "pay_001", "dev-secret")
    ok = verify_subscription_payment(
        db,
        user.user_id,
        order_id=order.order_id,
        payment_id="pay_001",
        signature=good_sig,
    )
    assert ok["ok"] is True
    assert ok["plan"] == "pro"

    order2 = create_subscription_order(db, user.user_id, "pro")
    bad = verify_subscription_payment(
        db,
        user.user_id,
        order_id=order2.order_id,
        payment_id="pay_002",
        signature="bad-signature",
    )
    assert bad["ok"] is False
    assert bad["error"] == "invalid_signature"
