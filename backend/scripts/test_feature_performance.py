"""
Test script to demonstrate feature extraction performance optimizations
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import time

from PIL import Image

from app.ml.feature_extractor import FeatureExtractor


def create_test_images(count: int = 10):
    """Create test images for performance testing"""
    images = []
    for i in range(count):
        # Create images with different colors
        color = (
            (i * 25) % 256,
            (i * 50) % 256,
            (i * 75) % 256,
        )
        img = Image.new("RGB", (224, 224), color=color)
        images.append(img)
    return images


def test_sequential_extraction():
    """Test sequential feature extraction (baseline)"""
    print("\n=== Sequential Extraction (No Cache) ===")
    extractor = FeatureExtractor(enable_cache=False)
    images = create_test_images(10)

    start_time = time.time()
    for i, img in enumerate(images):
        features = extractor.extract(img)
        print(f"Image {i+1}: Extracted {features.shape[0]} features")

    elapsed = time.time() - start_time
    print(f"Total time: {elapsed:.2f}s")
    print(f"Average per image: {elapsed/len(images):.2f}s")
    return elapsed


def test_batch_extraction():
    """Test batch feature extraction"""
    print("\n=== Batch Extraction (No Cache) ===")
    extractor = FeatureExtractor(enable_cache=False)
    images = create_test_images(10)

    start_time = time.time()
    features = extractor.extract_batch(images)
    elapsed = time.time() - start_time

    print(f"Extracted {features.shape[0]} images with {features.shape[1]} features each")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Average per image: {elapsed/len(images):.2f}s")
    return elapsed


def test_cached_extraction():
    """Test feature extraction with caching"""
    print("\n=== Cached Extraction ===")
    extractor = FeatureExtractor(enable_cache=True)
    images = create_test_images(5)

    # First pass - populate cache
    print("First pass (populating cache):")
    start_time = time.time()
    for i, img in enumerate(images):
        features = extractor.extract(img, use_cache=True)
        print(f"  Image {i+1}: Extracted {features.shape[0]} features")
    first_pass = time.time() - start_time
    print(f"  Time: {first_pass:.2f}s")

    # Second pass - use cache
    print("\nSecond pass (using cache):")
    start_time = time.time()
    for i, img in enumerate(images):
        features = extractor.extract(img, use_cache=True)
        print(f"  Image {i+1}: Retrieved {features.shape[0]} features from cache")
    second_pass = time.time() - start_time
    print(f"  Time: {second_pass:.2f}s")

    speedup = first_pass / second_pass if second_pass > 0 else float("inf")
    print(f"\nSpeedup: {speedup:.2f}x faster with cache")
    return first_pass, second_pass


async def test_async_extraction():
    """Test async feature extraction"""
    print("\n=== Async Extraction ===")
    extractor = FeatureExtractor(enable_cache=False)
    images = create_test_images(5)

    start_time = time.time()

    # Extract features concurrently
    tasks = [extractor.extract_async(img) for img in images]
    results = await asyncio.gather(*tasks)

    elapsed = time.time() - start_time

    print(f"Extracted {len(results)} images asynchronously")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Average per image: {elapsed/len(images):.2f}s")
    return elapsed


async def test_async_batch_extraction():
    """Test async batch feature extraction"""
    print("\n=== Async Batch Extraction ===")
    extractor = FeatureExtractor(enable_cache=False)
    images = create_test_images(10)

    start_time = time.time()
    features = await extractor.extract_batch_async(images)
    elapsed = time.time() - start_time

    print(f"Extracted {features.shape[0]} images with {features.shape[1]} features each")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Average per image: {elapsed/len(images):.2f}s")
    return elapsed


def main():
    """Run all performance tests"""
    print("=" * 60)
    print("Feature Extraction Performance Tests")
    print("=" * 60)

    # Test 1: Sequential extraction
    seq_time = test_sequential_extraction()

    # Test 2: Batch extraction
    batch_time = test_batch_extraction()

    # Test 3: Cached extraction
    cache_first, cache_second = test_cached_extraction()

    # Test 4: Async extraction
    async_time = asyncio.run(test_async_extraction())

    # Test 5: Async batch extraction
    async_batch_time = asyncio.run(test_async_batch_extraction())

    # Summary
    print("\n" + "=" * 60)
    print("Performance Summary")
    print("=" * 60)
    print(f"Sequential (10 images):      {seq_time:.2f}s")
    print(f"Batch (10 images):           {batch_time:.2f}s")
    print(f"  Speedup vs Sequential:     {seq_time/batch_time:.2f}x")
    print(f"\nCached (5 images, 1st pass): {cache_first:.2f}s")
    print(f"Cached (5 images, 2nd pass): {cache_second:.2f}s")
    print(f"  Speedup with cache:        {cache_first/cache_second:.2f}x")
    print(f"\nAsync (5 images):            {async_time:.2f}s")
    print(f"Async Batch (10 images):     {async_batch_time:.2f}s")
    print("=" * 60)

    # Performance targets check
    print("\nPerformance Target Check (< 2s per image):")
    avg_batch = batch_time / 10
    print(
        f"  Batch extraction: {avg_batch:.2f}s per image - {'✓ PASS' if avg_batch < 2 else '✗ FAIL'}"
    )
    print(
        f"  Cached extraction: {cache_second/5:.2f}s per image - {'✓ PASS' if cache_second/5 < 2 else '✗ FAIL'}"
    )


if __name__ == "__main__":
    main()
