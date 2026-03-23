"""
Test script for complete image recognition pipeline
Tests the ImageRecognizer class and /api/v1/recognition/analyze endpoint
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging
from app.ml.image_recognizer import ImageRecognizer

logger = setup_logging()


def test_image_recognizer():
    """Test ImageRecognizer class with sample image"""
    print("\n" + "=" * 80)
    print("Testing ImageRecognizer Class")
    print("=" * 80)

    try:
        # Initialize recognizer
        print("\n1. Initializing ImageRecognizer...")
        recognizer = ImageRecognizer()
        print("   ✓ ImageRecognizer initialized successfully")

        # Create a simple test image (blue square)
        print("\n2. Creating test image...")
        import numpy as np
        from PIL import Image

        # Create a 224x224 blue image
        test_image = np.zeros((224, 224, 3), dtype=np.uint8)
        test_image[:, :, 2] = 180  # Blue channel
        pil_image = Image.fromarray(test_image)
        print("   ✓ Test image created (224x224 blue square)")

        # Perform recognition
        print("\n3. Performing complete recognition...")
        result = recognizer.recognize(pil_image)
        print("   ✓ Recognition completed successfully")

        # Display results
        print("\n" + "-" * 80)
        print("RECOGNITION RESULTS:")
        print("-" * 80)
        print(f"Category:            {result.category}")
        print(f"Category Confidence: {result.category_confidence:.3f}")
        print(f"Main Color:          {result.main_color.name} {result.main_color.hex_code}")
        print(f"Secondary Colors:    {[c.name for c in result.secondary_colors]}")
        print(f"Style Tags:          {result.style_tags}")
        print(f"Feature Vector:      {len(result.feature_vector)}-dimensional")
        print(f"Feature Vector Sum:  {sum(result.feature_vector):.3f}")
        print("-" * 80)

        # Validate result structure
        print("\n4. Validating result structure...")
        assert result.category in [
            "上衣",
            "裤子",
            "裙子",
            "外套",
            "鞋",
            "包",
        ], f"Invalid category: {result.category}"
        assert 0 <= result.category_confidence <= 1, "Confidence out of range"
        assert result.main_color is not None, "Main color is None"
        assert len(result.feature_vector) == 1280, "Feature vector wrong dimension"
        assert len(result.style_tags) > 0, "No style tags returned"
        print("   ✓ Result structure is valid")

        print("\n" + "=" * 80)
        print("✓ ALL TESTS PASSED")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_api_endpoint():
    """Test the /api/v1/recognition/analyze endpoint"""
    print("\n" + "=" * 80)
    print("Testing API Endpoint: POST /api/v1/recognition/analyze")
    print("=" * 80)

    try:
        from io import BytesIO

        import numpy as np
        import requests
        from PIL import Image

        # Check if server is running
        print("\n1. Checking if server is running...")
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            if response.status_code == 200:
                print("   ✓ Server is running")
            else:
                print("   ✗ Server returned non-200 status")
                return False
        except requests.exceptions.RequestException:
            print("   ✗ Server is not running")
            print("   Please start the server with: python run.py")
            return False

        # Create test image
        print("\n2. Creating test image...")
        test_image = np.zeros((224, 224, 3), dtype=np.uint8)
        test_image[:, :, 2] = 180  # Blue
        pil_image = Image.fromarray(test_image)

        # Convert to bytes
        img_bytes = BytesIO()
        pil_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        print("   ✓ Test image created")

        # Send request
        print("\n3. Sending POST request to /api/v1/recognition/analyze...")
        files = {"file": ("test.png", img_bytes, "image/png")}
        response = requests.post("http://localhost:8000/api/v1/recognition/analyze", files=files)

        if response.status_code == 200:
            print("   ✓ Request successful (200 OK)")
        else:
            print(f"   ✗ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        # Parse response
        print("\n4. Parsing response...")
        result = response.json()
        print("   ✓ Response parsed successfully")

        # Display results
        print("\n" + "-" * 80)
        print("API RESPONSE:")
        print("-" * 80)
        print(f"Category:            {result['category']}")
        print(f"Category Confidence: {result['category_confidence']:.3f}")
        print(f"Main Color:          {result['main_color']['name']}")
        print(f"Secondary Colors:    {[c['name'] for c in result['secondary_colors']]}")
        print(f"Style Tags:          {result['style_tags']}")
        print(f"Feature Vector Dim:  {len(result['feature_vector'])}")
        print("-" * 80)

        # Validate response
        print("\n5. Validating response structure...")
        assert "category" in result, "Missing category"
        assert "category_confidence" in result, "Missing category_confidence"
        assert "main_color" in result, "Missing main_color"
        assert "secondary_colors" in result, "Missing secondary_colors"
        assert "style_tags" in result, "Missing style_tags"
        assert "feature_vector" in result, "Missing feature_vector"
        assert len(result["feature_vector"]) == 1280, "Wrong feature vector dimension"
        print("   ✓ Response structure is valid")

        print("\n" + "=" * 80)
        print("✓ API TEST PASSED")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"\n✗ API TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("COMPLETE IMAGE RECOGNITION PIPELINE TEST")
    print("=" * 80)

    # Test 1: ImageRecognizer class
    test1_passed = test_image_recognizer()

    # Test 2: API endpoint
    test2_passed = test_api_endpoint()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"ImageRecognizer Class: {'✓ PASSED' if test1_passed else '✗ FAILED'}")
    print(f"API Endpoint:          {'✓ PASSED' if test2_passed else '✗ FAILED'}")
    print("=" * 80)

    if test1_passed and test2_passed:
        print("\n✓ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n✗ SOME TESTS FAILED")
        sys.exit(1)
