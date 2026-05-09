"""
Tests for heuristic_category fallback and confidence threshold behavior.

Key changes:
- MIN_CONFIDENCE lowered from 0.3 to 0.12
- When confidence < 0.12, heuristic_category() is called instead of returning "unknown"
- heuristic_category uses aspect ratio: wide→upper, tall→dress, neither→lower
"""

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from app.ml.category_classifier import CategoryClassifier


def _mock_low_confidence_predictions(confidence_value: float) -> np.ndarray:
    """Build mock ImageNet predictions with total score = confidence_value for best category."""
    preds = np.zeros(1000, dtype=float)
    # Spread the score across a few garment-related indices so the sum matches
    per_class = confidence_value / 3
    preds[610] = per_class
    preds[611] = per_class
    preds[612] = per_class
    return preds


def _make_image(w: int, h: int) -> Image.Image:
    """Create a solid-color test image of the given dimensions."""
    return Image.new("RGB", (w, h), color="blue")


class TestHeuristicCategory:
    """Test the heuristic_category fallback method directly."""

    def test_wide_image_returns_upper(self):
        """宽 > 高 * 0.8 → upper"""
        classifier = CategoryClassifier()
        # Wide: 500x400 → aspect=1.25 > 0.8
        img = _make_image(500, 400)
        assert classifier.heuristic_category(img) == "upper"

    def test_wide_image_edge_case_returns_upper(self):
        """Aspect ratio > 0.9 returns upper."""
        classifier = CategoryClassifier()
        # 401x400 → aspect≈1.0 > 0.9 → upper
        img = _make_image(401, 400)
        assert classifier.heuristic_category(img) == "upper"

    def test_tall_image_returns_dress(self):
        """高 > 宽 * 1.4 → dress"""
        classifier = CategoryClassifier()
        # Tall: 400x700 → h=700, w*1.4=560 → 700 > 560 → dress
        img = _make_image(400, 700)
        assert classifier.heuristic_category(img) == "dress"

    def test_tall_image_edge_case_returns_dress(self):
        """Tall at exact boundary → dress"""
        classifier = CategoryClassifier()
        # 500x700 → h=700, w*1.4=700 → 700 > 700 is False → lower
        # Use 500x701 → 701 > 700 → dress
        img = _make_image(500, 701)
        assert classifier.heuristic_category(img) == "dress"

    def test_squareish_image_returns_lower(self):
        """Neither wide nor tall → lower (default)"""
        classifier = CategoryClassifier()
        # 400x450 → aspect=0.889; not > 0.8; 450 > 400*1.4=560? No → lower
        img = _make_image(400, 450)
        assert classifier.heuristic_category(img) == "lower"

    def test_upper_image_path(self):
        """wide (aspect > 0.8) images return upper."""
        classifier = CategoryClassifier()
        for w, h in [(600, 400), (800, 300), (300, 200)]:
            img = _make_image(w, h)
            result = classifier.heuristic_category(img)
            assert result == "upper", f"Image {w}x{h} should be upper, got {result}"

    def test_dress_image_path(self):
        """Tall (h > w * 1.4) images return dress."""
        classifier = CategoryClassifier()
        for w, h in [(300, 500), (400, 700), (250, 600)]:
            img = _make_image(w, h)
            result = classifier.heuristic_category(img)
            assert result == "dress", f"Image {w}x{h} should be dress, got {result}"

    def test_lower_image_path(self):
        """In-between images return lower."""
        classifier = CategoryClassifier()
        for w, h in [(400, 450), (450, 500), (300, 400)]:
            img = _make_image(w, h)
            result = classifier.heuristic_category(img)
            assert result == "lower", f"Image {w}x{h} should be lower, got {result}"

    def test_heuristic_accepts_path_string(self, tmp_path):
        """heuristic_category accepts a file path."""
        classifier = CategoryClassifier()
        img = _make_image(600, 400)
        path = tmp_path / "test_upper.jpg"
        img.save(str(path))
        assert classifier.heuristic_category(str(path)) == "upper"

    def test_heuristic_accepts_pil_image(self):
        """heuristic_category accepts a PIL Image directly."""
        classifier = CategoryClassifier()
        img = _make_image(400, 700)
        assert classifier.heuristic_category(img) == "dress"

    def test_heuristic_default_on_error(self):
        """On any exception, heuristic returns 'upper' (the default)."""
        classifier = CategoryClassifier()
        result = classifier.heuristic_category("/nonexistent/path/image.jpg")
        assert result == "upper"


class TestLowConfidenceFallback:
    """Test that low-confidence classifications fall back to heuristic, not 'unknown'."""

    def test_confidence_below_012_returns_heuristic_upper(self):
        """
        When model confidence < 0.12, the result must NOT be 'unknown'.
        Instead it should come from heuristic_category.
        """
        classifier = CategoryClassifier()

        mock_preds = _mock_low_confidence_predictions(0.05)

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_preds])

            img = _make_image(600, 400)  # wide → heuristic says "upper"
            category, confidence = classifier.classify_category(img)

            assert (
                category != "unknown"
            ), f"Expected heuristic fallback, not 'unknown' for confidence={confidence:.3f}"
            assert category == "upper", f"Expected 'upper' from heuristic, got {category!r}"
            assert confidence == pytest.approx(0.05, abs=0.001)

    def test_confidence_below_012_returns_heuristic_dress(self):
        """Low confidence on a tall image falls back to dress."""
        classifier = CategoryClassifier()

        mock_preds = _mock_low_confidence_predictions(0.03)

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_preds])

            img = _make_image(300, 600)  # tall → heuristic says "dress"
            category, confidence = classifier.classify_category(img)

            assert category != "unknown"
            assert category == "dress"
            assert confidence == pytest.approx(0.03, abs=0.001)

    def test_confidence_below_012_returns_heuristic_lower(self):
        """Low confidence on a square-ish image falls back to lower."""
        classifier = CategoryClassifier()

        mock_preds = _mock_low_confidence_predictions(0.04)

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_preds])

            img = _make_image(400, 500)  # neither wide nor tall → lower
            category, confidence = classifier.classify_category(img)

            assert category != "unknown"
            assert category == "lower"
            assert confidence == pytest.approx(0.04, abs=0.001)

    def test_confidence_above_012_returns_model_category(self):
        """When confidence >= 0.12, the model's best category is returned."""
        classifier = CategoryClassifier()

        mock_preds = np.zeros(1000, dtype=float)
        for idx in range(610, 630):
            mock_preds[idx] = 0.15  # sum ≈ 3.0 for 上衣

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_preds])

            img = _make_image(224, 224)
            category, confidence = classifier.classify_category(img)

            # Should be the model's category, not a heuristic fallback
            assert category == "上衣", f"Expected model category '上衣', got {category!r}"
            assert confidence >= 0.12

    def test_confidence_at_exactly_012_boundary(self):
        """Confidence exactly at 0.12 should use model category (>=, not >)."""
        classifier = CategoryClassifier()

        mock_preds = _mock_low_confidence_predictions(0.12)

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_preds])

            category, confidence = classifier.classify_category(_make_image(224, 224))

            # 0.12 is NOT < 0.12, so it should go through model path, not heuristic
            assert confidence == pytest.approx(0.12, abs=0.001)
            assert category == "上衣"

    def test_confidence_just_below_012_uses_heuristic(self):
        """Confidence just below 0.12 (e.g., 0.119) should use heuristic."""
        classifier = CategoryClassifier()

        mock_preds = _mock_low_confidence_predictions(0.119)

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_preds])

            img = _make_image(600, 400)
            category, confidence = classifier.classify_category(img)

            assert category != "unknown"
            assert category == "upper"
            assert confidence == pytest.approx(0.119, abs=0.001)
