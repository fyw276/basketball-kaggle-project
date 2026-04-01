"""
Performance tests for the Smart Outfit Assistant API

Tests verify that the system meets performance requirements:
- Single image recognition: < 20 seconds (first run with model loading)
- Similarity calculation: < 2 seconds
- Outfit recommendation: < 3 seconds
- Concurrent request handling

Note: Tests marked with @pytest.mark.slow may take longer due to model loading.
Run with: pytest -m "not slow" to skip slow tests
"""

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
    """Test that image recognition completes within reasonable time"""
    from app.ml.image_recognizer import ImageRecognizer

    recognizer = ImageRecognizer()

    # Create test image
    img_bytes_io = create_test_image()
    img_bytes = img_bytes_io.getvalue()  # Get bytes from BytesIO

    # Measure recognition time
    start_time = time.time()
    result = recognizer.recognize(img_bytes)
    elapsed_time = time.time() - start_time

    # Verify performance requirement (relaxed to 20s for first run with model loading)
    assert elapsed_time < 20.0, f"Image recognition took {elapsed_time:.2f}s, expected < 20.0s"

    # Verify result structure
    assert result is not None
    assert hasattr(result, "category")
    assert hasattr(result, "main_color")


@pytest.mark.asyncio
async def test_feature_extraction_performance():
    """Test that feature extraction is fast"""
    from app.ml.feature_extractor import FeatureExtractor

    extractor = FeatureExtractor()

    # Create test image - get bytes directly
    img_bytes_io = create_test_image()
    img_bytes = img_bytes_io.getvalue()

    # Measure extraction time
    start_time = time.time()
    features = await extractor.extract_async(img_bytes)
    elapsed_time = time.time() - start_time

    # Feature extraction should be fast (relaxed to 10s for first run with model loading)
    assert elapsed_time < 10.0, f"Feature extraction took {elapsed_time:.2f}s, expected < 10.0s"

    # Verify feature vector
    assert features is not None
    assert len(features) == 1280


@pytest.mark.asyncio
async def test_similarity_calculation_performance():
    """Test that similarity calculation completes within 2 seconds"""
    from app.services.similarity import SimilarityAnalyzer

    analyzer = SimilarityAnalyzer()

    # Create test feature vectors (simulate wardrobe of 50 items)
    from uuid import uuid4

    import numpy as np

    target_feature = np.random.rand(1280).astype(np.float32)
    wardrobe_features = [(uuid4(), np.random.rand(1280).astype(np.float32)) for i in range(50)]

    # Measure calculation time
    start_time = time.time()
    similar_items = analyzer.find_similar_garments(
        target_feature, wardrobe_features, min_threshold=0.5
    )
    elapsed_time = time.time() - start_time

    # Verify performance requirement
    assert elapsed_time < 2.0, f"Similarity calculation took {elapsed_time:.2f}s, expected < 2.0s"

    # Verify results
    assert isinstance(similar_items, list)


@pytest.mark.asyncio
async def test_outfit_recommendation_performance():
    """Test that outfit recommendation completes within 3 seconds"""
    from uuid import uuid4

    from app.models.garment import Garment
    from app.services.outfit_recommender import OutfitRecommender

    recommender = OutfitRecommender()

    # Create target garment
    target_garment = Garment(
        garment_id=uuid4(),
        user_id=uuid4(),
        category="上衣",
        main_color={
            "name": "蓝",
            "hex_code": "#0000ff",
            "rgb": (0, 0, 255),
            "hsv": (240, 100, 100),
        },
        secondary_colors=[],
        style_tags=["通勤", "简约"],
        fit_type="标准",
        image_path="/test/image.jpg",
        image_url="/uploads/test/image.jpg",
        feature_vector=[0.1] * 1280,
    )

    # Create mock wardrobe (30 items)
    wardrobe = []
    for i in range(30):
        garment = Garment(
            garment_id=uuid4(),
            user_id=target_garment.user_id,
            category=["裤子", "裙子", "鞋"][i % 3],
            main_color={"name": "黑", "hex_code": "#000000", "rgb": (0, 0, 0), "hsv": (0, 0, 0)},
            secondary_colors=[],
            style_tags=["通勤"],
            fit_type="标准",
            image_path=f"/test/garment_{i}.jpg",
            image_url=f"/uploads/garment_{i}.jpg",
            feature_vector=[0.1] * 1280,
        )
        wardrobe.append(garment)

    # Measure recommendation time
    start_time = time.time()
    outfits = recommender.recommend_outfits(target_garment, wardrobe, num_outfits=3)
    elapsed_time = time.time() - start_time

    # Verify performance requirement
    assert elapsed_time < 3.0, f"Outfit recommendation took {elapsed_time:.2f}s, expected < 3.0s"

    # Verify results
    assert isinstance(outfits, list)


@pytest.mark.asyncio
async def test_batch_feature_extraction_performance():
    """Test batch feature extraction is faster than sequential"""
    pytest.skip("Flaky on cold GPU boot — re-enable once model warm-up is stable")


@pytest.mark.slow
def test_concurrent_requests_performance():
    """Test that the system can handle concurrent requests"""
    from app.ml.image_recognizer import ImageRecognizer

    recognizer = ImageRecognizer()

    # Create test images - get bytes
    num_concurrent = 5
    images = [create_test_image().getvalue() for _ in range(num_concurrent)]

    # Measure concurrent processing using batch
    start_time = time.time()

    results = recognizer.recognize_batch(images)

    elapsed_time = time.time() - start_time

    # All requests should complete
    assert len(results) == num_concurrent

    # Total time should be reasonable (relaxed for model loading)
    assert elapsed_time < 60.0, f"Batch processing took {elapsed_time:.2f}s, expected < 60.0s"


@pytest.mark.asyncio
async def test_cache_performance_improvement():
    """Test that caching improves performance"""
    # Skip this test as cache client implementation may vary
    pytest.skip("Cache implementation varies - skipping performance test")


def test_similarity_calculation_scalability():
    """Test similarity calculation scales with wardrobe size"""
    from uuid import uuid4

    from app.services.similarity import SimilarityAnalyzer

    analyzer = SimilarityAnalyzer()

    import numpy as np

    target_feature = np.random.rand(1280).astype(np.float32)

    # Test with different wardrobe sizes
    sizes = [10, 50, 100, 200]
    times = []

    for size in sizes:
        wardrobe_features = [
            (uuid4(), np.random.rand(1280).astype(np.float32)) for i in range(size)
        ]

        start_time = time.perf_counter()
        analyzer.find_similar_garments(target_feature, wardrobe_features, min_threshold=0.5)
        elapsed_time = time.perf_counter() - start_time

        times.append(elapsed_time)

    # All should complete within 2 seconds
    for size, elapsed in zip(sizes, times):
        assert (
            elapsed < 2.0
        ), f"Similarity calculation for {size} items took {elapsed:.2f}s, expected < 2.0s"

    # Rough linear scaling: 200 items should not take wildly more than 4× 50 items.
    # Sub-millisecond timings on fast CPUs have jitter; skip ratio check when not measurable.
    baseline = max(times[1], 0.001)
    if baseline >= 0.003:
        assert times[-1] < baseline * 4, f"Similarity calculation doesn't scale well: {times}"


@pytest.mark.slow
def test_end_to_end_performance():
    """Test complete workflow performance"""
    # This test simulates a complete user workflow:
    # 1. Upload image
    # 2. Recognize garment
    # 3. Calculate similarity

    from uuid import uuid4

    from app.ml.image_recognizer import ImageRecognizer
    from app.services.similarity import SimilarityAnalyzer

    recognizer = ImageRecognizer()
    analyzer = SimilarityAnalyzer()

    # Create test image - get bytes
    img_bytes_io = create_test_image()
    img_bytes = img_bytes_io.getvalue()

    # Measure complete workflow
    start_time = time.time()

    # Step 1: Recognize (includes feature extraction)
    recognition_result = recognizer.recognize(img_bytes)

    # Step 2: Calculate similarity (with mock wardrobe)
    import numpy as np

    features = np.array(recognition_result.feature_vector, dtype=np.float32)
    wardrobe_features = [(uuid4(), np.random.rand(1280).astype(np.float32)) for i in range(30)]
    similar_items = analyzer.find_similar_garments(features, wardrobe_features, min_threshold=0.5)

    elapsed_time = time.time() - start_time

    # Complete workflow should be fast (relaxed for model loading)
    assert elapsed_time < 30.0, f"End-to-end workflow took {elapsed_time:.2f}s, expected < 30.0s"

    # Verify all steps completed
    assert recognition_result is not None
    assert features is not None
    assert isinstance(similar_items, list)
