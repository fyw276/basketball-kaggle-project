"""
Unit tests for FeatureExtractor
"""

from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from app.ml.feature_extractor import FeatureExtractor


class TestFeatureExtractor:
    """Test suite for FeatureExtractor class"""

    @pytest.fixture
    def extractor(self):
        """Create FeatureExtractor instance without cache"""
        return FeatureExtractor(enable_cache=False)

    @pytest.fixture
    def extractor_with_cache(self):
        """Create FeatureExtractor instance with mock cache"""
        mock_cache = Mock()
        mock_cache.get.return_value = None
        mock_cache.set.return_value = True
        return FeatureExtractor(cache=mock_cache, enable_cache=True)

    @pytest.fixture
    def test_image(self):
        """Create a test image"""
        # Create a simple RGB image
        return Image.new("RGB", (224, 224), color=(100, 150, 200))

    def test_initialization(self, extractor):
        """Test FeatureExtractor initialization"""
        assert extractor is not None
        assert extractor.model is not None
        assert extractor.preprocessor is not None
        assert extractor.model_loader is not None

    def test_initialization_with_cache(self, extractor_with_cache):
        """Test FeatureExtractor initialization with cache enabled"""
        assert extractor_with_cache is not None
        assert extractor_with_cache.enable_cache is True
        assert extractor_with_cache.cache is not None

    def test_feature_dimension(self, extractor):
        """Test that feature dimension is 1280"""
        dimension = extractor.get_feature_dimension()
        assert dimension == 1280

    def test_extract_single_image(self, extractor, test_image):
        """Test extracting features from a single image"""
        features = extractor.extract(test_image)

        # Check shape
        assert features.shape == (1280,)

        # Check data type
        assert features.dtype == np.float32 or features.dtype == np.float64

        # Check L2 normalization (norm should be 1.0)
        norm = np.linalg.norm(features)
        assert np.isclose(norm, 1.0, atol=1e-5)

    def test_extract_with_cache(self, extractor_with_cache, test_image):
        """Test extracting features with caching"""
        # First extraction - should cache
        features1 = extractor_with_cache.extract(test_image, use_cache=True)

        # Verify cache.set was called
        assert extractor_with_cache.cache.set.called

        # Check features
        assert features1.shape == (1280,)
        norm = np.linalg.norm(features1)
        assert np.isclose(norm, 1.0, atol=1e-5)

    def test_extract_cache_hit(self, test_image):
        """Test cache hit scenario"""
        # Create mock cache with cached features
        mock_cache = Mock()
        cached_features = np.random.rand(1280).astype(np.float32)
        cached_features = cached_features / np.linalg.norm(cached_features)
        mock_cache.get.return_value = cached_features.tolist()

        extractor = FeatureExtractor(cache=mock_cache, enable_cache=True)

        # Extract - should return cached features
        features = extractor.extract(test_image, use_cache=True)

        # Verify cache.get was called
        assert mock_cache.get.called

        # Features should match cached features
        assert np.allclose(features, cached_features, atol=1e-5)

    def test_extract_from_different_sources(self, extractor, test_image, tmp_path):
        """Test extracting features from different image sources"""
        # Test with PIL Image
        features_pil = extractor.extract(test_image)
        assert features_pil.shape == (1280,)

        # Test with file path
        image_path = tmp_path / "test.jpg"
        test_image.save(image_path)
        features_path = extractor.extract(str(image_path))
        assert features_path.shape == (1280,)

        # Features should be similar (not identical due to JPEG compression)
        similarity = np.dot(features_pil, features_path)
        assert similarity > 0.95  # High similarity expected

    def test_extract_batch(self, extractor):
        """Test batch feature extraction"""
        # Create multiple test images
        images = [
            Image.new("RGB", (224, 224), color=(255, 0, 0)),
            Image.new("RGB", (224, 224), color=(0, 255, 0)),
            Image.new("RGB", (224, 224), color=(0, 0, 255)),
        ]

        features = extractor.extract_batch(images)

        # Check shape
        assert features.shape == (3, 1280)

        # Check L2 normalization for each vector
        for i in range(3):
            norm = np.linalg.norm(features[i])
            assert np.isclose(norm, 1.0, atol=1e-5)

    def test_extract_batch_with_cache(self, extractor_with_cache):
        """Test batch extraction with caching"""
        images = [
            Image.new("RGB", (224, 224), color=(255, 0, 0)),
            Image.new("RGB", (224, 224), color=(0, 255, 0)),
        ]

        features = extractor_with_cache.extract_batch(images, use_cache=True)

        # Check shape
        assert features.shape == (2, 1280)

        # Verify cache operations were called
        assert extractor_with_cache.cache.get.called
        assert extractor_with_cache.cache.set.called

    def test_extract_batch_empty_list(self, extractor):
        """Test that empty list raises ValueError"""
        with pytest.raises(ValueError, match="image_sources cannot be empty"):
            extractor.extract_batch([])

    def test_l2_normalization(self, extractor):
        """Test L2 normalization method"""
        # Create unnormalized features
        features = np.array([[3.0, 4.0, 0.0] * 426 + [3.0, 4.0]])  # 1280 dims
        features = features.reshape(1, 1280)

        # Normalize
        normalized = extractor._l2_normalize(features)

        # Check norm is 1.0
        norm = np.linalg.norm(normalized[0])
        assert np.isclose(norm, 1.0, atol=1e-5)

    def test_feature_consistency(self, extractor, test_image):
        """Test that same image produces consistent features"""
        features1 = extractor.extract(test_image)
        features2 = extractor.extract(test_image)

        # Features should be identical
        assert np.allclose(features1, features2, atol=1e-6)

    def test_different_images_different_features(self, extractor):
        """Test that different images produce different features"""
        image1 = Image.new("RGB", (224, 224), color=(255, 0, 0))
        image2 = Image.new("RGB", (224, 224), color=(0, 0, 255))

        features1 = extractor.extract(image1)
        features2 = extractor.extract(image2)

        # Features should be different
        assert not np.allclose(features1, features2, atol=0.1)

        # But both should be normalized
        assert np.isclose(np.linalg.norm(features1), 1.0, atol=1e-5)
        assert np.isclose(np.linalg.norm(features2), 1.0, atol=1e-5)

    @pytest.mark.asyncio
    async def test_extract_async(self, extractor, test_image):
        """Test async feature extraction"""
        features = await extractor.extract_async(test_image)

        # Check shape and normalization
        assert features.shape == (1280,)
        norm = np.linalg.norm(features)
        assert np.isclose(norm, 1.0, atol=1e-5)

    @pytest.mark.asyncio
    async def test_extract_batch_async(self, extractor):
        """Test async batch feature extraction"""
        images = [
            Image.new("RGB", (224, 224), color=(255, 0, 0)),
            Image.new("RGB", (224, 224), color=(0, 255, 0)),
        ]

        features = await extractor.extract_batch_async(images)

        # Check shape
        assert features.shape == (2, 1280)

        # Check L2 normalization for each vector
        for i in range(2):
            norm = np.linalg.norm(features[i])
            assert np.isclose(norm, 1.0, atol=1e-5)

    def test_compute_image_hash(self, extractor, test_image, tmp_path):
        """Test image hash computation"""
        # Test with PIL Image
        hash1 = extractor._compute_image_hash(test_image)
        assert isinstance(hash1, str)
        assert len(hash1) == 32  # MD5 hash length

        # Test with file path
        image_path = tmp_path / "test.png"
        test_image.save(image_path)
        hash2 = extractor._compute_image_hash(str(image_path))
        assert isinstance(hash2, str)
        assert len(hash2) == 32

        # Same image should produce same hash
        hash3 = extractor._compute_image_hash(test_image)
        assert hash1 == hash3

    def test_cache_operations(self, extractor_with_cache, test_image):
        """Test cache get and set operations"""
        # Compute hash
        image_hash = extractor_with_cache._compute_image_hash(test_image)

        # Create test features
        test_features = np.random.rand(1280).astype(np.float32)

        # Test caching
        result = extractor_with_cache._cache_features(image_hash, test_features)
        assert result is True
        assert extractor_with_cache.cache.set.called

    def test_clear_cache(self, extractor_with_cache):
        """Test cache clearing"""
        extractor_with_cache.cache.flush_all.return_value = True
        result = extractor_with_cache.clear_cache()
        assert result is True
        assert extractor_with_cache.cache.flush_all.called

    def test_feature_vector_dimension_1280(self, extractor, test_image):
        """Test that feature vectors are exactly 1280 dimensions (Requirement 12.5)"""
        features = extractor.extract(test_image)

        # Verify exact dimension
        assert features.shape == (1280,), f"Expected shape (1280,), got {features.shape}"
        assert len(features) == 1280, f"Expected 1280 features, got {len(features)}"

        # Verify it's a 1D array
        assert features.ndim == 1, f"Expected 1D array, got {features.ndim}D"

    def test_l2_normalization_exact(self, extractor, test_image):
        """Test L2 normalization produces unit vectors (norm = 1.0)"""
        features = extractor.extract(test_image)

        # Calculate L2 norm
        norm = np.linalg.norm(features)

        # Verify norm is exactly 1.0 (within floating point precision)
        assert np.isclose(norm, 1.0, atol=1e-6), f"Expected norm 1.0, got {norm}"

        # Verify no NaN or Inf values
        assert not np.any(np.isnan(features)), "Feature vector contains NaN values"
        assert not np.any(np.isinf(features)), "Feature vector contains Inf values"

    def test_batch_extraction_dimension_consistency(self, extractor):
        """Test batch extraction maintains consistent dimensions"""
        # Create batch of different colored images
        images = [
            Image.new("RGB", (224, 224), color=(255, 0, 0)),
            Image.new("RGB", (224, 224), color=(0, 255, 0)),
            Image.new("RGB", (224, 224), color=(0, 0, 255)),
            Image.new("RGB", (224, 224), color=(255, 255, 0)),
            Image.new("RGB", (224, 224), color=(255, 0, 255)),
        ]

        features = extractor.extract_batch(images)

        # Verify batch shape
        assert features.shape == (5, 1280), f"Expected shape (5, 1280), got {features.shape}"

        # Verify each feature vector is 1280 dimensions
        for i, feature_vec in enumerate(features):
            assert feature_vec.shape == (1280,), f"Feature {i} has wrong shape: {feature_vec.shape}"

            # Verify L2 normalization for each
            norm = np.linalg.norm(feature_vec)
            assert np.isclose(norm, 1.0, atol=1e-5), f"Feature {i} norm is {norm}, expected 1.0"

    def test_batch_extraction_large_batch(self, extractor):
        """Test batch extraction with larger batch size"""
        # Create a larger batch (10 images)
        images = [
            Image.new("RGB", (224, 224), color=(i * 25, (255 - i * 25), 128)) for i in range(10)
        ]

        features = extractor.extract_batch(images)

        # Verify shape
        assert features.shape == (10, 1280)

        # Verify all vectors are normalized
        norms = np.linalg.norm(features, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5), f"Not all norms are 1.0: {norms}"

    def test_l2_normalization_zero_vector_handling(self, extractor):
        """Test L2 normalization handles edge case of near-zero vectors"""
        # Create a very small feature vector (edge case)
        small_features = np.array([[1e-15] * 1280])

        # Normalize
        normalized = extractor._l2_normalize(small_features)

        # Should not produce NaN or Inf (this is the key requirement)
        assert not np.any(np.isnan(normalized)), "Normalization produced NaN"
        assert not np.any(np.isinf(normalized)), "Normalization produced Inf"

        # The implementation uses a minimum norm of 1e-12 to avoid division by zero
        # So the result will be the original vector divided by 1e-12
        # This is acceptable behavior - the key is no NaN/Inf values

    def test_feature_extraction_data_type(self, extractor, test_image):
        """Test that extracted features have correct data type"""
        features = extractor.extract(test_image)

        # Verify data type is float
        assert features.dtype in [
            np.float32,
            np.float64,
        ], f"Expected float type, got {features.dtype}"

        # Verify all values are finite
        assert np.all(np.isfinite(features)), "Feature vector contains non-finite values"
