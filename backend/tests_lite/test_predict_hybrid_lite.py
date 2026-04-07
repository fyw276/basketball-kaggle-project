"""Lightweight tests for hybrid inference behavior in predict service."""

import os

os.environ.setdefault("DEBUG", "false")

from app.services import outfit_style_predict as predict_mod


class _DummyPipeline:
    def __init__(self, score: float):
        self._score = score

    def predict(self, _x):
        return [self._score]


def _request():
    return predict_mod.PredictRequest(
        top="Shirt",
        bottom="Jeans",
        color_top="Blue",
        color_bottom="Black",
        season="Spring",
        occasion="Work",
    )


def test_predict_local_mode_has_metadata(monkeypatch):
    monkeypatch.setattr(predict_mod, "ensure_pipeline", lambda: _DummyPipeline(8.0))
    monkeypatch.setattr(predict_mod.settings, "HYBRID_INFERENCE_ENABLED", False)
    monkeypatch.setattr(predict_mod.settings, "EXTERNAL_ENHANCE_ENABLED", False)

    result = predict_mod.predict_impl(_request())

    assert result.source == "local"
    assert result.fallback_reason is None
    assert result.model_version_local == "local-sklearn-pipeline"
    assert result.model_version_external is None
    assert result.latency_ms is not None


def test_predict_hybrid_success(monkeypatch):
    monkeypatch.setattr(predict_mod, "ensure_pipeline", lambda: _DummyPipeline(5.0))
    monkeypatch.setattr(predict_mod.settings, "HYBRID_INFERENCE_ENABLED", True)
    monkeypatch.setattr(predict_mod.settings, "EXTERNAL_ENHANCE_ENABLED", True)
    monkeypatch.setattr(predict_mod.settings, "LOW_CONF_THRESHOLD", 0.9)
    monkeypatch.setattr(predict_mod.settings, "HIGH_CONF_THRESHOLD", 0.95)
    monkeypatch.setattr(predict_mod.settings, "LOCAL_WEIGHT", 0.5)
    monkeypatch.setattr(predict_mod.settings, "EXTERNAL_WEIGHT", 0.5)
    monkeypatch.setattr(
        predict_mod,
        "call_external_enhance",
        lambda payload, timeout_ms: {
            "score": 9.0,
            "explanation": "外部增强判定更匹配",
            "model_version": "ext-v1",
        },
    )

    result = predict_mod.predict_impl(_request())

    assert result.source == "hybrid"
    assert result.fallback_reason == "low_confidence"
    assert result.score > 6.0
    assert result.model_version_external == "ext-v1"


def test_predict_hybrid_external_failed_fallback(monkeypatch):
    monkeypatch.setattr(predict_mod, "ensure_pipeline", lambda: _DummyPipeline(5.0))
    monkeypatch.setattr(predict_mod.settings, "HYBRID_INFERENCE_ENABLED", True)
    monkeypatch.setattr(predict_mod.settings, "EXTERNAL_ENHANCE_ENABLED", True)
    monkeypatch.setattr(predict_mod.settings, "LOW_CONF_THRESHOLD", 0.9)
    monkeypatch.setattr(predict_mod.settings, "HIGH_CONF_THRESHOLD", 0.95)

    def _raise_external(payload, timeout_ms):
        raise RuntimeError("external down")

    monkeypatch.setattr(predict_mod, "call_external_enhance", _raise_external)

    result = predict_mod.predict_impl(_request())

    assert result.source == "local"
    assert result.fallback_reason == "external_failed"
