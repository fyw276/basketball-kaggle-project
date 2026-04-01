"""Tests for outfit multi-image CLIP merge helpers."""

from app.api.analysis import _merge_clip_like_results


def test_merge_clip_like_results_single_returns_same():
    r = {
        "feature_vector": [1.0, 2.0, 3.0],
        "style_tags": ["a"],
        "category": "上衣",
        "category_confidence": 0.8,
        "occasions": ["日常"],
    }
    out = _merge_clip_like_results([r])
    assert out["feature_vector"] == [1.0, 2.0, 3.0]
    assert out["category"] == "上衣"


def test_merge_clip_like_results_averages_same_length():
    r1 = {
        "feature_vector": [2.0, 0.0],
        "style_tags": ["a"],
        "category": "上衣",
        "category_confidence": 0.5,
        "occasions": ["x"],
    }
    r2 = {
        "feature_vector": [0.0, 2.0],
        "style_tags": ["b"],
        "category": "裤子",
        "category_confidence": 0.5,
        "occasions": ["y"],
    }
    out = _merge_clip_like_results([r1, r2])
    assert out["feature_vector"] == [1.0, 1.0]
    assert out["category"] == "上衣"
    assert set(out["style_tags"]) == {"a", "b"}
    assert set(out["occasions"]) == {"x", "y"}


def test_merge_clip_like_results_pads_mixed_dimensions():
    """768-dim + 1280-dim: pad shorter with zeros then average."""
    r1 = {
        "feature_vector": [2.0] * 768,
        "style_tags": [],
        "category": "上衣",
        "category_confidence": 0.5,
        "occasions": [],
    }
    r2 = {
        "feature_vector": [0.0] * 1280,
        "style_tags": [],
        "category": "裤子",
        "category_confidence": 0.5,
        "occasions": [],
    }
    out = _merge_clip_like_results([r1, r2])
    assert len(out["feature_vector"]) == 1280
    assert out["feature_vector"][0] == 1.0
    assert out["feature_vector"][767] == 1.0
    assert out["feature_vector"][768] == 0.0
