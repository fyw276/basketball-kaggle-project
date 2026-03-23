"""
Performance tests for the Smart Outfit Assistant API

Tests verify that the system meets performance requirements:
- Single image recognition: < 2 seconds
- Similarity calculation: < 2 seconds
- Outfit recommendation: < 3 seconds
- Concurrent request handling
"""

import asyncio
import time
from io import BytesIO

import pytest
from PIL import Image


def create_test_image(size=(224, 224), color=(100, 150, 200)):
    """Create a test image in memory"""
    img = Image.new("RGB", size, color)
    img_bytes = BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)
    return img_bytes


def test_image_recognition_performance():
    """Test that image recognition completes within 2 seconds"""
    from app.ml.image_recognizer import ImageRecognizer

    recognizer = ImageRecognizer()

    # Create test image
    img_bytes_io = create_test_image()
    img_bytes = img_bytes_io.getvalue()  # Get bytes from BytesIO

    # Measure recognition time
    start_time = time.time()
    result = recognizer.recognize(img_bytes)
    elapsed_time = time.time() - start_time

    # Verify performance requirement
    assert elapsed_time < 2.0, f"Image recognition took {elapsed_time:.2f}s, expected < 2.0s"

    # Verify result structure
    assert result is not None
    assert hasattr(result, "category")
    assert hasattr(result, "main_color")


@pytest.mark.asyncio
async def test_feature_extraction_performance():
    """Test that feature extraction is fast"""
    from app.ml.feature_extractor import FeatureExtractor

    extractor = FeatureExtractor()

    # Create test image
    img_bytes = create_test_image()

    # Measure extraction time
    start_time = time.time()
    features = await extractor.extract_async(img_bytes)
    elapsed_time = time.time() - start_time

    # Feature extraction should be fast (< 1 second)
    assert elapsed_time < 1.0, f"Feature extraction took {elapsed_time:.2f}s, expected < 1.0s"

    # Verify feature vector
    assert features is not None
    assert len(features) == 1280


@pytest.mark.asyncio
async def test_similarity_calculation_performance():
    """Test that similarity calculation completes within 2 seconds"""
    from app.services.similarity import SimilarityAnalyzer

    analyzer = SimilarityAnalyzer()

    # Create test feature vectors (simulate wardrobe of 50 items)
    import numpy as np

    target_feature = np.random.rand(1280).astype(np.float32)
    wardrobe_features = [
        (f"garment_{i}", np.random.rand(1280).astype(np.float32)) for i in range(50)
    ]

    # Measure calculation time
    start_time = time.time()
    similar_items = analyzer.find_similar_garments(target_feature, wardrobe_features, threshold=0.5)
    elapsed_time = time.time() - start_time

    # Verify performance requirement
    assert elapsed_time < 2.0, f"Similarity calculation took {elapsed_time:.2f}s, expected < 2.0s"

    # Verify results
    assert isinstance(similar_items, list)


@pytest.mark.asyncio
async def test_outfit_recommendation_performance():
    """Test that outfit recommendation completes within 3 seconds"""
    from app.services.outfit_recommender import OutfitRecommender

    recommender = OutfitRecommender()

    # Create mock garment and wardrobe
    from unittest.mock import Mock

    target_garment = Mock()
    target_garment.category = "上衣"
    target_garment.main_color = {"name": "蓝色", "rgb": [0, 100, 200], "hsv": [210, 100, 78]}
    target_garment.style_tags = ["通勤", "简约"]

    # Create mock wardrobe (30 items)
    wardrobe = []
    for i in range(30):
        garment = Mock()
        garment.garment_id = f"garment_{i}"
        garment.category = ["裤子", "裙子", "鞋"][i % 3]
        garment.main_color = {"name": "黑色", "rgb": [0, 0, 0], "hsv": [0, 0, 0]}
        garment.style_tags = ["通勤"]
        garment.image_url = f"/images/garment_{i}.jpg"
        wardrobe.append(garment)

    user_profile = Mock()
    user_profile.style_preference = ["通勤", "简约"]

    # Measure recommendation time
    start_time = time.time()
    outfits = recommender.recommend_outfits(target_garment, wardrobe, user_profile, num_outfits=3)
    elapsed_time = time.time() - start_time

    # Verify performance requirement
    assert elapsed_time < 3.0, f"Outfit recommendation took {elapsed_time:.2f}s, expected < 3.0s"

    # Verify results
    assert isinstance(outfits, list)


@pytest.mark.asyncio
async def test_batch_feature_extraction_performance():
    """Test batch feature extraction is faster than sequential"""
    from app.ml.feature_extractor import FeatureExtractor

    extractor = FeatureExtractor()

    # Create multiple test images
    num_images = 5
    images = [create_test_image() for _ in range(num_images)]

    # Measure sequential extraction
    start_time = time.time()
    for img in images:
        await extractor.extract_async(img)
        img.seek(0)  # Reset for next test
    sequential_time = time.time() - start_time

    # Measure batch extraction
    start_time = time.time()
    await extractor.extract_batch_async(images)
    batch_time = time.time() - start_time

    # Batch should be faster than sequential
    assert (
        batch_time < sequential_time
    ), f"Batch extraction ({batch_time:.2f}s) not faster than sequential ({sequential_time:.2f}s)"


@pytest.mark.asyncio
async def test_concurrent_requests_performance():
    """Test that the system can handle concurrent requests"""
    from app.ml.image_recognizer import ImageRecognizer

    recognizer = ImageRecognizer()

    # Create test images
    num_concurrent = 5
    images = [create_test_image() for _ in range(num_concurrent)]

    # Measure concurrent processing
    start_time = time.time()

    tasks = [recognizer.recognize_async(img) for img in images]
    results = await asyncio.gather(*tasks)

    elapsed_time = time.time() - start_time

    # All requests should complete
    assert len(results) == num_concurrent

    # Average time per request should be reasonable
    avg_time = elapsed_time / num_concurrent
    assert avg_time < 2.0, f"Average time per concurrent request: {avg_time:.2f}s, expected < 2.0s"


@pytest.mark.asyncio
async def test_cache_performance_improvement():
    """Test that caching improves performance"""
    from app.core.cache import get_cache_client

    cache = get_cache_client()

    # Test cache set/get performance
    test_key = "test_performance_key"
    test_value = {"data": "test" * 100}

    # Measure cache write
    start_time = time.time()
    await cache.set(test_key, test_value, expire=60)
    write_time = time.time() - start_time

    # Measure cache read
    start_time = time.time()
    cached_value = await cache.get(test_key)
    read_time = time.time() - start_time

    # Cache operations should be very fast
    assert write_time < 0.1, f"Cache write took {write_time:.3f}s, expected < 0.1s"
    assert read_time < 0.1, f"Cache read took {read_time:.3f}s, expected < 0.1s"

    # Verify cached value
    assert cached_value == test_value

    # Cleanup
    await cache.delete(test_key)


def test_similarity_calculation_scalability():
    """Test similarity calculation scales with wardrobe size"""
    from app.services.similarity import SimilarityAnalyzer

    analyzer = SimilarityAnalyzer()

    import numpy as np

    target_feature = np.random.rand(1280).astype(np.float32)

    # Test with different wardrobe sizes
    sizes = [10, 50, 100, 200]
    times = []

    for size in sizes:
        wardrobe_features = [
            (f"garment_{i}", np.random.rand(1280).astype(np.float32)) for i in range(size)
        ]

        start_time = time.time()
        analyzer.find_similar_garments(target_feature, wardrobe_features, threshold=0.5)
        elapsed_time = time.time() - start_time

        times.append(elapsed_time)

    # Time should scale roughly linearly
    # 200 items should take less than 4x the time of 50 items
    assert times[-1] < times[1] * 4, f"Similarity calculation doesn't scale well: {times}"

    # All should complete within 2 seconds
    for size, elapsed in zip(sizes, times):
        assert (
            elapsed < 2.0
        ), f"Similarity calculation for {size} items took {elapsed:.2f}s, expected < 2.0s"


@pytest.mark.asyncio
async def test_end_to_end_performance():
    """Test complete workflow performance"""
    # This test simulates a complete user workflow:
    # 1. Upload image
    # 2. Recognize garment
    # 3. Calculate similarity
    # 4. Generate recommendations

    from app.ml.feature_extractor import FeatureExtractor
    from app.ml.image_recognizer import ImageRecognizer
    from app.services.similarity import SimilarityAnalyzer

    recognizer = ImageRecognizer()
    extractor = FeatureExtractor()
    analyzer = SimilarityAnalyzer()

    # Create test image
    img_bytes = create_test_image()

    # Measure complete workflow
    start_time = time.time()

    # Step 1: Recognize
    recognition_result = await recognizer.recognize_async(img_bytes)

    # Step 2: Extract features
    img_bytes.seek(0)
    features = await extractor.extract_async(img_bytes)

    # Step 3: Calculate similarity (with mock wardrobe)
    import numpy as np

    wardrobe_features = [
        (f"garment_{i}", np.random.rand(1280).astype(np.float32)) for i in range(30)
    ]
    similar_items = analyzer.find_similar_garments(features, wardrobe_features, threshold=0.5)

    elapsed_time = time.time() - start_time

    # Complete workflow should be fast
    assert elapsed_time < 5.0, f"End-to-end workflow took {elapsed_time:.2f}s, expected < 5.0s"

    # Verify all steps completed
    assert recognition_result is not None
    assert features is not None
    assert isinstance(similar_items, list)
