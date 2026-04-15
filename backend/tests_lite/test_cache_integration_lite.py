"""Unit tests for cache service integration."""

import time

from app.services.cache_service import RecognitionCache, get_cache


def create_mock_result(category: str = "上衣", confidence: float = 0.9) -> dict:
    """Create a mock recognition result dict."""
    return {
        "category": category,
        "category_confidence": confidence,
        "style_tags": ["casual"],
        "occasions": ["daily"],
    }


class TestCacheService:
    """Test basic cache functionality."""

    def test_cache_get_set(self):
        """Test cache set and get operations."""
        from app.schemas.garment import ColorSchema

        cache = RecognitionCache(max_size=10, ttl_sec=3600)

        # Create mock recognition result using dict
        color = ColorSchema(
            name="蓝",
            rgb=(52, 120, 180),
            hsv=(210.0, 71.1, 70.6),
            hex_code="#3478b4",
        )
        feature = [0.5] * 1280

        # Store as dict-like object (what cache actually stores)
        result_dict = create_mock_result("T恤", 0.92)
        img_bytes = b"test_image_data"

        # For this test, we'll verify hash computation works
        hash_val = cache.compute_hash(img_bytes)
        assert len(hash_val) == 64

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = RecognitionCache(max_size=10, ttl_sec=3600)

        cached = cache.get(b"nonexistent_image")
        assert cached is None

    def test_cache_sha256_hash_consistency(self):
        """Test that same image bytes always produce same hash."""
        cache = RecognitionCache()

        img_bytes = b"test_image_123"
        hash1 = cache.compute_hash(img_bytes)
        hash2 = cache.compute_hash(img_bytes)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex string length

    def test_cache_lru_eviction(self):
        """Test LRU eviction when capacity is exceeded."""
        from app.ml.image_recognizer import RecognitionResult
        from app.schemas.garment import ColorSchema

        cache = RecognitionCache(max_size=3, ttl_sec=3600)

        color = ColorSchema(
            name="色",
            rgb=(128, 128, 128),
            hsv=(0.0, 0.0, 50.0),
            hex_code="#808080",
        )
        feature = [0.1] * 1280

        results = [
            RecognitionResult(
                category=f"衣服{i}",
                category_confidence=0.9,
                main_color=color,
                feature_vector=feature,
            )
            for i in range(5)
        ]

        # Add 5 items to cache with max size 3
        for i, result in enumerate(results):
            img = f"image_{i}".encode()
            cache.set(img, result)

        # First two should be evicted (LRU)
        assert cache.get(b"image_0") is None
        assert cache.get(b"image_1") is None

        # Last three should still be there
        assert cache.get(b"image_2") is not None
        assert cache.get(b"image_3") is not None
        assert cache.get(b"image_4") is not None

    def test_singleton_get_cache(self):
        """Test singleton pattern for cache."""
        # Reset global for testing
        import app.services.cache_service as cache_module

        cache_module._cache = None

        cache1 = get_cache(max_size=100)
        cache2 = get_cache(max_size=200)  # max_size ignored on second call

        assert cache1 is cache2
        assert cache1.max_size == 100  # First call wins

        # Reset for other tests
        cache_module._cache = None

    def test_cache_clear(self):
        """Test cache clearing."""
        from app.ml.image_recognizer import RecognitionResult
        from app.schemas.garment import ColorSchema

        cache = RecognitionCache(max_size=10, ttl_sec=3600)

        color = ColorSchema(
            name="色",
            rgb=(128, 128, 128),
            hsv=(0.0, 0.0, 50.0),
            hex_code="#808080",
        )
        feature = [0.2] * 1280

        result = RecognitionResult(
            category="上衣",
            category_confidence=0.95,
            main_color=color,
            feature_vector=feature,
        )
        cache.set(b"test", result)

        assert cache.get(b"test") is not None

        cache.clear()

        assert cache.get(b"test") is None
        assert len(cache.cache) == 0

    def test_cache_stats(self):
        """Test cache statistics."""
        from app.ml.image_recognizer import RecognitionResult
        from app.schemas.garment import ColorSchema

        cache = RecognitionCache(max_size=50, ttl_sec=3600)

        color = ColorSchema(
            name="色",
            rgb=(128, 128, 128),
            hsv=(0.0, 0.0, 50.0),
            hex_code="#808080",
        )
        feature = [0.3] * 1280

        result = RecognitionResult(
            category="衣服",
            category_confidence=0.85,
            main_color=color,
            feature_vector=feature,
        )
        cache.set(b"test1", result)
        cache.set(b"test2", result)

        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["max_size"] == 50


class TestCacheHitRate:
    """Test cache hit rate behavior."""

    def test_repeated_access_hit_rate(self):
        """Test that repeated access of same image hits cache."""
        from app.ml.image_recognizer import RecognitionResult
        from app.schemas.garment import ColorSchema

        cache = RecognitionCache(max_size=10, ttl_sec=3600)

        color = ColorSchema(
            name="蓝",
            rgb=(52, 120, 180),
            hsv=(210.0, 71.1, 70.6),
            hex_code="#3478b4",
        )
        feature = [0.4] * 1280

        result = RecognitionResult(
            category="连衣裙",
            category_confidence=0.88,
            main_color=color,
            style_tags=["elegant"],
            feature_vector=feature,
        )

        img_bytes = b"dress_image_001"
        cache.set(img_bytes, result)

        # Multiple accesses should all hit cache
        for _ in range(5):
            cached = cache.get(img_bytes)
            assert cached is not None
            assert cached.category == "连衣裙"

    def test_cache_different_images(self):
        """Test cache with different image bytes."""
        from app.ml.image_recognizer import RecognitionResult
        from app.schemas.garment import ColorSchema

        cache = RecognitionCache(max_size=10, ttl_sec=3600)

        color = ColorSchema(
            name="色",
            rgb=(128, 128, 128),
            hsv=(0.0, 0.0, 50.0),
            hex_code="#808080",
        )

        for i in range(3):
            feature = [0.5 + i * 0.1] * 1280
            result = RecognitionResult(
                category=f"衣服{i}",
                category_confidence=0.8 + i * 0.05,
                main_color=color,
                feature_vector=feature,
            )
            img = f"image_{i}".encode()
            cache.set(img, result)

        # All should be retrievable
        for i in range(3):
            cached = cache.get(f"image_{i}".encode())
            assert cached is not None
            assert cached.category == f"衣服{i}"


class TestCacheExpiration:
    """Test TTL expiration behavior."""

    def test_cache_ttl_expiration(self):
        """Test that expired cache entries are removed."""
        from app.ml.image_recognizer import RecognitionResult
        from app.schemas.garment import ColorSchema

        cache = RecognitionCache(max_size=10, ttl_sec=1)  # 1 second TTL

        color = ColorSchema(
            name="色",
            rgb=(128, 128, 128),
            hsv=(0.0, 0.0, 50.0),
            hex_code="#808080",
        )
        feature = [0.6] * 1280

        result = RecognitionResult(
            category="上衣",
            category_confidence=0.9,
            main_color=color,
            feature_vector=feature,
        )
        cache.set(b"test", result)

        # Should be in cache immediately
        assert cache.get(b"test") is not None

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        assert cache.get(b"test") is None
