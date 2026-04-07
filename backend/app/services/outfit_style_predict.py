"""
穿搭风格分（sklearn pipeline）+ 推荐列表与解释 — 供 backend.main 与 app.main 共用。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.external_enhance_client import call_external_enhance

_logger = logging.getLogger(__name__)

# backend/app/services -> parents[3] = 仓库根目录（与 backend/main.py 中 ROOT 一致）
_REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = _REPO_ROOT / "model" / "model.pkl"

_pipeline: Any | None = None


class PredictRequest(BaseModel):
    top: str = Field(..., description="上装")
    bottom: str = Field(..., description="下装")
    color_top: str = Field(..., description="上装颜色")
    color_bottom: str = Field(..., description="下装颜色")
    season: str = Field(..., description="季节")
    occasion: str = Field(..., description="场合")


class RecommendationItem(BaseModel):
    outfit: str
    score: float


class PredictResponse(BaseModel):
    score: float = Field(..., description="最终评分（0-10）")
    recommendations: list[RecommendationItem] = Field(..., description="推荐组合列表")
    explanation: str = Field(..., description="推荐解释")
    source: str = Field(default="local", description="结果来源: local | hybrid | external")
    fallback_reason: str | None = Field(
        default=None,
        description="回退原因: low_confidence | small_margin | external_failed",
    )
    model_version_local: str = Field(default="local-sklearn-pipeline", description="本地模型版本")
    model_version_external: str | None = Field(default=None, description="外部增强模型版本")
    latency_ms: int | None = Field(default=None, description="本次推理耗时（毫秒）")


def _build_recommendations(score: float, top: str, bottom: str) -> list[RecommendationItem]:
    primary = f"{top.strip()} + {bottom.strip()}"
    return [
        RecommendationItem(outfit=primary, score=score),
        RecommendationItem(outfit="Shirt + Chinos", score=max(0.0, score - 0.3)),
        RecommendationItem(outfit="Hoodie + Joggers", score=max(0.0, score - 0.6)),
    ]


def _build_explanation(score: float) -> str:
    if score > 8:
        return "颜色搭配协调，适合当前季节和场景"
    return "搭配一般，可以尝试更协调的颜色组合"


def _normalized_confidence(score: float) -> float:
    return max(0.0, min(1.0, score / 10.0))


def _top2_margin(recs: list[RecommendationItem]) -> float:
    if len(recs) < 2:
        return 1.0
    return abs(float(recs[0].score) - float(recs[1].score)) / 10.0


def ensure_pipeline() -> Any:
    """加载并缓存 sklearn pipeline；缺失文件时抛错。"""
    global _pipeline
    if _pipeline is None:
        if not MODEL_PATH.is_file():
            raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
        _pipeline = joblib.load(MODEL_PATH)
        _logger.info("已加载穿搭风格模型: %s", MODEL_PATH)
    return _pipeline


def predict_impl(body: PredictRequest) -> PredictResponse:
    """模型推理并组装推荐与解释。"""
    started_at = time.perf_counter()
    pipeline = ensure_pipeline()
    payload = body.model_dump()
    _logger.info("predict input: %s", json.dumps(payload, ensure_ascii=False))
    X = pd.DataFrame([payload])
    raw = pipeline.predict(X)[0]
    score = float(raw)
    recs = _build_recommendations(score, body.top, body.bottom)
    expl = _build_explanation(score)

    response = PredictResponse(score=score, recommendations=recs, explanation=expl)

    confidence = _normalized_confidence(score)
    margin = _top2_margin(recs)
    trigger_reason: str | None = None
    if confidence < settings.LOW_CONF_THRESHOLD:
        trigger_reason = "low_confidence"
    elif margin < settings.MARGIN_THRESHOLD:
        trigger_reason = "small_margin"

    should_enhance = (
        settings.HYBRID_INFERENCE_ENABLED
        and settings.EXTERNAL_ENHANCE_ENABLED
        and confidence < settings.HIGH_CONF_THRESHOLD
        and trigger_reason is not None
    )

    if should_enhance:
        try:
            external_payload = call_external_enhance(
                payload=payload, timeout_ms=settings.EXTERNAL_INFER_TIMEOUT_MS
            )
            external_score = float(external_payload.get("score", score))
            external_expl = str(external_payload.get("explanation", "")).strip()
            fused_score = score * settings.LOCAL_WEIGHT + external_score * settings.EXTERNAL_WEIGHT
            fused_recs = _build_recommendations(fused_score, body.top, body.bottom)
            response = PredictResponse(
                score=fused_score,
                recommendations=fused_recs,
                explanation=(external_expl or expl),
                source="hybrid",
                fallback_reason=trigger_reason,
                model_version_external=str(
                    external_payload.get("model_version", "external-unknown")
                ),
            )
        except Exception as exc:
            _logger.warning("external enhance failed, fallback to local: %s", exc)
            response.fallback_reason = "external_failed"

    response.latency_ms = int((time.perf_counter() - started_at) * 1000)
    _logger.info("predict output score=%s", score)
    return response


def reset_pipeline_for_tests() -> None:
    """测试用：清空缓存。"""
    global _pipeline
    _pipeline = None
