"""Lightweight tests for fine-tuned inference client fallback behaviors."""

from unittest.mock import Mock

from app.services import finetuned_infer_client as mod


class _OkResp:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _DummyClient:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json, headers):
        return _OkResp(self._payload)


def test_try_finetuned_infer_disabled_returns_none(monkeypatch):
    """Test that try_finetuned_infer returns None when FINETUNED_INFER_ENABLED is False."""
    mock_settings = Mock()
    mock_settings.FINETUNED_INFER_ENABLED = False
    mock_settings.FINETUNED_INFER_API_BASE_URL = ""
    monkeypatch.setattr(mod, "settings", mock_settings)

    assert mod.try_finetuned_infer(b"abc", feature="ut") is None


def test_call_finetuned_infer_normalizes_payload(monkeypatch):
    """Test that call_finetuned_infer properly normalizes API response."""
    mock_settings = Mock()
    mock_settings.FINETUNED_INFER_ENABLED = True
    mock_settings.FINETUNED_INFER_API_BASE_URL = "http://fake"
    mock_settings.FINETUNED_INFER_API_PATH = "/infer/fashion"
    mock_settings.FINETUNED_INFER_API_KEY = ""
    mock_settings.FINETUNED_INFER_TIMEOUT_MS = 1000
    monkeypatch.setattr(mod, "settings", mock_settings)

    payload = {
        "category": "上衣",
        "category_confidence": 0.9,
        "style_tags": ["简约"],
        "occasions": ["休闲日常"],
        "feature_vector": [0.1, 0.2, 0.3],
    }
    monkeypatch.setattr(mod, "settings", mock_settings)

    payload = {
        "category": "上衣",
        "category_confidence": 0.9,
        "style_tags": ["简约"],
        "occasions": ["休闲日常"],
        "feature_vector": [0.1, 0.2, 0.3],
    }
    monkeypatch.setattr(mod.httpx, "Client", lambda timeout: _DummyClient(payload))

    result = mod.call_finetuned_infer(b"img")

    assert result["category"] == "上衣"
    assert result["feature_dim"] == 3
    assert result["style_tags"] == ["简约"]


def test_try_finetuned_infer_fallback_on_error(monkeypatch):
    """Test that try_finetuned_infer falls back to None when call_finetuned_infer raises."""
    mock_settings = Mock()
    mock_settings.FINETUNED_INFER_ENABLED = True
    mock_settings.FINETUNED_INFER_API_BASE_URL = "http://fake"
    monkeypatch.setattr(mod, "settings", mock_settings)

    def _raise(_image):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "call_finetuned_infer", _raise)

    assert mod.try_finetuned_infer(b"img", feature="ut") is None
