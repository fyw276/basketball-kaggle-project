"""
Feature extraction using MobileNetV2
"""

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
from PIL import Image

from app.core.cache import RedisCache, feature_cache_key
from app.core.logging import setup_logging
from app.ml.image_preprocessor import ImagePreprocessor
from app.ml.model_loader import ModelLoader

logger = setup_logging()


class FeatureExtractor:
    """Extract feature vectors from images using MobileNetV2"""

    def __init__(
        self,
        model_loader: ModelLoader = None,
        preprocessor: ImagePreprocessor = None,
        cache: RedisCache = None,
        enable_cache: bool = True,
    ):
        """
        Initialize feature extractor

        Args:
            model_loader: ModelLoader instance (creates new if None)
            preprocessor: ImagePreprocessor instance (creates new if None)
            cache: RedisCache instance (creates new if None)
            enable_cache: Whether to enable feature caching (default: True)
        """
        self.model_loader = model_loader or ModelLoader()
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.enable_cache = enable_cache

        # Initialize cache if enabled
        if self.enable_cache:
            from app.core.cache import get_cache

            self.cache = cache or get_cache()
        else:
            self.cache = None

        # Load the feature extraction model
        try:
            self.model = self.model_loader.load_feature_extractor()
        except Exception as e:
            logger.warning("Feature model unavailable, using zero-vector fallback: %s", e)
            self.model = None

        # Thread pool for async operations
        self._executor = ThreadPoolExecutor(max_workers=4)

        logger.info(
            "FeatureExtractor initialized successfully (cache=%s)",
            "enabled" if enable_cache else "disabled",
        )

    def extract(
        self, image_source: Union[str, Path, bytes, Image.Image], use_cache: bool = True
    ) -> np.ndarray:
        """
        Extract feature vector from a single image

        Args:
            image_source: Image file path, bytes, or PIL Image
            use_cache: Whether to use cache for this extraction (default: True)

        Returns:
            np.ndarray: 1280-dimensional L2-normalized feature vector
        """
        # Try to get from cache if enabled
        if self.enable_cache and use_cache:
            image_hash = self._compute_image_hash(image_source)
            cached_features = self._get_cached_features(image_hash)
            if cached_features is not None:
                logger.debug(f"Cache hit for image hash: {image_hash}")
                return cached_features

        # Preprocess image
        preprocessed = self.preprocessor.preprocess_single(image_source)

        # Extract features
        if self.model is None:
            return np.zeros(1280, dtype=float)

        features = self.model.predict(preprocessed, verbose=0)

        # L2 normalization
        features = self._l2_normalize(features)

        # Return as 1D array
        result = features[0]

        # Cache the result if enabled
        if self.enable_cache and use_cache:
            self._cache_features(image_hash, result)

        return result

    def extract_batch(
        self, image_sources: List[Union[str, Path, bytes, Image.Image]], use_cache: bool = True
    ) -> np.ndarray:
        """
        Extract feature vectors from multiple images

        Args:
            image_sources: List of image file paths, bytes, or PIL Images
            use_cache: Whether to use cache for this extraction (default: True)

        Returns:
            np.ndarray: Array of shape (N, 1280) with L2-normalized feature vectors
        """
        if not image_sources:
            raise ValueError("image_sources cannot be empty")

        logger.info(f"Extracting features from batch of {len(image_sources)} images")

        # Check cache for each image if enabled
        results = []
        uncached_indices = []
        uncached_sources = []
        image_hashes = []

        if self.enable_cache and use_cache:
            for idx, source in enumerate(image_sources):
                image_hash = self._compute_image_hash(source)
                image_hashes.append(image_hash)
                cached_features = self._get_cached_features(image_hash)

                if cached_features is not None:
                    results.append(cached_features)
                    logger.debug(f"Cache hit for batch image {idx}")
                else:
                    results.append(None)
                    uncached_indices.append(idx)
                    uncached_sources.append(source)
        else:
            uncached_indices = list(range(len(image_sources)))
            uncached_sources = image_sources
            results = [None] * len(image_sources)

        # Extract features for uncached images
        if uncached_sources:
            logger.info(f"Extracting {len(uncached_sources)} uncached images")

            # Preprocess batch
            preprocessed_batch = self.preprocessor.preprocess_batch(uncached_sources)

            # Extract features
            features = self.model.predict(preprocessed_batch, verbose=0)

            # L2 normalization
            features = self._l2_normalize(features)

            # Store results and cache
            for i, idx in enumerate(uncached_indices):
                results[idx] = features[i]

                # Cache the result if enabled
                if self.enable_cache and use_cache:
                    self._cache_features(image_hashes[idx], features[i])

        # Convert to numpy array
        features_array = np.array(results)

        logger.info(f"Extracted feature batch shape: {features_array.shape}")

        return features_array

    def _l2_normalize(self, features: np.ndarray) -> np.ndarray:
        """
        Apply L2 normalization to feature vectors

        Args:
            features: Feature array of shape (N, 1280)

        Returns:
            np.ndarray: L2-normalized features
        """
        # Calculate L2 norm along feature dimension
        norms = np.linalg.norm(features, axis=1, keepdims=True)

        # Avoid division by zero
        norms = np.maximum(norms, 1e-12)

        # Normalize
        normalized = features / norms

        return normalized

    def get_feature_dimension(self) -> int:
        """
        Get the dimension of feature vectors

        Returns:
            int: Feature vector dimension (1280 for MobileNetV2)
        """
        return self.model.output_shape[-1]

    async def extract_async(
        self, image_source: Union[str, Path, bytes, Image.Image], use_cache: bool = True
    ) -> np.ndarray:
        """
        Asynchronously extract feature vector from a single image

        Args:
            image_source: Image file path, bytes, or PIL Image
            use_cache: Whether to use cache for this extraction (default: True)

        Returns:
            np.ndarray: 1280-dimensional L2-normalized feature vector
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.extract, image_source, use_cache)

    async def extract_batch_async(
        self, image_sources: List[Union[str, Path, bytes, Image.Image]], use_cache: bool = True
    ) -> np.ndarray:
        """
        Asynchronously extract feature vectors from multiple images

        Args:
            image_sources: List of image file paths, bytes, or PIL Images
            use_cache: Whether to use cache for this extraction (default: True)

        Returns:
            np.ndarray: Array of shape (N, 1280) with L2-normalized feature vectors
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.extract_batch, image_sources, use_cache
        )

    def _compute_image_hash(self, image_source: Union[str, Path, bytes, Image.Image]) -> str:
        """
        Compute hash for an image source

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            str: MD5 hash of the image content
        """
        if isinstance(image_source, (str, Path)):
            # Hash file content
            with open(image_source, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        elif isinstance(image_source, bytes):
            # Hash bytes directly
            return hashlib.md5(image_source).hexdigest()
        elif isinstance(image_source, Image.Image):
            # Convert PIL Image to bytes and hash
            import io

            buffer = io.BytesIO()
            image_source.save(buffer, format="PNG")
            return hashlib.md5(buffer.getvalue()).hexdigest()
        else:
            raise ValueError(f"Unsupported image source type: {type(image_source)}")

    def _get_cached_features(self, image_hash: str) -> Optional[np.ndarray]:
        """
        Get cached features from Redis

        Args:
            image_hash: Hash of the image

        Returns:
            Optional[np.ndarray]: Cached feature vector or None if not found
        """
        if not self.cache:
            return None

        try:
            cache_key = feature_cache_key(image_hash)
            cached_data = self.cache.get(cache_key)

            if cached_data is not None:
                # Convert list back to numpy array
                return np.array(cached_data, dtype=np.float32)

            return None
        except Exception as e:
            logger.warning(f"Failed to get cached features: {e}")
            return None

    def _cache_features(self, image_hash: str, features: np.ndarray) -> bool:
        """
        Cache features to Redis

        Args:
            image_hash: Hash of the image
            features: Feature vector to cache

        Returns:
            bool: True if caching succeeded, False otherwise
        """
        if not self.cache:
            return False

        try:
            cache_key = feature_cache_key(image_hash)
            # Convert numpy array to list for JSON serialization
            features_list = features.tolist()
            # Cache for 24 hours (86400 seconds)
            return self.cache.set(cache_key, features_list, expire=86400)
        except Exception as e:
            logger.warning(f"Failed to cache features: {e}")
            return False

    def clear_cache(self) -> bool:
        """
        Clear all cached features

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.cache:
            return False

        try:
            # This is a simple implementation - in production you might want
            # to only clear feature-related keys
            logger.warning("Clearing all feature cache")
            return self.cache.flush_all()
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False

    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=False)
