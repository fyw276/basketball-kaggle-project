"""Tests for cache-first recognition helpers in wardrobe_simple API."""

from types import SimpleNamespace

import pytest

from app.api import wardrobe_simple as mod


class _DummyCache:
    def __init__(self, cached=None):
        self._cached = cached
        self.set_calls = []

    def get(self, _image_bytes):
        return self._cached

    def set(self, image_bytes, result):
        self.set_calls.append((image_bytes, result))


def test_as_recognition_dict_from_dict():
    payload = {
        "category": "上衣",
        "category_confidence": 0.88,
        "style_tags": ["简约"],
        "feature_vector": [0.1] * 1280,
    }
    out = mod._as_recognition_dict(payload)
    assert out is payload


def test_as_recognition_dict_from_object():
    obj = SimpleNamespace(
        category="裤子",
        category_confidence=0.77,
        style_tags=["休闲"],
        feature_vector=[0.2] * 1280,
        fit_type="regular",
    )
    out = mod._as_recognition_dict(obj)
    assert out["category"] == "裤子"
    assert out["category_confidence"] == 0.77
    assert out["fit_type"] == "regular"


def test_recognize_with_cache_hit(monkeypatch):
    cached = {
        "category": "上衣",
        "category_confidence": 0.9,
        "style_tags": ["通勤"],
        "feature_vector": [0.1] * 1280,
    }
    cache = _DummyCache(cached=cached)

    monkeypatch.setattr(mod, "get_cache", lambda: cache)

    result, cache_hit = mod._recognize_with_cache(b"img")
    assert cache_hit is True
    assert result["category"] == "上衣"
    assert len(cache.set_calls) == 0


def test_recognize_with_cache_miss_uses_finetuned(monkeypatch):
    cache = _DummyCache(cached=None)
    finetuned = {
        "category": "连衣裙",
        "category_confidence": 0.86,
        "style_tags": ["优雅"],
        "feature_vector": [0.1] * 1280,
    }

    monkeypatch.setattr(mod, "get_cache", lambda: cache)
    monkeypatch.setattr(mod, "try_finetuned_infer", lambda _b, feature=None: finetuned)

    result, cache_hit = mod._recognize_with_cache(b"img")
    assert cache_hit is False
    assert result["category"] == "连衣裙"
    assert len(cache.set_calls) == 1


def test_recognize_with_cache_miss_fallback_clip(monkeypatch):
    cache = _DummyCache(cached=None)
    clip_payload = {
        "category": "裤子",
        "category_confidence": 0.83,
        "style_tags": ["日常"],
        "feature_vector": [0.1] * 1280,
    }

    class _Recognizer:
        def recognize(self, _b):
            return clip_payload

    monkeypatch.setattr(mod, "get_cache", lambda: cache)
    monkeypatch.setattr(mod, "try_finetuned_infer", lambda _b, feature=None: None)
    monkeypatch.setattr(mod, "get_clip_recognizer", lambda: _Recognizer())

    result, cache_hit = mod._recognize_with_cache(b"img")
    assert cache_hit is False
    assert result["category"] == "裤子"
    assert len(cache.set_calls) == 1
