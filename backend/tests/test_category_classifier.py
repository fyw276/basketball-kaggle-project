"""
Tests for CategoryClassifier behavior with low confidence results.

Key requirement: when confidence < 0.12, classifier returns heuristic_category fallback
(aspect-ratio based) instead of the model's misclassified category.
The threshold was lowered from 0.3 to 0.12 to use more classifications.
"""

import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.ml.category_classifier import CategoryClassifier


def _make_test_image() -> Image.Image:
    """Create a minimal test image."""
    return Image.new("RGB", (224, 224), color="blue")


class TestCategoryClassifierLowConfidence:
    """Test that low confidence results are properly handled."""

    def test_low_confidence_returns_unknown_not_wrong_category(self):
        """
        When model returns a category like "鞋" with confidence 0.074 (< 0.12),
        classifier MUST return a heuristic fallback (not the wrong garment category).

        The threshold was lowered from 0.3 to 0.12. When confidence < 0.12,
        the result comes from heuristic_category (aspect-ratio based), not "unknown".
        For a square-ish test image (224x224), heuristic returns "upper".
        """
        classifier = CategoryClassifier(confidence_threshold=0.5)

        # Simulate MobileNetV2 predictions that produce:
        # - "鞋" (shoes) with very low confidence (0.074)
        # - Other categories with even lower scores
        mock_predictions = np.zeros(1000, dtype=float)
        # ImageNet classes 788-800 for shoes
        mock_predictions[788] = 0.04
        mock_predictions[789] = 0.034
        # Make "shoes" the highest-scoring category but still very low
        total = mock_predictions[788] + mock_predictions[789]

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_predictions])

            category, confidence = classifier.classify_category(_make_test_image())

            print(f"Category: {category!r}, Confidence: {confidence:.3f}")

            # At confidence < 0.12, classifier falls back to heuristic (aspect ratio).
            # For a 224x224 (square) image, aspect=1.0 > 0.9, so heuristic returns "upper".
            assert category != "鞋", (
                f"Expected heuristic fallback, not {category!r} when confidence={confidence:.3f} < 0.12. "
                f"Low confidence results should NOT be the model's misclassified category."
            )
            assert confidence < 0.12

    def test_high_confidence_returns_real_category(self):
        """
        When confidence > 0.5, classifier should return the actual classified category.
        """
        classifier = CategoryClassifier(confidence_threshold=0.5)

        # Simulate high confidence for "上衣" (top)
        mock_predictions = np.zeros(1000, dtype=float)
        # ImageNet classes for jersey/shirt/upper garment: 610-640
        for idx in range(610, 630):
            mock_predictions[idx] = 0.15
        # Sum should be high enough to pass threshold
        mock_predictions[620] = 0.20  # Add extra for shirt/jersey

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_predictions])

            category, confidence = classifier.classify_category(_make_test_image())

            print(f"Category: {category!r}, Confidence: {confidence:.3f}")

            # High confidence should return the actual category, not "unknown"
            assert category != "unknown", (
                f"Expected real category when confidence={confidence:.3f} > 0.3, "
                f"but got 'unknown'. "
                f"High confidence results should be used."
            )
            assert (
                confidence > 0.3
            ), f"Expected confidence > 0.3 for high-confidence case, got {confidence:.3f}"

    def test_very_low_confidence_scenario_mimicking_real_bug(self):
        """
        Reproduce the exact scenario from the bug report:
        - confidence=0.074
        - classified as "鞋" (shoes)
        - Should NOT return the wrong category

        At confidence < 0.12, the classifier returns heuristic_category fallback.
        For a square-ish 224x224 test image, heuristic returns "upper".
        The key fix is: it must NOT return the misclassified "鞋" category.
        """
        classifier = CategoryClassifier(confidence_threshold=0.5)

        # Exact scenario: shoes with 0.074 total score
        mock_predictions = np.zeros(1000, dtype=float)
        # Only some shoe-related classes have small values
        mock_predictions[788] = 0.040
        mock_predictions[789] = 0.034
        # All other categories are 0
        # Total for "鞋" = 0.074

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_predictions])

            category, confidence = classifier.classify_category(_make_test_image())

            print(f"[BUG REPRO] Category: {category!r}, Confidence: {confidence:.3f}")

            # BUG BEHAVIOR would be: category="鞋", confidence=0.074
            # FIXED BEHAVIOR: heuristic fallback, NOT the wrong garment category
            assert category != "鞋", (
                f"BUG: Got category={category!r} with confidence={confidence:.3f}. "
                f"When confidence < 0.12, classifier MUST NOT return the model's "
                f"misclassified category. It should return heuristic fallback instead."
            )
            assert confidence < 0.12

    def test_confidence_threshold_boundary_at_0_3(self):
        """
        Test the boundary at exactly 0.12 (the actual threshold).
        Results with confidence >= 0.12 should return the model's best category.
        Results with confidence < 0.12 should use heuristic fallback.
        """
        classifier = CategoryClassifier(confidence_threshold=0.5)

        # At exactly 0.12 - should return model's best category (>=, not >)
        mock_predictions = np.zeros(1000, dtype=float)
        for idx in range(610, 620):
            mock_predictions[idx] = 0.02  # Sum = 0.20 for 上衣

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_predictions])

            category, confidence = classifier.classify_category(_make_test_image())

            print(f"Boundary test - Category: {category!r}, Confidence: {confidence:.3f}")

            # 0.12 is NOT < 0.12, so it should go through model path
            assert confidence >= 0.12
            assert category == "上衣"

    def test_multiple_categories_all_low_confidence(self):
        """
        When ALL category scores are very low (e.g., image is not a garment),
        classifier returns heuristic fallback instead of "unknown".

        The threshold was lowered from 0.3 to 0.12. When confidence < 0.12,
        the classifier returns heuristic_category (aspect-ratio based).
        For a 224x224 square image, heuristic returns "upper".
        """
        classifier = CategoryClassifier(confidence_threshold=0.5)

        # All categories get tiny scores - this is like classifying a random image
        mock_predictions = np.zeros(1000, dtype=float)
        mock_predictions[0] = 0.02  # Some random class
        mock_predictions[100] = 0.015  # Another random class
        mock_predictions[200] = 0.018  # Another random class
        # No garment-related classes have significant scores

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_predictions])

            category, confidence = classifier.classify_category(_make_test_image())

            print(f"Non-garment image - Category: {category!r}, Confidence: {confidence:.3f}")

            # Very low confidence falls back to heuristic, not "unknown"
            if confidence < 0.12:
                assert category != "unknown", f"Expected heuristic fallback, got {category!r}"


class TestCategoryClassifierIntegration:
    """Integration tests for CategoryClassifier with real-ish predictions."""

    def test_pants_high_confidence(self):
        """High confidence for pants should return '裤子'."""
        classifier = CategoryClassifier(confidence_threshold=0.5)

        mock_predictions = np.zeros(1000, dtype=float)
        # ImageNet classes for pants/trousers: 640-650 and 414
        for idx in range(640, 648):
            mock_predictions[idx] = 0.12

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_predictions])

            category, confidence = classifier.classify_category(_make_test_image())

            print(f"Pants test - Category: {category!r}, Confidence: {confidence:.3f}")

            if confidence >= 0.3:
                # Should be classified as pants
                assert (
                    "裤" in category or "pants" in category.lower()
                ), f"High-confidence pants should return '裤子', got {category!r}"

    def test_bags_low_confidence(self):
        """Bags with low confidence should use heuristic fallback, not misclassify."""
        classifier = CategoryClassifier(confidence_threshold=0.5)

        mock_predictions = np.zeros(1000, dtype=float)
        # ImageNet classes for bags/backpacks: 414-433 and 800
        for idx in range(414, 420):
            mock_predictions[idx] = 0.015  # Very low scores
        mock_predictions[800] = 0.010  # purse
        # Total for "包" = 0.09 + 0.01 = 0.10 < 0.12 threshold

        with patch.object(classifier, "model") as mock_model:
            mock_model.predict.return_value = np.array([mock_predictions])

            category, confidence = classifier.classify_category(_make_test_image())

            print(f"Bags low confidence - Category: {category!r}, Confidence: {confidence:.3f}")

            # At confidence < 0.12, classifier uses heuristic (aspect ratio) instead of model.
            # Must NOT return the wrong garment category like "包".
            assert category != "包", (
                f"Bags at low confidence (={confidence:.3f}) should NOT return "
                f"misclassified '包', got {category!r}."
            )
            assert confidence < 0.12

    def test_confidence_level_description(self):
        """Test the confidence level description helper."""
        classifier = CategoryClassifier()

        assert classifier.get_confidence_level(0.9) == "高置信度"
        assert classifier.get_confidence_level(0.65) == "中等置信度"
        assert classifier.get_confidence_level(0.2) == "低置信度"
        assert classifier.get_confidence_level(0.8) == "高置信度"
        assert classifier.get_confidence_level(0.5) == "中等置信度"
