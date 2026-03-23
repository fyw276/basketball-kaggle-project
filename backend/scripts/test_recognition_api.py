"""
Test script for recognition API endpoint
"""

import sys
from io import BytesIO
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


def create_test_image(size=(224, 224)):
    """Create a test image"""
    img_array = np.random.randint(0, 255, (size[0], size[1], 3), dtype=np.uint8)
    img = Image.fromarray(img_array, "RGB")

    # Convert to bytes
    img_bytes = BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)

    return img_bytes


def main():
    print("=" * 60)
    print("Recognition API Test")
    print("=" * 60)
    print()

    try:
        # Test health endpoint
        print("=== Testing Health Endpoint ===")
        response = client.get("/health")
        assert response.status_code == 200
        print(f"✓ Health check passed: {response.json()}")
        print()

        # Test get categories endpoint
        print("=== Testing GET /api/v1/recognition/categories ===")
        response = client.get("/api/v1/recognition/categories")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Categories retrieved: {data['count']} categories")
        print(f"  Categories: {', '.join(data['categories'])}")
        print()

        # Test category recognition endpoint
        print("=== Testing POST /api/v1/recognition/category ===")
        test_image = create_test_image()

        response = client.post(
            "/api/v1/recognition/category",
            files={"file": ("test.jpg", test_image, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()

        print("✓ Category recognition successful:")
        print(f"  - Category: {data['category']}")
        print(f"  - Confidence: {data['confidence']:.4f}")
        print(f"  - Confidence Level: {data['confidence_level']}")
        print()

        # Test with invalid file type
        print("=== Testing Invalid File Type ===")
        response = client.post(
            "/api/v1/recognition/category",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )

        assert response.status_code == 400
        print(f"✓ Invalid file type rejected: {response.json()['detail']}")
        print()

        print("=" * 60)
        print("✓ ALL API TESTS PASSED!")
        print("=" * 60)

    except AssertionError as e:
        print(f"✗ Test assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
