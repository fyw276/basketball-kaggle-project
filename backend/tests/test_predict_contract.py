"""
Contract tests for POST /predict (outfit style scoring).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.outfit_style_predict import MODEL_PATH, reset_pipeline_for_tests
from tests.api_json import unwrap_json


def _sample_payload() -> dict[str, str]:
    return {
        "top": "T-shirt",
        "bottom": "Jeans",
        "color_top": "white",
        "color_bottom": "navy",
        "season": "summer",
        "occasion": "casual",
    }


def test_predict_contract_returns_required_fields(client: TestClient):
    """
    /predict must always return:
    - score: number
    - recommendations: list[{outfit, score}]
    - explanation: string

    If model file is missing in this environment, skip (should be provided in repo for demos).
    """
    if not MODEL_PATH.is_file():
        pytest.skip(f"predict model not found: {MODEL_PATH}")

    # Ensure we don't carry state between tests/runs.
    reset_pipeline_for_tests()

    res = client.post("/predict", json=_sample_payload())
    assert res.status_code == 200, res.text

    data = unwrap_json(res)
    assert isinstance(data, dict)

    assert "score" in data
    assert isinstance(data["score"], (int, float))

    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) >= 1

    first = data["recommendations"][0]
    assert isinstance(first, dict)
    assert isinstance(first.get("outfit"), str)
    assert isinstance(first.get("score"), (int, float))

    assert "explanation" in data
    assert isinstance(data["explanation"], str)
    assert data["explanation"].strip() != ""


def test_predict_recommendations_are_top3_like(client: TestClient):
    """
    The API should return a Top3-like list for the default local builder.
    """
    if not MODEL_PATH.is_file():
        pytest.skip(f"predict model not found: {MODEL_PATH}")

    reset_pipeline_for_tests()

    payload = _sample_payload()
    payload["top"] = "Shirt"
    payload["bottom"] = "Chinos"

    res = client.post("/predict", json=payload)
    assert res.status_code == 200, res.text
    data = unwrap_json(res)

    recs = data.get("recommendations") or []
    assert isinstance(recs, list)
    assert len(recs) == 3

    assert recs[0]["outfit"] == "Shirt + Chinos"
