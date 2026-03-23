"""
Image preprocessing for MobileNetV2 model
"""

from io import BytesIO
from pathlib import Path
from typing import List, Union

import numpy as np
from PIL import Image

from app.core.logging import setup_logging

logger = setup_logging()


class ImagePreprocessor:
    """Preprocess images for MobileNetV2 inference"""

    def __init__(self, target_size: tuple = (224, 224)):
        """
        Initialize image preprocessor

        Args:
            target_size: Target image size (height, width)
        """
        self.target_size = target_size
        logger.info(f"ImagePreprocessor initialized with target_size={target_size}")

    def load_image(self, image_source: Union[str, Path, bytes, Image.Image]) -> Image.Image:
        """
        Load image from various sources

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            PIL.Image: Loaded image in RGB format

        Raises:
            ValueError: If image format is not supported or image is invalid
        """
        try:
            # Validate input is not None
            if image_source is None:
                raise ValueError("Image source cannot be None")

            if isinstance(image_source, Image.Image):
                # Already a PIL Image
                image = image_source
            elif isinstance(image_source, bytes):
                # Load from bytes
                if len(image_source) == 0:
                    raise ValueError("Image bytes cannot be empty")
                image = Image.open(BytesIO(image_source))
            elif isinstance(image_source, (str, Path)):
                # Load from file path
                image = Image.open(image_source)
            else:
                raise ValueError(f"Unsupported image source type: {type(image_source)}")

            # Validate image dimensions
            if image.size[0] == 0 or image.size[1] == 0:
                raise ValueError(
                    f"Invalid image dimensions: {image.size[0]}x{image.size[1]}. "
                    "Image must have non-zero width and height."
                )

            # Convert to RGB (handles RGBA, grayscale, etc.)
            if image.mode != "RGB":
                logger.debug(f"Converting image from {image.mode} to RGB")
                image = image.convert("RGB")

            return image

        except Exception as e:
            logger.error(f"Failed to load image: {e}")
            raise ValueError(f"Failed to load image: {e}")

    def resize_image(self, image: Image.Image) -> Image.Image:
        """
        Resize image to target size

        Args:
            image: PIL Image

        Returns:
            PIL.Image: Resized image
        """
        if image.size != self.target_size:
            logger.debug(f"Resizing image from {image.size} to {self.target_size}")
            # Use BILINEAR resampling for better quality
            image = image.resize(self.target_size, Image.Resampling.BILINEAR)

        return image

    def normalize_image(self, image_array: np.ndarray) -> np.ndarray:
        """
        Normalize image array to [-1, 1] range (MobileNetV2 preprocessing)

        Args:
            image_array: Image array with values in [0, 255]

        Returns:
            np.ndarray: Normalized image array in [-1, 1]
        """
        # MobileNetV2 preprocessing: scale to [-1, 1]
        normalized = (image_array / 127.5) - 1.0
        return normalized

    def preprocess_single(self, image_source: Union[str, Path, bytes, Image.Image]) -> np.ndarray:
        """
        Preprocess a single image for model inference

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            np.ndarray: Preprocessed image array with shape (1, 224, 224, 3)
        """
        # 1. Load image
        image = self.load_image(image_source)

        # 2. Resize to target size
        image = self.resize_image(image)

        # 3. Convert to numpy array
        image_array = np.array(image, dtype=np.float32)

        # 4. Normalize to [-1, 1]
        image_array = self.normalize_image(image_array)

        # 5. Add batch dimension
        image_array = np.expand_dims(image_array, axis=0)

        logger.debug(f"Preprocessed image shape: {image_array.shape}")

        return image_array

    def preprocess_batch(
        self, image_sources: List[Union[str, Path, bytes, Image.Image]]
    ) -> np.ndarray:
        """
        Preprocess multiple images for batch inference

        Args:
            image_sources: List of image file paths, bytes, or PIL Images

        Returns:
            np.ndarray: Preprocessed image batch with shape (N, 224, 224, 3)
        """
        if not image_sources:
            raise ValueError("image_sources cannot be empty")

        logger.info(f"Preprocessing batch of {len(image_sources)} images")

        preprocessed_images = []

        for idx, image_source in enumerate(image_sources):
            try:
                # Preprocess single image (returns shape (1, 224, 224, 3))
                preprocessed = self.preprocess_single(image_source)
                # Remove batch dimension for stacking
                preprocessed_images.append(preprocessed[0])

            except Exception as e:
                logger.error(f"Failed to preprocess image {idx}: {e}")
                raise

        # Stack all images into a batch
        batch = np.stack(preprocessed_images, axis=0)

        logger.info(f"Preprocessed batch shape: {batch.shape}")

        return batch

    def validate_image(self, image_source: Union[str, Path, bytes, Image.Image]) -> bool:
        """
        Validate if image can be loaded and processed

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            bool: True if image is valid, False otherwise
        """
        try:
            image = self.load_image(image_source)
            # Check if image has valid dimensions
            if image.size[0] == 0 or image.size[1] == 0:
                logger.warning("Image has zero width or height")
                return False
            return True
        except Exception as e:
            logger.warning(f"Image validation failed: {e}")
            return False
