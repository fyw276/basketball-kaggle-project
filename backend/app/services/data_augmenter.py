"""Data augmentation utilities for training dataset expansion.

Applies transformations to training images to increase dataset diversity:
rotation, brightness, contrast, and crop variations.
"""

import io
import logging
import random
from typing import List, Tuple

from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)


class DataAugmenter:
    """Apply data augmentation transformations to training images."""

    def __init__(
        self,
        rotation_range: Tuple[int, int] = (-15, 15),
        brightness_range: Tuple[float, float] = (0.8, 1.2),
        contrast_range: Tuple[float, float] = (0.8, 1.2),
    ):
        """Initialize data augmenter.

        Args:
            rotation_range: Min/max rotation in degrees
            brightness_range: Min/max brightness factor
            contrast_range: Min/max contrast factor
        """
        self.rotation_range = rotation_range
        self.brightness_range = brightness_range
        self.contrast_range = contrast_range

    def augment(self, image_bytes: bytes, num_variants: int = 1, seed: int = None) -> List[bytes]:
        """Generate augmented variants of an image.

        Args:
            image_bytes: Original image data
            num_variants: Number of variants to generate
            seed: Random seed for reproducibility

        Returns:
            List of augmented image byte strings
        """
        if seed is not None:
            random.seed(seed)

        try:
            img = Image.open(io.BytesIO(image_bytes))

            variants = [image_bytes]  # Include original

            for _ in range(num_variants):
                variant = self._apply_transforms(img)
                variant_bytes = io.BytesIO()
                variant.save(variant_bytes, format="JPEG", quality=85)
                variants.append(variant_bytes.getvalue())

            logger.debug(f"Generated {len(variants)} image variants")
            return variants

        except Exception as e:
            logger.error(f"Augmentation failed: {e}")
            return [image_bytes]  # Return original on error

    def _apply_transforms(self, img: Image.Image) -> Image.Image:
        """Apply random transformations to image.

        Args:
            img: PIL Image

        Returns:
            Augmented PIL Image
        """
        # Random rotation
        angle = random.randint(self.rotation_range[0], self.rotation_range[1])
        img = img.rotate(angle, expand=False, fillcolor=(255, 255, 255))

        # Random brightness
        brightness_factor = random.uniform(self.brightness_range[0], self.brightness_range[1])
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(brightness_factor)

        # Random contrast
        contrast_factor = random.uniform(self.contrast_range[0], self.contrast_range[1])
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(contrast_factor)

        # Random crop (10-20% of edges)
        if random.random() > 0.5:
            width, height = img.size
            crop_fraction = random.uniform(0.1, 0.2)
            left = int(width * crop_fraction)
            top = int(height * crop_fraction)
            right = int(width * (1 - crop_fraction))
            bottom = int(height * (1 - crop_fraction))
            img = img.crop((left, top, right, bottom))
            # Resize back to original size
            img = img.resize((width, height), Image.Resampling.LANCZOS)

        return img


# Singleton instance
_augmenter = None


def get_augmenter(
    rotation_range: Tuple[int, int] = (-15, 15),
    brightness_range: Tuple[float, float] = (0.8, 1.2),
    contrast_range: Tuple[float, float] = (0.8, 1.2),
) -> DataAugmenter:
    """Get or create singleton data augmenter.

    Args:
        rotation_range: Rotation degrees
        brightness_range: Brightness factors
        contrast_range: Contrast factors

    Returns:
        DataAugmenter instance
    """
    global _augmenter
    if _augmenter is None:
        _augmenter = DataAugmenter(
            rotation_range=rotation_range,
            brightness_range=brightness_range,
            contrast_range=contrast_range,
        )
    return _augmenter
