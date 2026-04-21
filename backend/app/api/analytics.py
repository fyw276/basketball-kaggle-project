"""Aggregated metrics for data flywheel dashboards."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.api_response import success_response
from app.db.session import get_db
from app.models.user import User
from app.services.feedback_prefs import analytics_summary

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
async def get_summary(
    scope: Literal["user", "global"] = Query(
        "user",
        description="user = 当前用户；global = 全库汇总（演示/管理用）",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = None if scope == "global" else current_user.user_id
    data = analytics_summary(db, user_id=uid)
    return success_response(data, message="ok")


@router.get("/dependency-observability")
async def get_dependency_observability(
    _current_user: User = Depends(get_current_user),
):
    """天气 / 试衣 / AI / 混合推理外部增强：成功、失败、超时、降级计数与占比（单进程累计）。"""
    from app.observability.dependency_metrics import snapshot_rates

    return success_response(snapshot_rates(), message="ok")


@router.get("/tryon-v2-observability")
async def get_tryon_v2_observability(
    _current_user: User = Depends(get_current_user),
):
    """方案 A 试衣 v2：成功率、失败码分布、时延分位数（单进程累计）。"""
    from app.observability.tryon_v2_metrics import snapshot_tryon_v2_metrics

    return success_response(snapshot_tryon_v2_metrics(), message="ok")
