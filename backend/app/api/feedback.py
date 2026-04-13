"""User feedback events (like / adopt / view / dislike)."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.api_response import success_response
from app.db.session import get_db
from app.models.user import User
from app.services.feedback_prefs import record_feedback_event

router = APIRouter(prefix="/feedback", tags=["Feedback"])


class FeedbackCreate(BaseModel):
    event_type: str = Field(..., description="like | dislike | adopt | view")
    source: str = Field(
        "analysis_outfit", description="analysis_outfit | smart_outfit | collection | mood | other"
    )
    garment_id: Optional[str] = None
    collection_id: Optional[str] = None
    scene: Optional[str] = None
    payload: Optional[dict] = None


@router.post("/events")
async def create_feedback_event(
    body: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.event_type not in ("like", "dislike", "adopt", "view"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="event_type must be like, dislike, adopt, or view",
        )
    gid = None
    if body.garment_id:
        try:
            gid = UUID(body.garment_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid garment_id: {exc}",
            ) from exc

    ev = record_feedback_event(
        db,
        user_id=current_user.user_id,
        event_type=body.event_type,
        source=body.source or "analysis_outfit",
        garment_id=gid,
        collection_id=body.collection_id,
        scene=body.scene,
        payload=body.payload,
    )
    return success_response(
        {
            "event_id": str(ev.event_id),
            "event_type": ev.event_type,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        },
        message="ok",
    )
