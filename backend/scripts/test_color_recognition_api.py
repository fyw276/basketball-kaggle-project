"""
Test script for color recognition API endpoint
"""

import sys
from io import BytesIO
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def create_test_image(color_rgb: tuple, size: tuple = (200, 200)) -> bytes:
    """Create a solid color test image and return as bytes"""
    img_array = np.full((size[0], size[1], 3), color_rgb, dtype=np.uint8)
    img = Image.fromarray(img_array)

    # Convert to bytes
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer.getvalue()


async def test_color_recognition_endpoint():
    """Test the color recognition API endpoint"""
    base_url = "http://localhost:8000"
    endpoint = f"{base_url}/api/v1/recognition/colors"

    # Test cases: (RGB, Expected Color Name)
    test_cases = [
        ((255, 0, 0), "红"),  # Red
        ((0, 0, 255), "蓝"),  # Blue
        ((0, 255, 0), "绿"),  # Green
        ((255, 255, 0), "黄"),  # Yellow
        ((0, 0, 0), "黑"),  # Black
        ((255, 255, 255), "白"),  # White
    ]

    print("Testing Color Recognition API Endpoint")
    print("=" * 60)
    print(f"Endpoint: {endpoint}")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for rgb, expected_name in test_cases:
            print(f"Testing RGB: {rgb} (Expected: {expected_name})")

            # Create test image
            image_bytes = create_test_image(rgb)

            # Prepare multipart form data
            files = {"file": ("test.jpg", image_bytes, "image/jpeg")}

            try:
                # Send POST request
                response = await client.post(endpoint, files=files)

                if response.status_code == 200:
                    result = response.json()
                    main_color = result["main_color"]

                    print(f"  ✓ Status: {response.status_code}")
                    print(f"  Main Color: {main_color['name']}")
                    print(f"  RGB: {main_color['rgb']}")
                    print(f"  HSV: {main_color['hsv']}")
                    print(f"  Hex: {main_color['hex_code']}")

                    # Check if correct
                    if main_color["name"] == expected_name:
                        print("  ✓ PASS: Color correctly identified")
                    else:
                        print(f"  ✗ FAIL: Expected {expected_name}, got {main_color['name']}")

                    # Show secondary colors if any
                    if result.get("secondary_colors"):
                        print(
                            f"  Secondary Colors: {[c['name'] for c in result['secondary_colors']]}"
                        )

                else:
                    print(f"  ✗ FAIL: Status {response.status_code}")
                    print(f"  Error: {response.text}")

            except Exception as e:
                print(f"  ✗ ERROR: {e}")

            print()

    print("=" * 60)
    print("Color recognition API test completed!")


if __name__ == "__main__":
    import asyncio

    print("Starting color recognition API test...")
    print("Make sure the FastAPI server is running on http://localhost:8000")
    print()

    try:
        asyncio.run(test_color_recognition_endpoint())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
