"""
Test script for StyleClassifier
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.ml.style_classifier import StyleClassifier


def test_style_classifier():
    """Test style classifier functionality"""
    print("=" * 60)
    print("Testing StyleClassifier")
    print("=" * 60)

    # Initialize classifier
    print("\n1. Initializing StyleClassifier...")
    classifier = StyleClassifier(threshold=0.3)
    print(f"   ✓ Classifier initialized with threshold={classifier.get_threshold()}")

    # Test get_style_tags
    print("\n2. Testing get_style_tags()...")
    style_tags = classifier.get_style_tags()
    print(f"   ✓ Available style tags ({len(style_tags)}):")
    for i, tag in enumerate(style_tags, 1):
        print(f"      {i}. {tag}")

    # Test with sample image (create a simple test image)
    print("\n3. Testing classify_style() with synthetic image...")
    try:
        import numpy as np
        from PIL import Image

        # Create a simple test image (224x224 RGB)
        test_image = Image.fromarray(np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8))

        # Classify style
        styles = classifier.classify_style(test_image)
        print(f"   ✓ Classified styles: {styles}")

        # Classify with scores
        style_scores = classifier.classify_style_with_scores(test_image)
        print("   ✓ Style scores:")
        for tag, score in sorted(style_scores.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"      {tag}: {score:.3f}")

    except Exception as e:
        print(f"   ✗ Error during classification: {e}")
        import traceback

        traceback.print_exc()

    # Test threshold adjustment
    print("\n4. Testing threshold adjustment...")
    try:
        classifier.set_threshold(0.5)
        print(f"   ✓ Threshold updated to {classifier.get_threshold()}")

        # Test with new threshold
        styles_high_threshold = classifier.classify_style(test_image)
        print(f"   ✓ Styles with threshold=0.5: {styles_high_threshold}")

    except Exception as e:
        print(f"   ✗ Error during threshold test: {e}")

    # Test invalid threshold
    print("\n5. Testing invalid threshold handling...")
    try:
        classifier.set_threshold(1.5)
        print("   ✗ Should have raised ValueError")
    except ValueError as e:
        print(f"   ✓ Correctly raised ValueError: {e}")

    print("\n" + "=" * 60)
    print("StyleClassifier tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_style_classifier()
