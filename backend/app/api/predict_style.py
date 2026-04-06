"""
POST /predict — 与 backend.main 相同的 AI 穿搭风格分接口（同一模型与响应结构）。
"""

from fastapi import APIRouter, HTTPException

from app.services.outfit_style_predict import (
    PredictRequest,
    PredictResponse,
    ensure_pipeline,
    predict_impl,
)

router = APIRouter(tags=["outfit-style-predict"])


@router.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest) -> PredictResponse:
    try:
        ensure_pipeline()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return predict_impl(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
