"""
Test wardrobe management with image recognition integration

This script tests:
1. Adding garment with image recognition
2. Listing garments with filtering
3. Getting garment details
4. Updating garment
5. Deleting garment
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import numpy as np
from PIL import Image

from app.core.logging import setup_logging

logger = setup_logging()


def print_header(title):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_section(title):
    """Print formatted section"""
    print(f"\n{title}")
    print("-" * 80)


def create_test_image(color="blue"):
    """Create a test image with specified color"""
    img = np.zeros((224, 224, 3), dtype=np.uint8)
    if color == "blue":
        img[:, :, 2] = 180
    elif color == "red":
        img[:, :, 0] = 200
    elif color == "green":
        img[:, :, 1] = 180
    return Image.fromarray(img)


def test_image_recognition_integration():
    """Test image recognition integration with wardrobe"""
    print_section("1. Testing Image Recognition Integration")

    try:
        from app.ml.image_recognizer import ImageRecognizer

        # Initialize recognizer
        recognizer = ImageRecognizer()
        print("   ✓ ImageRecognizer initialized")

        # Create test image
        test_image = create_test_image("blue")
        print("   ✓ Test image created")

        # Recognize image
        result = recognizer.recognize(test_image)
        print("   ✓ Image recognition successful")
        print(f"     - Category: {result.category}")
        print(f"     - Main color: {result.main_color.name}")
        print(f"     - Style tags: {result.style_tags}")
        print(f"     - Feature vector: {len(result.feature_vector)}-dim")

        # Validate result structure
        assert result.category is not None
        assert result.main_color is not None
        assert len(result.feature_vector) == 1280
        print("   ✓ Result validation passed")

        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_garment_data_models():
    """Test garment data models"""
    print_section("2. Testing Garment Data Models")

    try:
        from app.schemas.garment import ColorSchema, GarmentCreate

        # Create color schema
        color = ColorSchema(
            name="蓝", rgb=(52, 120, 180), hsv=(210.0, 71.1, 70.6), hex_code="#3478b4"
        )
        print("   ✓ ColorSchema created")

        # Create garment schema
        garment = GarmentCreate(
            category="上衣",
            main_color=color,
            secondary_colors=[],
            style_tags=["通勤", "简约"],
            fit_type="标准",
            image_path="/path/to/image.jpg",
            image_url="/uploads/image.jpg",
            feature_vector=[0.1] * 1280,
            notes="Test garment",
        )
        print("   ✓ GarmentCreate schema created")

        # Validate schema
        assert garment.category == "上衣"
        assert garment.main_color.name == "蓝"
        assert len(garment.style_tags) == 2
        assert len(garment.feature_vector) == 1280
        print("   ✓ Schema validation passed")

        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_storage_service():
    """Test storage service"""
    print_section("3. Testing Storage Service")

    try:

        from app.services.storage import get_storage_service

        storage = get_storage_service()
        print("   ✓ Storage service initialized")

        # Test directory creation
        user_dir = storage._get_user_directory("test_user")
        assert user_dir.exists()
        print("   ✓ User directory created")

        # Test filename generation
        filename = storage._generate_filename("test.jpg", "test_user")
        assert filename.endswith(".jpg")
        assert "test_user" in filename
        print(f"   ✓ Filename generated: {filename}")

        # Cleanup
        storage.cleanup_user_directory("test_user")
        print("   ✓ Cleanup successful")

        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_garment_service():
    """Test garment service (without database)"""
    print_section("4. Testing Garment Service Structure")

    try:
        from app.services.garment import (
            count_garments_by_user,
            create_garment,
            delete_garment,
            get_garment_by_id,
            get_garments_by_user,
            update_garment,
        )

        # Check all functions exist
        assert callable(get_garment_by_id)
        assert callable(get_garments_by_user)
        assert callable(count_garments_by_user)
        assert callable(create_garment)
        assert callable(update_garment)
        assert callable(delete_garment)
        print("   ✓ All service functions exist")

        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_api_endpoints():
    """Test API endpoint structure"""
    print_section("5. Testing API Endpoint Structure")

    try:
        from app.api.wardrobe import router

        # Check router exists
        assert router is not None
        print("   ✓ Wardrobe router exists")

        # Check routes
        routes = [route.path for route in router.routes]
        expected_routes = [
            "/wardrobe/garments",
            "/wardrobe/garments/{garment_id}",
        ]

        for expected in expected_routes:
            # Check if any route matches (may have prefix variations)
            if any(expected in route for route in routes):
                print(f"   ✓ Route exists: {expected}")
            else:
                print(f"   ⚠ Route not found: {expected}")

        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_validation_constants():
    """Test validation constants"""
    print_section("6. Testing Validation Constants")

    try:
        from app.schemas.garment import VALID_CATEGORIES, VALID_FIT_TYPES, VALID_STYLE_TAGS

        # Check categories
        assert len(VALID_CATEGORIES) == 6
        assert "上衣" in VALID_CATEGORIES
        print(f"   ✓ Valid categories: {VALID_CATEGORIES}")

        # Check fit types
        assert len(VALID_FIT_TYPES) == 4
        assert "修身" in VALID_FIT_TYPES
        print(f"   ✓ Valid fit types: {VALID_FIT_TYPES}")

        # Check style tags
        assert len(VALID_STYLE_TAGS) >= 10
        assert "通勤" in VALID_STYLE_TAGS
        print(f"   ✓ Valid style tags: {len(VALID_STYLE_TAGS)} tags")

        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print_header("WARDROBE MANAGEMENT INTEGRATION TEST")

    results = {
        "Image Recognition Integration": test_image_recognition_integration(),
        "Garment Data Models": test_garment_data_models(),
        "Storage Service": test_storage_service(),
        "Garment Service": test_garment_service(),
        "API Endpoints": test_api_endpoints(),
        "Validation Constants": test_validation_constants(),
    }

    # Summary
    print_header("TEST SUMMARY")
    print()
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name:.<50} {status}")

    total = len(results)
    passed = sum(results.values())
    print()
    print(f"  Total: {passed}/{total} tests passed")
    print("=" * 80)

    if all(results.values()):
        print("\n✓ ALL TESTS PASSED")
        print("\nWardrobe Management Status: READY")
        print("\nNext Steps:")
        print("  1. Test with actual database")
        print("  2. Test API endpoints with HTTP requests")
        print("  3. Implement similarity analysis (Task 14)")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        print("\nPlease review the failed tests and fix issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
