"""Category classification for garment images."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Tuple, Union

import numpy as np
from PIL import Image

try:
    import tensorflow as tf
except Exception:  # pragma: no cover - optional dependency
    tf = None

if tf is not None and (not hasattr(tf, "keras") or not hasattr(tf, "Tensor")):  # pragma: no cover
    tf = None

from app.core.logging import setup_logging
from app.ml.image_preprocessor import ImagePreprocessor
from app.ml.model_loader import ModelLoader
from app.services.garment_taxonomy import (
    CATEGORY_BAG,
    CATEGORY_OUTER,
    CATEGORY_PANTS,
    CATEGORY_SHOES,
    CATEGORY_SKIRT,
    CATEGORY_TOP,
    normalize_category,
)

logger = setup_logging()


class _FallbackCategoryModel:
    def predict(self, preprocessed, verbose=0):
        batch = getattr(preprocessed, "shape", [1])[0] or 1
        preds = np.zeros((batch, 1000), dtype=float)
        preds[:, 0] = 1.0
        return preds


GARMENT_CATEGORIES = {
    0: CATEGORY_TOP,
    1: CATEGORY_PANTS,
    2: CATEGORY_SKIRT,
    3: CATEGORY_OUTER,
    4: CATEGORY_SHOES,
    5: CATEGORY_BAG,
}


class CategoryClassifier:
    """
    Garment category classifier using a lightweight ImageNet mapping.

    The mapping is intentionally conservative. Low confidence predictions are
    normalized and then backed by a simple silhouette heuristic, because the
    downstream outfit engine must never receive internal labels such as
    ``upper`` or mojibake category names.
    """

    def __init__(
        self,
        model_loader: ModelLoader = None,
        preprocessor: ImagePreprocessor = None,
        confidence_threshold: float = 0.5,
    ):
        self.model_loader = model_loader or ModelLoader()
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.confidence_threshold = float(confidence_threshold)
        self.model = self._load_classification_model()
        logger.info("CategoryClassifier initialized with threshold=%s", self.confidence_threshold)

    def _load_classification_model(self) -> Any:
        logger.info("Loading MobileNetV2 classification model")
        if tf is None:
            logger.warning("TensorFlow unavailable; using fallback category model")
            return _FallbackCategoryModel()
        model = tf.keras.applications.MobileNetV2(
            input_shape=(224, 224, 3),
            include_top=True,
            weights="imagenet",
        )
        model.trainable = False
        return model

    def classify_category(
        self, image_source: Union[str, Path, bytes, Image.Image]
    ) -> Tuple[str, float]:
        preprocessed = self.preprocessor.preprocess_single(image_source)
        predictions = self.model.predict(preprocessed, verbose=0)
        category, confidence = self._map_to_garment_category(predictions[0])

        if confidence < 0.12:
            heuristic = self.heuristic_category(image_source)
            logger.warning(
                "Low category confidence %.3f; using heuristic category %s",
                confidence,
                heuristic,
            )
            return heuristic, float(confidence)

        normalized = normalize_category(category)
        logger.info("Classified as %s with confidence %.3f", normalized, confidence)
        return normalized, float(confidence)

    def _map_to_garment_category(self, predictions: np.ndarray) -> Tuple[str, float]:
        imagenet_mappings = {
            CATEGORY_TOP: list(range(610, 640)) + list(range(770, 780)),
            CATEGORY_PANTS: list(range(640, 650)) + [414],
            CATEGORY_SKIRT: list(range(650, 660)),
            CATEGORY_OUTER: list(range(433, 445)) + list(range(660, 670)),
            CATEGORY_SHOES: list(range(788, 800)) + list(range(804, 820)),
            CATEGORY_BAG: list(range(414, 433)) + [800],
        }

        category_scores = {}
        for category, indices in imagenet_mappings.items():
            score = sum(float(predictions[idx]) for idx in indices if idx < len(predictions))
            category_scores[category] = score

        best_category = max(category_scores, key=category_scores.get)
        confidence = float(category_scores[best_category])
        if confidence < self.confidence_threshold:
            logger.warning(
                "Low confidence %.3f < %.3f, keeping best category %s",
                confidence,
                self.confidence_threshold,
                best_category,
            )
        return best_category, confidence

    def heuristic_category(self, image_source: Union[str, Path, bytes, Image.Image]) -> str:
        try:
            img = self._open_image(image_source)
            w, h = img.size
            aspect = w / h if h > 0 else 1.0
            if aspect > 1.05:
                return CATEGORY_TOP
            if aspect < 0.62:
                return CATEGORY_SKIRT
            return CATEGORY_PANTS
        except Exception:
            return CATEGORY_TOP

    def _open_image(self, image_source: Union[str, Path, bytes, Image.Image]) -> Image.Image:
        if isinstance(image_source, Image.Image):
            return image_source
        if isinstance(image_source, bytes):
            img = Image.open(BytesIO(image_source))
        else:
            img = Image.open(image_source)
        img.load()
        return img

    def get_confidence_level(self, confidence: float) -> str:
        if confidence >= 0.8:
            return "高置信度"
        if confidence >= 0.5:
            return "中等置信度"
        return "低置信度"

    def get_categories(self) -> dict:
        return GARMENT_CATEGORIES.copy()
