"""
Model loader for MobileNetV2 pretrained model
"""

from pathlib import Path
from typing import Any, Optional

try:
    import tensorflow as tf
    from tensorflow.keras.applications import MobileNetV2
except Exception:  # pragma: no cover - optional dependency
    tf = None
    MobileNetV2 = None

from app.core.logging import setup_logging

logger = setup_logging()


class _FallbackFeatureModel:
    """Fallback model used when tensorflow is unavailable."""

    input_shape = (224, 224, 3)
    output_shape = (None, 1280)
    trainable = False

    def predict(self, preprocessed, verbose=0):
        import numpy as np

        batch = getattr(preprocessed, "shape", [1])[0] or 1
        return np.zeros((batch, 1280), dtype=float)

    def count_params(self):
        return 0


class ModelLoader:
    """Load and manage MobileNetV2 pretrained model"""

    def __init__(self, model_dir: Optional[str] = None):
        """
        Initialize model loader

        Args:
            model_dir: Directory to store model weights (optional)
        """
        if model_dir is None:
            # Default to models directory in project root
            project_root = Path(__file__).parent.parent.parent.parent
            model_dir = project_root / "models"

        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self._feature_extractor_model: Optional[Any] = None

        logger.info(f"ModelLoader initialized with model_dir: {self.model_dir}")

    def load_feature_extractor(
        self, input_shape: tuple = (224, 224, 3), weights: str = "imagenet"
    ) -> Any:
        """
        Load MobileNetV2 as feature extractor

        Args:
            input_shape: Input image shape (height, width, channels)
            weights: Pretrained weights to use ('imagenet' or None)

        Returns:
            MobileNetV2 model for feature extraction
        """
        if self._feature_extractor_model is not None:
            logger.info("Returning cached feature extractor model")
            return self._feature_extractor_model

        if tf is None or MobileNetV2 is None:
            logger.warning("TensorFlow unavailable; using fallback feature model")
            self._feature_extractor_model = _FallbackFeatureModel()
            return self._feature_extractor_model

        logger.info(
            f"Loading MobileNetV2 feature extractor with weights={weights}, "
            f"input_shape={input_shape}"
        )

        try:
            # Load MobileNetV2 without top classification layer
            # pooling='avg' gives us 1280-dimensional feature vector
            model = MobileNetV2(
                input_shape=input_shape,
                include_top=False,
                weights=weights,
                pooling="avg",
            )

            # Freeze the model weights (no training)
            model.trainable = False

            self._feature_extractor_model = model

            logger.info(
                f"MobileNetV2 feature extractor loaded successfully. "
                f"Output shape: {model.output_shape}"
            )

            return model

        except Exception as e:
            logger.error(f"Failed to load MobileNetV2 model: {e}")
            raise

    def get_model_info(self) -> dict:
        """
        Get information about the loaded model

        Returns:
            dict: Model information
        """
        if self._feature_extractor_model is None:
            return {"status": "not_loaded"}

        return {
            "status": "loaded",
            "model_name": "MobileNetV2",
            "input_shape": self._feature_extractor_model.input_shape,
            "output_shape": self._feature_extractor_model.output_shape,
            "trainable": self._feature_extractor_model.trainable,
            "total_params": self._feature_extractor_model.count_params(),
        }

    def clear_cache(self):
        """Clear cached model from memory"""
        if self._feature_extractor_model is not None:
            logger.info("Clearing cached feature extractor model")
            del self._feature_extractor_model
            self._feature_extractor_model = None
            if tf is not None:
                tf.keras.backend.clear_session()
