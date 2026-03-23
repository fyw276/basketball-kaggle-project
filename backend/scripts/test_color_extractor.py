"""
Test script for color extraction module
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ml.color_extractor import ColorExtractor


def create_test_image(color_rgb: tuple, size: tuple = (100, 100)) -> Image.Image:
    """Create a solid color test image"""
    img_array = np.full((size[0], size[1], 3), color_rgb, dtype=np.uint8)
    return Image.fromarray(img_array)


def test_color_extraction():
    """Test color extraction with various colors"""
    extractor = ColorExtractor(n_colors=3)

    # Test cases: (RGB, Expected Color Name)
    test_cases = [
        ((255, 0, 0), "红"),  # Red
        ((255, 165, 0), "橙"),  # Orange
        ((255, 255, 0), "黄"),  # Yellow
        ((0, 255, 0), "绿"),  # Green
        ((0, 0, 255), "蓝"),  # Blue
        ((128, 0, 128), "紫"),  # Purple
        ((0, 0, 0), "黑"),  # Black
        ((255, 255, 255), "白"),  # White
        ((128, 128, 128), "灰"),  # Gray
        ((139, 69, 19), "棕"),  # Brown
    ]

    print("Testing Color Extraction:")
    print("=" * 60)

    for rgb, expected_name in test_cases:
        # Create test image
        test_img = create_test_image(rgb)

        # Extract main color
        main_color = extractor.get_main_color(test_img)

        # Display results
        print(f"\nTest RGB: {rgb}")
        print(f"Expected: {expected_name}")
        print(f"Detected: {main_color.name}")
        print(f"RGB: {main_color.rgb}")
        print(f"HSV: {tuple(round(x, 2) for x in main_color.hsv)}")
        print(f"Hex: {main_color.hex_code}")

        # Check if correct
        status = "✓ PASS" if main_color.name == expected_name else "✗ FAIL"
        print(f"Status: {status}")

    print("\n" + "=" * 60)
    print("Color extraction test completed!")


def test_rgb_to_hsv():
    """Test RGB to HSV conversion"""
    extractor = ColorExtractor()

    print("\nTesting RGB to HSV Conversion:")
    print("=" * 60)

    test_cases = [
        ((255, 0, 0), (0, 100, 100)),  # Red
        ((0, 255, 0), (120, 100, 100)),  # Green
        ((0, 0, 255), (240, 100, 100)),  # Blue
        ((255, 255, 255), (0, 0, 100)),  # White
        ((0, 0, 0), (0, 0, 0)),  # Black
    ]

    for rgb, expected_hsv in test_cases:
        hsv = extractor.rgb_to_hsv(rgb)
        print(f"\nRGB: {rgb}")
        print(f"Expected HSV: {expected_hsv}")
        print(f"Actual HSV: {tuple(round(x, 2) for x in hsv)}")


def test_rgb_to_hex():
    """Test RGB to hex conversion"""
    extractor = ColorExtractor()

    print("\nTesting RGB to Hex Conversion:")
    print("=" * 60)

    test_cases = [
        ((255, 0, 0), "#ff0000"),  # Red
        ((0, 255, 0), "#00ff00"),  # Green
        ((0, 0, 255), "#0000ff"),  # Blue
        ((255, 255, 255), "#ffffff"),  # White
        ((0, 0, 0), "#000000"),  # Black
    ]

    for rgb, expected_hex in test_cases:
        hex_code = extractor.rgb_to_hex(rgb)
        print(f"\nRGB: {rgb}")
        print(f"Expected Hex: {expected_hex}")
        print(f"Actual Hex: {hex_code}")
        status = "✓ PASS" if hex_code == expected_hex else "✗ FAIL"
        print(f"Status: {status}")


if __name__ == "__main__":
    print("Color Extractor Test Suite")
    print("=" * 60)

    try:
        test_color_extraction()
        test_rgb_to_hsv()
        test_rgb_to_hex()

        print("\n" + "=" * 60)
        print("All tests completed successfully!")

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
