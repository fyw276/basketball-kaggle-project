"""Image preprocessing utilities for normalization and optimization.

Handles image resizing, format conversion, compression to reduce file size
and normalize input for consistent model performance.
"""

import io
import logging
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Default preprocessing parameters
DEFAULT_MAX_WIDTH = 1024
DEFAULT_MAX_HEIGHT = 1024
DEFAULT_JPEG_QUALITY = 85
DEFAULT_FORMAT = "JPEG"


class ImagePreprocessor:
    """Preprocess images for recognition (resize, compress, format normalize)."""

    def __init__(
        self,
        max_width: int = DEFAULT_MAX_WIDTH,
        max_height: int = DEFAULT_MAX_HEIGHT,
        quality: int = DEFAULT_JPEG_QUALITY,
    ):
        """Initialize preprocessor.

        Args:
            max_width: Maximum image width (pixels)
            max_height: Maximum image height (pixels)
            quality: JPEG compression quality (1-95)
        """
        self.max_width = max_width
        self.max_height = max_height
        self.quality = max(1, min(95, quality))

    def preprocess(
        self, image_bytes: bytes, target_format: str = DEFAULT_FORMAT
    ) -> Tuple[bytes, Tuple[int, int], str]:
        """Preprocess image: resize, compress, normalize format.

        Args:
            image_bytes: Raw image data
            target_format: Target format (JPEG, PNG, WebP)

        Returns:
            Tuple of (preprocessed_bytes, (width, height), format_used)

        Raises:
            ValueError: If image cannot be opened or processed
        """
        try:
            # Open image
            img = Image.open(io.BytesIO(image_bytes))

            # Convert RGBA to RGB if needed
            if img.mode in ("RGBA", "LA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = rgb_img

            # Resize if needed
            img.thumbnail((self.max_width, self.max_height), Image.Resampling.LANCZOS)

            # Compress and save
            output = io.BytesIO()
            img.save(
                output,
                format=target_format,
                quality=self.quality,
                optimize=True,
            )

            processed_bytes = output.getvalue()
            logger.debug(
                f"Preprocessed image: {len(image_bytes)} → "
                f"{len(processed_bytes)} bytes, {img.size}"
            )

            return processed_bytes, img.size, target_format

        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}")
            raise ValueError(f"Cannot process image: {e}")

    def resize_only(self, image_bytes: bytes) -> Tuple[bytes, Tuple[int, int]]:
        """Resize image without compression (for display).

        Args:
            image_bytes: Raw image data

        Returns:
            Tuple of (resized_bytes, (width, height))
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((self.max_width, self.max_height), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            img.save(output, format=img.format or "JPEG")

            return output.getvalue(), img.size

        except Exception as e:
            logger.error(f"Image resize failed: {e}")
            raise ValueError(f"Cannot resize image: {e}")


# Singleton instance
_preprocessor: Optional[ImagePreprocessor] = None


def get_preprocessor(
    max_width: int = DEFAULT_MAX_WIDTH,
    max_height: int = DEFAULT_MAX_HEIGHT,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> ImagePreprocessor:
    """Get or create singleton preprocessor.

    Args:
        max_width: Max width (only used on first call)
        max_height: Max height (only used on first call)
        quality: JPEG quality (only used on first call)

    Returns:
        ImagePreprocessor instance
    """
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = ImagePreprocessor(
            max_width=max_width, max_height=max_height, quality=quality
        )
    return _preprocessor
