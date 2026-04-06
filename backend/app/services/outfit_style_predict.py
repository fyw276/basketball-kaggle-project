"""
穿搭风格分（sklearn pipeline）+ 推荐列表与解释 — 供 backend.main 与 app.main 共用。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from pydantic import BaseModel, Field

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
    score: float
    recommendations: list[RecommendationItem]
    explanation: str


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
    pipeline = ensure_pipeline()
    payload = body.model_dump()
    _logger.info("predict input: %s", json.dumps(payload, ensure_ascii=False))
    X = pd.DataFrame([payload])
    raw = pipeline.predict(X)[0]
    score = float(raw)
    recs = _build_recommendations(score, body.top, body.bottom)
    expl = _build_explanation(score)
    _logger.info("predict output score=%s", score)
    return PredictResponse(score=score, recommendations=recs, explanation=expl)


def reset_pipeline_for_tests() -> None:
    """测试用：清空缓存。"""
    global _pipeline
    _pipeline = None
