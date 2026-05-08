"""
Complete image recognition pipeline integrating all recognition modules
"""

from pathlib import Path
from typing import Any, List, Union

from PIL import Image
from pydantic import BaseModel, Field

from app.core.logging import setup_logging
from app.schemas.garment import ColorSchema

logger = setup_logging()

# Module-level singleton cache: load models once, reuse for all requests
_recognizer_instance: "ImageRecognizer | None" = None


def get_recognizer() -> "ImageRecognizer":
    """Return the cached ImageRecognizer singleton (loads models once)."""
    global _recognizer_instance
    if _recognizer_instance is None:
        logger.info("Creating ImageRecognizer singleton (first load)...")
        _recognizer_instance = ImageRecognizer()
        logger.info("ImageRecognizer singleton ready")
    return _recognizer_instance


class RecognitionResult(BaseModel):
    """Complete recognition result from image analysis"""

    category: str = Field(..., description="Recognized garment category")
    category_confidence: float = Field(..., ge=0, le=1, description="Category confidence score")
    main_color: ColorSchema = Field(..., description="Main dominant color")
    secondary_colors: List[ColorSchema] = Field(
        default_factory=list, description="Secondary colors"
    )
    style_tags: List[str] = Field(default_factory=list, description="Style tags")
    feature_vector: List[float] = Field(
        ..., min_length=1280, max_length=1280, description="1280-dim feature vector"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "category": "上衣",
                "category_confidence": 0.85,
                "main_color": {
                    "name": "蓝",
                    "rgb": (52, 120, 180),
                    "hsv": (210.0, 71.1, 70.6),
                    "hex_code": "#3478b4",
                },
                "secondary_colors": [
                    {
                        "name": "白",
                        "rgb": (240, 240, 240),
                        "hsv": (0.0, 0.0, 94.1),
                        "hex_code": "#f0f0f0",
                    }
                ],
                "style_tags": ["通勤", "简约"],
                "feature_vector": [0.1] * 1280,
            }
        }


class ImageRecognizer:
    """
    Complete image recognition pipeline integrating:
    - Category classification
    - Color extraction
    - Style classification
    - Feature extraction
    """

    def __init__(
        self,
        category_classifier: Any = None,
        color_extractor: Any = None,
        style_classifier: Any = None,
        feature_extractor: Any = None,
    ):
        """
        Initialize image recognizer with all recognition modules

        Args:
            category_classifier: CategoryClassifier instance (creates new if None)
            color_extractor: ColorExtractor instance (creates new if None)
            style_classifier: StyleClassifier instance (creates new if None)
            feature_extractor: FeatureExtractor instance (creates new if None)
        """
        logger.info("Initializing ImageRecognizer with all recognition modules")

        # Initialize all modules
        from app.ml.category_classifier import CategoryClassifier
        from app.ml.color_extractor import ColorExtractor
        from app.ml.feature_extractor import FeatureExtractor
        from app.ml.style_classifier import StyleClassifier

        self.category_classifier = category_classifier or CategoryClassifier()
        self.color_extractor = color_extractor or ColorExtractor(n_colors=3)
        self.style_classifier = style_classifier or StyleClassifier()
        self.feature_extractor = feature_extractor or FeatureExtractor()

        logger.info("ImageRecognizer initialized successfully")

    def recognize(self, image_source: Union[str, Path, bytes, Image.Image]) -> RecognitionResult:
        """
        Perform complete image recognition pipeline

        This method integrates all recognition modules to provide comprehensive
        analysis of a garment image, including category, colors, style, and features.

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            RecognitionResult: Complete recognition result with all attributes

        Raises:
            ValueError: If image processing fails
            Exception: For other unexpected errors
        """
        try:
            logger.info("Starting complete image recognition pipeline")

            # Step 1: Category classification
            logger.debug("Step 1/4: Classifying category")
            category, category_confidence = self.category_classifier.classify_category(image_source)
            logger.info(f"Category: {category} (confidence: {category_confidence:.3f})")

            # Step 2: Color extraction
            logger.debug("Step 2/4: Extracting colors")
            colors = self.color_extractor.extract_colors(image_source)
            main_color = colors[0] if colors else None
            secondary_colors = colors[1:] if len(colors) > 1 else []

            if not main_color:
                raise ValueError("Failed to extract main color from image")

            logger.info(
                f"Colors: main={main_color.name}, "
                f"secondary={[c.name for c in secondary_colors]}"
            )

            # Step 3: Style classification
            logger.debug("Step 3/4: Classifying style tags")
            style_tags = self.style_classifier.classify_style(image_source)
            logger.info(f"Style tags: {style_tags}")

            # Step 4: Feature extraction
            logger.debug("Step 4/4: Extracting feature vector")
            feature_vector = self.feature_extractor.extract(image_source)
            logger.info(f"Feature vector extracted: shape={feature_vector.shape}")

            # Construct result
            result = RecognitionResult(
                category=category,
                category_confidence=category_confidence,
                main_color=main_color,
                secondary_colors=secondary_colors,
                style_tags=style_tags,
                feature_vector=feature_vector.tolist(),
            )

            logger.info("Image recognition pipeline completed successfully")

            return result

        except ValueError as e:
            logger.error(f"Image recognition failed with validation error: {e}")
            raise
        except Exception as e:
            logger.error(f"Image recognition failed with unexpected error: {e}", exc_info=True)
            raise Exception(f"Image recognition pipeline failed: {str(e)}")

    def recognize_batch(
        self, image_sources: List[Union[str, Path, bytes, Image.Image]]
    ) -> List[RecognitionResult]:
        """
        Perform batch image recognition for multiple images

        Args:
            image_sources: List of image file paths, bytes, or PIL Images

        Returns:
            List[RecognitionResult]: List of recognition results

        Raises:
            ValueError: If image_sources is empty or invalid
        """
        if not image_sources:
            raise ValueError("image_sources cannot be empty")

        logger.info(f"Starting batch recognition for {len(image_sources)} images")

        results = []
        for idx, image_source in enumerate(image_sources):
            try:
                logger.debug(f"Processing image {idx + 1}/{len(image_sources)}")
                result = self.recognize(image_source)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process image {idx + 1}: {e}")
                # Continue processing other images
                continue

        logger.info(f"Batch recognition completed: {len(results)}/{len(image_sources)} successful")

        return results
