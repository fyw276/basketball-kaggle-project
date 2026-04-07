"""Lightweight API contract tests for /predict response metadata."""

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEBUG", "false")

from app.api import predict_style as predict_api
from app.services.outfit_style_predict import PredictResponse, RecommendationItem


def _payload():
    return {
        "top": "Shirt",
        "bottom": "Jeans",
        "color_top": "Blue",
        "color_bottom": "Black",
        "season": "Spring",
        "occasion": "Work",
    }


def test_predict_api_contract_contains_hybrid_fields(monkeypatch):
    monkeypatch.setattr(predict_api, "ensure_pipeline", lambda: True)
    monkeypatch.setattr(
        predict_api,
        "predict_impl",
        lambda body: PredictResponse(
            score=8.2,
            recommendations=[RecommendationItem(outfit="Shirt + Jeans", score=8.2)],
            explanation="颜色协调",
            source="local",
            fallback_reason=None,
            model_version_local="local-sklearn-pipeline",
            model_version_external=None,
            latency_ms=123,
        ),
    )

    app = FastAPI()
    app.include_router(predict_api.router)
    client = TestClient(app)

    response = client.post("/predict", json=_payload())
    assert response.status_code == 200
    data = response.json()

    assert "score" in data
    assert "recommendations" in data
    assert "explanation" in data
    assert data["source"] == "local"
    assert "fallback_reason" in data
    assert data["model_version_local"] == "local-sklearn-pipeline"
    assert "model_version_external" in data
    assert data["latency_ms"] == 123
