"""
Test script for category classifier
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from io import BytesIO

import numpy as np
from PIL import Image

from app.ml.category_classifier import CategoryClassifier


def create_test_image(size=(224, 224)):
    """Create a test image"""
    # Create random RGB image
    img_array = np.random.randint(0, 255, (size[0], size[1], 3), dtype=np.uint8)
    img = Image.fromarray(img_array, "RGB")
    return img


def main():
    print("=" * 60)
    print("Category Classifier Test")
    print("=" * 60)
    print()

    try:
        # Initialize classifier
        print("=== Initializing CategoryClassifier ===")
        classifier = CategoryClassifier()
        print("✓ CategoryClassifier initialized")
        print()

        # Get categories
        print("=== Available Categories ===")
        categories = classifier.get_categories()
        for cat_id, cat_name in categories.items():
            print(f"  {cat_id}: {cat_name}")
        print()

        # Test with a sample image
        print("=== Testing Category Classification ===")
        test_image = create_test_image()
        print(f"✓ Created test image: {test_image.size}")

        # Convert to bytes
        img_bytes = BytesIO()
        test_image.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        # Classify
        category, confidence = classifier.classify_category(img_bytes.getvalue())
        confidence_level = classifier.get_confidence_level(confidence)

        print("✓ Classification result:")
        print(f"  - Category: {category}")
        print(f"  - Confidence: {confidence:.4f}")
        print(f"  - Confidence Level: {confidence_level}")
        print()

        # Test confidence levels
        print("=== Testing Confidence Levels ===")
        test_confidences = [0.9, 0.7, 0.4]
        for conf in test_confidences:
            level = classifier.get_confidence_level(conf)
            print(f"  Confidence {conf:.1f} -> {level}")
        print()

        print("=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
