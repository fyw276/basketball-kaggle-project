"""
Test script to verify MobileNetV2 model loading and feature extraction
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import numpy as np
from PIL import Image

from app.ml.feature_extractor import FeatureExtractor
from app.ml.image_preprocessor import ImagePreprocessor
from app.ml.model_loader import ModelLoader


def test_model_loader():
    """Test ModelLoader"""
    print("\n=== Testing ModelLoader ===")

    ModelLoader()
    print("✓ ModelLoader initialized")

    # Load feature extractor
    model = loader.load_feature_extractor()
    print("✓ MobileNetV2 loaded")

    # Get model info
    info = loader.get_model_info()
    print(f"✓ Model info: {info}")

    return loader


def test_image_preprocessor():
    """Test ImagePreprocessor"""
    print("\n=== Testing ImagePreprocessor ===")

    ImagePreprocessor()
    print("✓ ImagePreprocessor initialized")

    # Create a test image
    test_image = Image.new("RGB", (300, 400), color="red")
    print(f"✓ Created test image: {test_image.size}")

    # Preprocess single image
    preprocessed = preprocessor.preprocess_single(test_image)
    print(f"✓ Preprocessed shape: {preprocessed.shape}")
    print(f"✓ Value range: [{preprocessed.min():.2f}, {preprocessed.max():.2f}]")

    # Verify shape
    assert preprocessed.shape == (1, 224, 224, 3), "Incorrect shape"
    print("✓ Shape verification passed")

    # Verify normalization range
    assert preprocessed.min() >= -1.0 and preprocessed.max() <= 1.0, "Incorrect normalization"
    print("✓ Normalization verification passed")

    # Test batch preprocessing
    test_images = [Image.new("RGB", (300, 400), color=c) for c in ["red", "green", "blue"]]
    batch = preprocessor.preprocess_batch(test_images)
    print(f"✓ Batch preprocessed shape: {batch.shape}")

    assert batch.shape == (3, 224, 224, 3), "Incorrect batch shape"
    print("✓ Batch shape verification passed")

    return preprocessor


def test_feature_extractor():
    """Test FeatureExtractor"""
    print("\n=== Testing FeatureExtractor ===")

    extractor = FeatureExtractor()
    print("✓ FeatureExtractor initialized")

    # Get feature dimension
    dim = extractor.get_feature_dimension()
    print(f"✓ Feature dimension: {dim}")

    # Create a test image
    test_image = Image.new("RGB", (300, 400), color="blue")

    # Extract features
    features = extractor.extract(test_image)
    print(f"✓ Extracted features shape: {features.shape}")
    print(f"✓ Feature vector norm: {np.linalg.norm(features):.4f}")

    # Verify shape
    assert features.shape == (1280,), "Incorrect feature shape"
    print("✓ Feature shape verification passed")

    # Verify L2 normalization (norm should be ~1.0)
    norm = np.linalg.norm(features)
    assert 0.99 <= norm <= 1.01, f"Feature vector not normalized: {norm}"
    print("✓ L2 normalization verification passed")

    # Test batch extraction
    test_images = [Image.new("RGB", (300, 400), color=c) for c in ["red", "green"]]
    batch_features = extractor.extract_batch(test_images)
    print(f"✓ Batch features shape: {batch_features.shape}")

    assert batch_features.shape == (2, 1280), "Incorrect batch feature shape"
    print("✓ Batch feature shape verification passed")

    return extractor


def main():
    """Run all tests"""
    print("=" * 60)
    print("MobileNetV2 Model Loading and Feature Extraction Test")
    print("=" * 60)

    try:
        # Test ModelLoader
        loader = test_model_loader()

        # Test ImagePreprocessor
        preprocessor = test_image_preprocessor()

        # Test FeatureExtractor
        extractor = test_feature_extractor()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nModel is ready for use:")
        print(f"  - Feature dimension: {extractor.get_feature_dimension()}")
        print("  - Input size: 224x224x3")
        print("  - Normalization: [-1, 1]")
        print("  - Output: L2-normalized 1280-dim vector")

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
