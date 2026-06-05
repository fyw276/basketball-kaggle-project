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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("upper", "上衣"),
        ("top", "上衣"),
        ("lower", "裤子"),
        ("bottom", "裤子"),
        ("pants", "裤子"),
        ("dress", "裙子"),
        ("skirt", "裙子"),
        ("连衣裙", "裙子"),
    ],
)
def test_normalize_auto_category_maps_classifier_fallbacks(raw, expected):
    assert mod._normalize_auto_category(raw) == expected


@pytest.mark.parametrize("raw", ["裤子", "裙子", "lower", "dress", "连衣裙"])
def test_low_confidence_fallback_keeps_known_categories(raw):
    assert mod._should_use_low_confidence_fallback(raw, manual_category_selected=False) is False


def test_low_confidence_fallback_skips_manual_category_override():
    assert mod._should_use_low_confidence_fallback("", manual_category_selected=True) is False


@pytest.mark.parametrize("raw", ["", "unknown", "not-a-category"])
def test_low_confidence_fallback_only_for_unknown_auto_categories(raw):
    assert mod._should_use_low_confidence_fallback(raw, manual_category_selected=False) is True


@pytest.mark.parametrize(("clip_category", "expected"), [("鞋", "鞋"), ("包", "包")])
def test_clip_upload_category_override_rescues_shoes_and_bags(monkeypatch, clip_category, expected):
    class _ClipCategoryClassifier:
        def classify_category(self, _image_bytes):
            return clip_category, 0.13

    monkeypatch.setattr(
        "app.ml.clip_category_classifier.get_clip_category_classifier",
        lambda: _ClipCategoryClassifier(),
    )

    assert mod._clip_upload_category_override(b"img", "上衣", 0.08, False) == (
        expected,
        0.13,
    )


def test_clip_upload_category_override_respects_manual_category(monkeypatch):
    class _ClipCategoryClassifier:
        def classify_category(self, _image_bytes):
            return "鞋", 0.99

    monkeypatch.setattr(
        "app.ml.clip_category_classifier.get_clip_category_classifier",
        lambda: _ClipCategoryClassifier(),
    )

    assert mod._clip_upload_category_override(b"img", "上衣", 0.08, True) is None


def test_silhouette_override_turns_upper_into_pants(monkeypatch):
    monkeypatch.setattr(mod, "_looks_like_pants_image", lambda _b: True)
    assert mod._apply_silhouette_category_override(b"img", "上衣", False) == "裤子"


def test_silhouette_override_respects_manual_category(monkeypatch):
    monkeypatch.setattr(mod, "_looks_like_pants_image", lambda _b: True)
    assert mod._apply_silhouette_category_override(b"img", "上衣", True) == "上衣"


def test_silhouette_override_leaves_non_pants_as_is(monkeypatch):
    monkeypatch.setattr(mod, "_looks_like_pants_image", lambda _b: False)
    assert mod._apply_silhouette_category_override(b"img", "上衣", False) == "上衣"


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


def test_recognize_with_cache_miss_fallback_image_recognizer(monkeypatch):
    cache = _DummyCache(cached=None)
    legacy_payload = {
        "category": "裤子",
        "category_confidence": 0.83,
        "style_tags": ["日常"],
        "feature_vector": [0.1] * 1280,
    }

    class _ImageRecognizer:
        def recognize(self, _b):
            return type("R", (), legacy_payload)()

    monkeypatch.setattr(mod, "get_cache", lambda: cache)
    monkeypatch.setattr(mod, "try_finetuned_infer", lambda _b, feature=None: None)
    monkeypatch.delenv("WARDROBE_USE_CLIP_FALLBACK", raising=False)
    monkeypatch.setattr("app.ml.image_recognizer.ImageRecognizer", _ImageRecognizer)

    result, cache_hit = mod._recognize_with_cache(b"img")
    assert cache_hit is False
    assert result["category"] == "裤子"
    assert len(cache.set_calls) == 1


def test_recognize_with_cache_miss_optional_clip_fallback(monkeypatch):
    cache = _DummyCache(cached=None)
    clip_payload = {
        "category": "裙子",
        "category_confidence": 0.81,
        "style_tags": ["优雅"],
        "feature_vector": [0.1] * 1280,
    }

    class _ClipRecognizer:
        def recognize(self, _b):
            return clip_payload

    monkeypatch.setenv("WARDROBE_USE_CLIP_FALLBACK", "1")
    monkeypatch.delenv("DISABLE_CLIP", raising=False)
    monkeypatch.setattr(mod, "get_cache", lambda: cache)
    monkeypatch.setattr(mod, "try_finetuned_infer", lambda _b, feature=None: None)
    monkeypatch.setattr("app.ml.clip_recognizer.get_clip_recognizer", lambda: _ClipRecognizer())

    result, cache_hit = mod._recognize_with_cache(b"img")
    assert cache_hit is False
    assert result["category"] == "裙子"
    assert len(cache.set_calls) == 1
