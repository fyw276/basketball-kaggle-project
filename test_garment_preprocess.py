import sys
import os
import numpy as np
from PIL import Image

# Add project to path
sys.path.insert(0, r"D:\Users\omen\OneDrive\桌面\clothing-assistant\backend")
sys.path.insert(0, r"D:\models\CatVTON_full")

print("=== Testing garment_preprocess ===")
print(f"Python: {sys.executable}")
print()

# Test 1: Check if rembg is available
print("[1] Testing rembg import...")
try:
    from rembg import remove

    print("    rembg: OK")
except ImportError as e:
    print(f"    rembg: FAILED - {e}")

# Test 2: Test garment_preprocess
print()
print("[2] Testing garment_preprocess...")
try:
    from app.services.garment_preprocess import preprocess_garment

    # Create a test garment image
    test_garment = Image.new("RGB", (400, 500), color=(200, 50, 50))

    result = preprocess_garment(test_garment, canvas_size=512)
    print(f"    garment_preprocess: OK")
    print(f"    Output shape: {result.shape}")
    print(f"    Output dtype: {result.dtype}")
    print(f"    Unique values: {len(np.unique(result))}")

    # Check how much of the image is non-black
    non_black_ratio = np.mean(result > 10)
    print(f"    Non-black pixel ratio: {non_black_ratio:.2%}")

    # Save for visual inspection
    result_img = Image.fromarray(result, mode="RGB")
    result_img.save(r"D:\models\catvton_debug\test_garment_preprocess.jpg", quality=95)
    print(f"    Saved to: D:\\models\\catvton_debug\\test_garment_preprocess.jpg")

except Exception as e:
    print(f"    garment_preprocess: FAILED - {e}")
    import traceback

    traceback.print_exc()

# Test 3: Test rembg directly
print()
print("[3] Testing rembg directly...")
try:
    from rembg import remove
    from io import BytesIO

    test_garment = Image.new("RGB", (400, 500), color=(200, 50, 50))
    result = remove(test_garment)

    if isinstance(result, Image.Image):
        print(f"    rembg remove: OK")
        print(f"    Output mode: {result.mode}")
        print(f"    Output size: {result.size}")

        # Check alpha channel
        if result.mode == "RGBA":
            alpha = np.array(result.split()[3])
            white_pixels = np.mean(alpha > 128)
            print(f"    Alpha white ratio: {white_pixels:.2%}")
    else:
        print(f"    rembg remove: returned {type(result)}")

except Exception as e:
    print(f"    rembg remove: FAILED - {e}")
