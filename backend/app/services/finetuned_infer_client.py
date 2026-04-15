"""Client for calling external fine-tuned model inference service.

Provides fallback behavior: uses fine-tuned model if available,
falls back to base CLIP model if service unavailable.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def call_finetuned_infer(image_data: bytes) -> dict:
    """Call the external fine-tuned model inference API.

    Args:
        image_data: Raw image bytes to classify

    Returns:
        Normalized inference result dict with standardized fields:
        - category: Predicted clothing category
        - category_confidence: Confidence score (0-1)
        - feature_dim: Dimension of feature vector
        - style_tags: List of style tags
        - occasions: List of suitable occasions
        - feature_vector: Embedding vector

    Raises:
        Network or API errors if the service is unreachable or returns error
    """
    timeout_secs = (settings.FINETUNED_INFER_TIMEOUT_MS or 5000) / 1000.0

    with httpx.Client(timeout=timeout_secs) as client:
        url = f"{settings.FINETUNED_INFER_API_BASE_URL}{settings.FINETUNED_INFER_API_PATH}"
        headers = {}
        if settings.FINETUNED_INFER_API_KEY:
            headers["Authorization"] = f"Bearer {settings.FINETUNED_INFER_API_KEY}"

        # Send as JSON with base64-encoded image or as raw binary
        # For mock compatibility, send as JSON
        json_payload = {"image_bytes": image_data.hex()}

        response = client.post(url, json=json_payload, headers=headers)
        response.raise_for_status()

        payload = response.json()

        # Normalize the response to standard fields
        result = {
            "category": payload.get("category"),
            "category_confidence": payload.get("category_confidence"),
            "style_tags": payload.get("style_tags", []),
            "occasions": payload.get("occasions", []),
        }

        # Add feature dimension if feature vector is present
        if "feature_vector" in payload:
            feature_vec = payload["feature_vector"]
            result["feature_vector"] = feature_vec
            result["feature_dim"] = len(feature_vec) if isinstance(feature_vec, list) else 0

        return result


def try_finetuned_infer(
    image_data: bytes,
    feature: str = "",
) -> dict | None:
    """Try to call fine-tuned inference; gracefully fall back to None on any error.

    Args:
        image_data: Raw image bytes
        feature: Feature name for logging/tracking (optional)

    Returns:
        Inference result dict if successful and enabled, None otherwise
    """
    if not settings.FINETUNED_INFER_ENABLED:
        return None

    try:
        return call_finetuned_infer(image_data)
    except Exception as e:
        logger.warning(
            f"Fine-tuned inference failed (feature={feature}); "
            f"falling back to base model: {type(e).__name__}: {e}"
        )
        return None
