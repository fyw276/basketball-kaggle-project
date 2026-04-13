"""Aggregate user feedback into rerank weights and analytics helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.feedback_event import FeedbackEvent
from app.models.garment import Garment
from app.models.outfit_collection import OutfitCollection


@dataclass(frozen=True)
class FeedbackRerankContext:
    """Passed into OutfitRecommender3D for light boosting."""

    liked_garment_ids: Set[str]
    style_tag_boost: Dict[str, float]


def get_rerank_context(db: Session, user_id) -> FeedbackRerankContext:
    """From like/adopt events, build garment id set + normalized style tag weights."""
    rows = (
        db.query(FeedbackEvent)
        .filter(
            FeedbackEvent.user_id == user_id,
            FeedbackEvent.event_type.in_(("like", "adopt")),
        )
        .all()
    )
    liked_ids: Set[str] = set()
    tag_counts: Dict[str, int] = {}
    for e in rows:
        if e.garment_id:
            gid = str(e.garment_id)
            liked_ids.add(gid)
            g = db.query(Garment).filter(Garment.garment_id == e.garment_id).first()
            if g and g.style_tags:
                for t in g.style_tags or []:
                    tag_counts[str(t)] = tag_counts.get(str(t), 0) + 1
        pl = e.payload or {}
        if isinstance(pl, dict):
            for t in pl.get("style_tags") or []:
                tag_counts[str(t)] = tag_counts.get(str(t), 0) + 1
    if not tag_counts:
        return FeedbackRerankContext(liked_ids, {})
    mx = max(tag_counts.values())
    # 单标签最大加成分 0.02（与 recommender 内 cap 配合）
    weights = {k: 0.02 * (v / mx) for k, v in tag_counts.items()}
    return FeedbackRerankContext(liked_ids, weights)


def record_feedback_event(
    db: Session,
    *,
    user_id,
    event_type: str,
    source: str = "analysis_outfit",
    garment_id=None,
    collection_id: Optional[str] = None,
    scene: Optional[str] = None,
    payload: Optional[dict] = None,
) -> FeedbackEvent:
    ev = FeedbackEvent(
        user_id=user_id,
        event_type=event_type,
        source=source,
        garment_id=garment_id,
        collection_id=collection_id,
        scene=scene,
        payload=payload,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def analytics_summary(db: Session, user_id=None) -> dict:
    """核心指标：反馈结构 + 收藏占比（收藏数/活跃用户近似用反馈用户数）。"""
    q_fb = db.query(func.count(FeedbackEvent.event_id))
    q_col = db.query(func.count(OutfitCollection.collection_id))
    if user_id is not None:
        q_fb = q_fb.filter(FeedbackEvent.user_id == user_id)
        q_col = q_col.filter(OutfitCollection.user_id == user_id)

    total_feedback = int(q_fb.scalar() or 0)
    total_collections = int(q_col.scalar() or 0)

    likes = db.query(func.count(FeedbackEvent.event_id)).filter(FeedbackEvent.event_type == "like")
    adopts = db.query(func.count(FeedbackEvent.event_id)).filter(
        FeedbackEvent.event_type == "adopt"
    )
    dislikes = db.query(func.count(FeedbackEvent.event_id)).filter(
        FeedbackEvent.event_type == "dislike"
    )
    views = db.query(func.count(FeedbackEvent.event_id)).filter(FeedbackEvent.event_type == "view")
    if user_id is not None:
        likes = likes.filter(FeedbackEvent.user_id == user_id)
        adopts = adopts.filter(FeedbackEvent.user_id == user_id)
        dislikes = dislikes.filter(FeedbackEvent.user_id == user_id)
        views = views.filter(FeedbackEvent.user_id == user_id)

    n_like = int(likes.scalar() or 0)
    n_adopt = int(adopts.scalar() or 0)
    n_dislike = int(dislikes.scalar() or 0)
    n_view = int(views.scalar() or 0)

    positive = n_like + n_adopt
    # 核心指标 1：正向反馈率
    positive_rate = positive / total_feedback if total_feedback else 0.0
    # 核心指标 2：收藏率近似 = 套装数 / (正向反馈 + 套装) 避免除零，表示「沉淀为收藏」的比例
    denom = max(1, positive + total_collections)
    collection_rate = total_collections / denom

    return {
        "total_feedback_events": total_feedback,
        "counts_by_type": {
            "like": n_like,
            "adopt": n_adopt,
            "dislike": n_dislike,
            "view": n_view,
        },
        "outfit_collections_total": total_collections,
        "metrics": {
            "positive_feedback_rate": round(positive_rate, 4),
            "collection_rate_proxy": round(collection_rate, 4),
            "note": (
                "collection_rate_proxy = collections / (positive_feedback + collections), "
                "rough flywheel indicator"
            ),
        },
    }


def export_events_as_dicts(db: Session, user_id=None, limit: int = 10_000) -> List[dict]:
    """Flat rows for JSONL export."""
    q = db.query(FeedbackEvent).order_by(FeedbackEvent.created_at.desc()).limit(limit)
    if user_id is not None:
        q = q.filter(FeedbackEvent.user_id == user_id)
    out: List[dict] = []
    for e in q.all():
        out.append(
            {
                "event_id": str(e.event_id),
                "user_id": str(e.user_id),
                "event_type": e.event_type,
                "source": e.source,
                "garment_id": str(e.garment_id) if e.garment_id else None,
                "collection_id": e.collection_id,
                "scene": e.scene,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
        )
    return out
