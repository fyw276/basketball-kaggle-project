"""Fine-tuned model inference wrapper with fallback to base model.

Provides a unified interface for attempting fine-tuned model inference
with automatic fallback to base CLIP if the fine-tuned service is unavailable.
"""

import logging
from typing import Optional

from app.ml.image_recognizer import ImageRecognizer, RecognitionResult
from app.services.finetuned_infer_client import try_finetuned_infer

logger = logging.getLogger(__name__)


class FinetunedInferenceWrapper:
    """Wrapper for fine-tuned inference with fallback to base model."""

    def __init__(self):
        """Initialize wrapper."""
        self.recognizer = ImageRecognizer()
        self.finetuned_enabled = False  # Check settings during init if needed

    def infer(
        self,
        image_bytes: bytes,
        prefer_finetuned: bool = True,
    ) -> RecognitionResult:
        """Infer clothing category from image with smart fallback.

        Strategy:
        1. If prefer_finetuned=True, try fine-tuned model first (with timeout)
        2. If fine-tuned fails or returns None, use base CLIP model
        3. Base model always succeeds (or raises exception)

        Args:
            image_bytes: Raw image data
            prefer_finetuned: Whether to attempt fine-tuned model first

        Returns:
            RecognitionResult with category and confidence
        """
        # Try fine-tuned model if enabled
        if prefer_finetuned:
            finetuned_result = try_finetuned_infer(image_bytes, feature="wrapper_infer")
            if finetuned_result:
                logger.debug("Using fine-tuned model inference")
                # Convert fine-tuned result to RecognitionResult
                return self._convert_finetuned_result(finetuned_result)

        # Fallback to base CLIP model
        logger.debug("Falling back to base CLIP model for inference")
        return self.recognizer.recognize(image_bytes)

    @staticmethod
    def _convert_finetuned_result(finetuned_dict: dict) -> RecognitionResult:
        """Convert fine-tuned API response to RecognitionResult.

        Args:
            finetuned_dict: Response from fine-tuned service

        Returns:
            RecognitionResult instance
        """
        category = finetuned_dict.get("category", "unknown")
        confidence = finetuned_dict.get("category_confidence", 0.0)
        style_tags = finetuned_dict.get("style_tags", [])
        occasions = finetuned_dict.get("occasions", [])

        result = RecognitionResult(
            category=category,
            category_confidence=max(0.0, min(1.0, float(confidence))),
            style_tags=style_tags,
            occasions=occasions,
            metadata={"source": "finetuned_model"},
        )

        return result


# Singleton instance
_wrapper: Optional[FinetunedInferenceWrapper] = None


def get_wrapper() -> FinetunedInferenceWrapper:
    """Get or create singleton inference wrapper.

    Returns:
        FinetunedInferenceWrapper instance
    """
    global _wrapper
    if _wrapper is None:
        _wrapper = FinetunedInferenceWrapper()
    return _wrapper
