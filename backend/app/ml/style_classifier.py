"""
Style classification for garment images using MobileNetV2
Multi-label classification with sigmoid activation
"""

from pathlib import Path
from typing import Any, Dict, List, Union

import numpy as np
from PIL import Image

try:
    import tensorflow as tf
except Exception:  # pragma: no cover - optional dependency
    tf = None

# Broken/namespace tensorflow import guard
if tf is not None and not hasattr(tf, "keras"):  # pragma: no cover
    tf = None

from app.core.logging import setup_logging
from app.ml.image_preprocessor import ImagePreprocessor
from app.ml.model_loader import ModelLoader

logger = setup_logging()


class _FallbackStyleModel:
    def predict(self, preprocessed, verbose=0):
        import numpy as np

        batch = getattr(preprocessed, "shape", [1])[0] or 1
        preds = np.zeros((batch, 1000), dtype=float)
        preds[:, 0] = 1.0
        return preds


# Style tags as defined in design document (12 styles)
STYLE_TAGS = [
    "通勤",  # Commute/Office wear
    "休闲",  # Casual
    "正式",  # Formal
    "运动",  # Sports/Athletic
    "街头",  # Street style
    "学院",  # School/Preppy
    "甜美",  # Sweet/Cute
    "简约",  # Minimalist
    "复古",  # Vintage/Retro
    "朋克",  # Punk
    "民族",  # Ethnic
    "优雅",  # Elegant
]


class StyleClassifier:
    """
    Garment style classifier using MobileNetV2 backbone with multi-label classification

    Since we're using pretrained MobileNetV2 on ImageNet, we'll map
    ImageNet classes to style tags as a simplified approach.
    For production, this should be replaced with a fine-tuned model.
    """

    def __init__(
        self,
        model_loader: ModelLoader = None,
        preprocessor: ImagePreprocessor = None,
        threshold: float = 0.3,
    ):
        """
        Initialize style classifier

        Args:
            model_loader: ModelLoader instance (creates new if None)
            preprocessor: ImagePreprocessor instance (creates new if None)
            threshold: Confidence threshold for multi-label classification
        """
        self.model_loader = model_loader or ModelLoader()
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.threshold = threshold

        # Load MobileNetV2 for style classification
        # In production, this should be a fine-tuned multi-label model
        self.model = self._load_style_model()

        logger.info(f"StyleClassifier initialized with threshold={threshold}")

    def _load_style_model(self) -> Any:
        """
        Load MobileNetV2 with style classification head

        Returns:
            Style classification model
        """
        logger.info("Loading MobileNetV2 style classification model")

        if tf is None:
            logger.warning("TensorFlow unavailable; using fallback style model")
            return _FallbackStyleModel()

        # Load MobileNetV2 with ImageNet classification head
        # We'll use this to map ImageNet classes to style tags
        model = tf.keras.applications.MobileNetV2(
            input_shape=(224, 224, 3),
            include_top=True,
            weights="imagenet",
        )

        model.trainable = False

        logger.info("MobileNetV2 style model loaded successfully")

        return model

    def classify_style(
        self, image_source: Union[str, Path, bytes, Image.Image], threshold: float = None
    ) -> List[str]:
        """
        Classify garment style tags from image (multi-label)

        Args:
            image_source: Image file path, bytes, or PIL Image
            threshold: Confidence threshold (uses default if None)

        Returns:
            List[str]: List of style tags that exceed threshold
        """
        if threshold is None:
            threshold = self.threshold

        # Preprocess image
        preprocessed = self.preprocessor.preprocess_single(image_source)

        # Get predictions
        predictions = self.model.predict(preprocessed, verbose=0)

        # Map ImageNet predictions to style tags with confidence scores
        style_scores = self._map_to_style_tags(predictions[0])

        # Apply threshold filtering
        style_tags = self._apply_threshold(style_scores, threshold)

        logger.info(f"Classified styles: {style_tags}")

        return style_tags

    def classify_style_with_scores(
        self, image_source: Union[str, Path, bytes, Image.Image]
    ) -> Dict[str, float]:
        """
        Classify garment style tags with confidence scores

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            Dict[str, float]: Dictionary mapping style tags to confidence scores
        """
        # Preprocess image
        preprocessed = self.preprocessor.preprocess_single(image_source)

        # Get predictions
        predictions = self.model.predict(preprocessed, verbose=0)

        # Map ImageNet predictions to style tags with confidence scores
        style_scores = self._map_to_style_tags(predictions[0])

        logger.debug(f"Style scores: {style_scores}")

        return style_scores

    def _map_to_style_tags(self, predictions: np.ndarray) -> Dict[str, float]:
        """
        Map ImageNet predictions to style tags using heuristic rules

        This is a simplified mapping. In production, use a fine-tuned model.

        Args:
            predictions: ImageNet class probabilities (1000 classes)

        Returns:
            Dict[str, float]: Style tag to confidence score mapping
        """
        # ImageNet class ranges for style tags (approximate heuristic mapping)
        # These mappings are based on ImageNet class indices
        imagenet_style_mappings = {
            "通勤": list(range(610, 620))
            + list(range(770, 780))
            + [458, 459],  # suit, blazer, business attire
            "休闲": list(range(610, 640)) + list(range(640, 650)),  # casual wear, jeans
            "正式": list(range(433, 445))
            + list(range(610, 620))
            + [458, 459],  # suit, tuxedo, formal wear
            "运动": list(range(638, 640))
            + list(range(788, 795))
            + [566],  # jersey, sneakers, sports wear
            "街头": list(range(610, 640))
            + list(range(788, 800))
            + [566],  # streetwear, sneakers, hoodies
            "学院": list(range(610, 630)) + [458],  # preppy style, blazer
            "甜美": list(range(650, 660)) + list(range(610, 620)),  # dresses, skirts
            "简约": list(range(610, 630)) + list(range(770, 780)),  # minimalist clothing
            "复古": list(range(650, 670)) + list(range(433, 445)),  # vintage styles
            "朋克": list(range(610, 640)) + [414],  # punk style, leather
            "民族": list(range(650, 660)),  # ethnic patterns
            "优雅": list(range(650, 670))
            + list(range(433, 445))
            + [458],  # elegant dresses, formal wear
        }

        # Calculate confidence for each style tag
        style_scores = {}
        for style_tag, indices in imagenet_style_mappings.items():
            # Sum probabilities of relevant ImageNet classes
            score = sum(predictions[idx] for idx in indices if idx < len(predictions))
            # Apply sigmoid-like normalization to get multi-label probabilities
            # This simulates sigmoid output for multi-label classification
            style_scores[style_tag] = float(score)

        # Normalize scores to simulate sigmoid probabilities
        # Apply softmax-like normalization but keep multi-label nature
        max_score = max(style_scores.values()) if style_scores else 1.0
        if max_score > 0:
            style_scores = {k: min(v / max_score, 1.0) for k, v in style_scores.items()}

        return style_scores

    def _apply_threshold(self, style_scores: Dict[str, float], threshold: float) -> List[str]:
        """
        Apply threshold filtering to style scores

        Args:
            style_scores: Style tag to confidence score mapping
            threshold: Minimum confidence threshold

        Returns:
            List[str]: Style tags that exceed threshold
        """
        # Filter styles that exceed threshold
        filtered_styles = [tag for tag, score in style_scores.items() if score >= threshold]

        # If no styles exceed threshold, return the top style
        if not filtered_styles:
            max_style = max(style_scores, key=style_scores.get)
            filtered_styles = [max_style]
            logger.debug(
                f"No styles exceeded threshold {threshold}, "
                f"using top style: {max_style} ({style_scores[max_style]:.3f})"
            )

        return filtered_styles

    def get_style_tags(self) -> List[str]:
        """
        Get all available style tags

        Returns:
            List[str]: List of all style tags
        """
        return STYLE_TAGS.copy()

    def get_threshold(self) -> float:
        """
        Get current threshold value

        Returns:
            float: Current threshold
        """
        return self.threshold

    def set_threshold(self, threshold: float) -> None:
        """
        Set threshold value

        Args:
            threshold: New threshold value (0.0 to 1.0)
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Threshold must be between 0.0 and 1.0, got {threshold}")

        self.threshold = threshold
        logger.info(f"Threshold updated to {threshold}")
