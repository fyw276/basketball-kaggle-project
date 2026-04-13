"""
Category classification for garment images using MobileNetV2
"""

from pathlib import Path
from typing import Any, Tuple, Union

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


class _FallbackCategoryModel:
    def predict(self, preprocessed, verbose=0):
        import numpy as np

        batch = getattr(preprocessed, "shape", [1])[0] or 1
        preds = np.zeros((batch, 1000), dtype=float)
        preds[:, 0] = 1.0
        return preds


# 6 garment categories as specified in requirements
GARMENT_CATEGORIES = {
    0: "上衣",  # Tops: T-shirts, shirts, sweaters, hoodies
    1: "裤子",  # Pants: jeans, casual pants, trousers
    2: "裙子",  # Skirts: dresses, skirts
    3: "外套",  # Outerwear: jackets, coats, windbreakers
    4: "鞋",  # Shoes: sneakers, leather shoes, boots
    5: "包",  # Bags: handbags, backpacks, crossbody bags
}


class CategoryClassifier:
    """
    Garment category classifier using MobileNetV2 backbone

    Since we're using pretrained MobileNetV2 on ImageNet, we'll map
    ImageNet classes to our 6 garment categories as a simplified approach.
    For production, this should be replaced with a fine-tuned model.
    """

    def __init__(
        self,
        model_loader: ModelLoader = None,
        preprocessor: ImagePreprocessor = None,
        confidence_threshold: float = 0.5,
    ):
        """
        Initialize category classifier

        Args:
            model_loader: ModelLoader instance (creates new if None)
            preprocessor: ImagePreprocessor instance (creates new if None)
            confidence_threshold: Minimum confidence for category prediction
        """
        self.model_loader = model_loader or ModelLoader()
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.confidence_threshold = confidence_threshold

        # Load MobileNetV2 with ImageNet classification head for now
        # In production, this should be a fine-tuned model
        self.model = self._load_classification_model()

        logger.info(f"CategoryClassifier initialized with threshold={confidence_threshold}")

    def _load_classification_model(self) -> Any:
        """
        Load MobileNetV2 with classification head

        Returns:
            Classification model
        """
        logger.info("Loading MobileNetV2 classification model")

        if tf is None:
            logger.warning("TensorFlow unavailable; using fallback category model")
            return _FallbackCategoryModel()

        # Load MobileNetV2 with ImageNet classification head
        model = tf.keras.applications.MobileNetV2(
            input_shape=(224, 224, 3),
            include_top=True,
            weights="imagenet",
        )

        model.trainable = False

        logger.info("MobileNetV2 classification model loaded successfully")

        return model

    def classify_category(
        self, image_source: Union[str, Path, bytes, Image.Image]
    ) -> Tuple[str, float]:
        """
        Classify garment category from image

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            Tuple[str, float]: (category_name, confidence)
                - category_name: One of 6 categories (上衣/裤子/裙子/外套/鞋/包)
                - confidence: Confidence score [0, 1]
        """
        # Preprocess image
        preprocessed = self.preprocessor.preprocess_single(image_source)

        # Get predictions
        predictions = self.model.predict(preprocessed, verbose=0)

        # Map ImageNet predictions to garment categories
        category, confidence = self._map_to_garment_category(predictions[0])

        logger.info(f"Classified as '{category}' with confidence {confidence:.3f}")

        return category, confidence

    def _map_to_garment_category(self, predictions: np.ndarray) -> Tuple[str, float]:
        """
        Map ImageNet predictions to garment categories

        This is a simplified heuristic mapping. In production, use a fine-tuned model.

        Args:
            predictions: ImageNet class probabilities (1000 classes)

        Returns:
            Tuple[str, float]: (category_name, confidence)
        """
        # ImageNet class ranges for garment categories (approximate mapping)
        # These are based on ImageNet class indices
        imagenet_mappings = {
            "上衣": list(range(610, 640)) + list(range(770, 780)),  # jersey, sweatshirt, etc.
            "裤子": list(range(640, 650)) + [414],  # jean, trouser
            "裙子": list(range(650, 660)),  # miniskirt, gown
            "外套": list(range(433, 445)) + list(range(660, 670)),  # jacket, coat
            "鞋": list(range(788, 800)) + list(range(804, 820)),  # shoe, boot
            "包": list(range(414, 433)) + [800],  # backpack, handbag, purse
        }

        # Calculate confidence for each garment category
        category_scores = {}
        for category, indices in imagenet_mappings.items():
            # Sum probabilities of relevant ImageNet classes
            score = sum(predictions[idx] for idx in indices if idx < len(predictions))
            category_scores[category] = score

        # Get category with highest score
        best_category = max(category_scores, key=category_scores.get)
        confidence = category_scores[best_category]

        # If confidence is too low, keep the best-scoring category instead of
        # forcing every uncertain item into "上衣". The previous fallback
        # introduced a strong top-wear bias and hurt downstream outfit quality.
        if confidence < self.confidence_threshold:
            logger.warning(
                f"Low confidence {confidence:.3f} < {self.confidence_threshold}, "
                f"keeping best category '{best_category}'"
            )
            return best_category, confidence

        return best_category, float(confidence)

    def get_confidence_level(self, confidence: float) -> str:
        """
        Get confidence level description

        Args:
            confidence: Confidence score [0, 1]

        Returns:
            str: Confidence level (高置信度/中等置信度/低置信度)
        """
        if confidence >= 0.8:
            return "高置信度"
        elif confidence >= 0.5:
            return "中等置信度"
        else:
            return "低置信度"

    def get_categories(self) -> dict:
        """
        Get all available garment categories

        Returns:
            dict: Category ID to name mapping
        """
        return GARMENT_CATEGORIES.copy()
