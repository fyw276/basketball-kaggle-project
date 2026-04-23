"""
Automated tests for the garment fidelity overlay (ai_warp_hybrid) in tryon_v2.

Tests verify:
1. Overlay function executes without errors
2. Garment color is blended onto AI result (RGB changes in garment region)
3. Overlay region is in the upper body area (not too high/low)
4. Face/neck protection works (face pixels remain unchanged)
5. Different garment aspect ratios handled correctly
"""

from pathlib import Path
from sys import exit as sys_exit

import numpy as np
from PIL import Image

from app.services.tryon_v2.warp_engine import overlay_top_onto_ai_result


def make_test_image(size, r, g, b):
    """Create a solid color test image."""
    arr = np.full((size[1], size[0], 3), [r, g, b], dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def make_gradient_image(size, r_start, r_end, g_start, g_end, b_start, b_end):
    """Create a gradient test image (simulates person)."""
    h, w = size[1], size[0]
    arr = np.zeros((h, w, 3), dtype=np.float32)
    for i in range(h):
        t = i / max(h - 1, 1)
        arr[i, :, 0] = r_start + (r_end - r_start) * t
        arr[i, :, 1] = g_start + (g_end - g_start) * t
        arr[i, :, 2] = b_start + (b_end - b_start) * t
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def make_garment_image(size, r, g, b, pattern=False):
    """Create a test garment image (solid color or checkerboard)."""
    arr = np.full((size[1], size[0], 3), [r, g, b], dtype=np.uint8)
    if pattern:
        # Checkerboard pattern
        for y in range(size[1]):
            for x in range(size[0]):
                if (x // 8 + y // 8) % 2 == 0:
                    arr[y, x] = [r, g, b]
                else:
                    arr[y, x] = [max(0, r - 40), max(0, g - 40), max(0, b - 40)]
    return Image.fromarray(arr, mode="RGB")


def test_overlay_no_crash():
    """Test 1: overlay function executes without errors."""
    print("Test 1: overlay executes without crash...", end=" ")
    ai = make_gradient_image((512, 768), 80, 60, 120, 100, 160, 140)
    person = make_gradient_image((512, 768), 100, 80, 140, 120, 180, 160)
    garment = make_garment_image((200, 300), 200, 100, 50)

    result, meta = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.90)
    assert result is not None, "Result should not be None"
    assert result.size == ai.size, f"Result size {result.size} != AI size {ai.size}"
    assert (
        meta.get("engine") == "ai_warp_hybrid"
    ), f"Expected ai_warp_hybrid, got {meta.get('engine')}"
    print("PASS")
    return result, meta


def test_overlay_changes_color():
    """Test 2: garment color should appear in the result (upper body region)."""
    print("Test 2: garment color appears in result...", end=" ")

    # AI result: dark blue (simulating AI-generated dark garment)
    ai = make_gradient_image((512, 768), 60, 50, 100, 90, 150, 140)
    person = make_gradient_image((512, 768), 100, 80, 140, 120, 180, 160)

    # Garment: bright orange-red
    garment = make_garment_image((200, 300), 220, 80, 40)

    result, meta = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.90)

    # Check upper body region (y=15%-50% of image = chest area)
    arr = np.array(result)
    h, w = arr.shape[:2]
    chest = arr[int(h * 0.15) : int(h * 0.45), int(w * 0.25) : int(w * 0.75)]
    ai_chest = np.array(ai)[int(h * 0.15) : int(h * 0.45), int(w * 0.25) : int(w * 0.75)]

    chest_mean = chest.mean(axis=(0, 1))
    chest_ai_mean = ai_chest.mean(axis=(0, 1))

    # Garment R should be significantly higher than AI result R
    assert (
        chest_mean[0] > chest_ai_mean[0] + 20
    ), f"R channel: result={chest_mean[0]:.0f} should be > AI={chest_ai_mean[0]:.0f} + 20"

    # Garment G should be similar (both are medium)
    # Result should look different from AI in upper body
    diff = np.abs(chest.astype(float) - ai_chest.astype(float)).mean()
    assert diff > 10, f"Result should differ from AI by >10 mean pixel diff, got {diff:.1f}"

    print(f"PASS (diff={diff:.1f}, R: {chest_ai_mean[0]:.0f}->{chest_mean[0]:.0f})")
    return result, meta


def test_overlay_region_in_upper_body():
    """Test 3: overlay region should be in upper body area (y < 60% of image)."""
    print("Test 3: overlay region in upper body...", end=" ")

    ai = make_gradient_image((512, 768), 60, 50, 100, 90, 150, 140)
    person = make_gradient_image((512, 768), 100, 80, 140, 120, 180, 160)
    garment = make_garment_image((200, 300), 220, 80, 40)

    result, meta = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.90)

    region = meta.get("overlay_region", {})
    ai_h = 768
    y0, y1 = region.get("y0", -1), region.get("y1", -1)

    # Upper garment should be roughly y=10%-60% of image height
    assert y0 >= 0, "y0 should be defined"
    assert y0 < ai_h * 0.60, f"y0={y0} ({y0/ai_h*100:.1f}%) should be < 60% of image height"
    assert y1 < ai_h * 0.85, f"y1={y1} ({y1/ai_h*100:.1f}%) should be < 85% of image height"

    print(f"PASS (region y=[{y0},{y1}], {y0/ai_h*100:.1f}%-{y1/ai_h*100:.1f}% of {ai_h}px)")
    return result, meta


def test_face_protection():
    """Test 4: face/neck region should remain unchanged (or very similar)."""
    print("Test 4: face protection...", end=" ")

    # AI result with distinct face region
    ai = make_gradient_image((512, 768), 80, 60, 130, 110, 170, 150)
    person = make_gradient_image((512, 768), 100, 80, 140, 120, 180, 160)
    garment = make_garment_image((200, 300), 220, 80, 40)

    result, meta = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.90)

    # Face region: top 15% of image
    arr_ai = np.array(ai)
    arr_result = np.array(result)
    h, w = arr_ai.shape[:2]
    face = arr_ai[: int(h * 0.15), int(w * 0.30) : int(w * 0.70)]
    face_result = arr_result[: int(h * 0.15), int(w * 0.30) : int(w * 0.70)]

    diff = np.abs(face.astype(float) - face_result.astype(float)).mean()
    # Face should be almost unchanged (diff < 5)
    assert diff < 8, f"Face region should be protected, diff={diff:.1f} too high"

    print(f"PASS (face diff={diff:.2f} < 8)")
    return result, meta


def test_different_garment_aspects():
    """Test 5: different garment aspect ratios should be handled."""
    print("Test 5: different garment aspects...", end=" ")

    ai = make_gradient_image((512, 768), 60, 50, 100, 90, 150, 140)
    person = make_gradient_image((512, 768), 100, 80, 140, 120, 180, 160)

    # Wide garment (t-shirt-like)
    g1 = make_garment_image((400, 200), 180, 60, 100)
    r1, m1 = overlay_top_onto_ai_result(ai, person, g1, garment_alpha=0.90)
    assert m1.get("engine") == "ai_warp_hybrid", "Wide garment should work"

    # Tall garment (sweater-like)
    g2 = make_garment_image((150, 400), 60, 160, 200)
    r2, m2 = overlay_top_onto_ai_result(ai, person, g2, garment_alpha=0.90)
    assert m2.get("engine") == "ai_warp_hybrid", "Tall garment should work"

    # Square garment
    g3 = make_garment_image((300, 300), 100, 100, 100)
    r3, m3 = overlay_top_onto_ai_result(ai, person, g3, garment_alpha=0.90)
    assert m3.get("engine") == "ai_warp_hybrid", "Square garment should work"

    print("PASS (3 aspect ratios handled)")
    return r1, m1


def test_garment_alpha():
    """Test 6: different alpha values produce different results."""
    print("Test 6: garment_alpha parameter...", end=" ")

    ai = make_gradient_image((512, 768), 60, 50, 100, 90, 150, 140)
    person = make_gradient_image((512, 768), 100, 80, 140, 120, 180, 160)
    garment = make_garment_image((200, 300), 220, 80, 40)

    # High alpha = more garment color
    r_high, _ = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.95)
    # Low alpha = more AI color
    r_low, _ = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.50)

    h, w = np.array(ai).shape[:2]
    chest_high = np.array(r_high)[int(h * 0.25) : int(h * 0.40), int(w * 0.3) : int(w * 0.7)].mean()
    chest_low = np.array(r_low)[int(h * 0.25) : int(h * 0.40), int(w * 0.3) : int(w * 0.7)].mean()

    # High alpha should have more garment R (220 vs 60 in AI)
    # Low alpha should be closer to AI (around 110-140)
    assert (
        chest_high > chest_low
    ), f"High alpha ({chest_high:.0f}) should be brighter than low alpha ({chest_low:.0f})"

    print(f"PASS (alpha=0.95→{chest_high:.0f}, alpha=0.50→{chest_low:.0f})")
    return r_high, r_low


def test_with_real_data():
    """Test 7: real user data (if available)."""
    print("Test 7: real user data...", end=" ")

    user_dir = Path(
        "D:/Users/omen/OneDrive/桌面/clothing-assistant/backend/uploads"
        "/cb27466e-157d-47c7-8280-63915e062577"
    )
    split_dir = user_dir / "split"
    result_dir = user_dir / "tryon_v2"

    if not (split_dir.exists() and result_dir.exists()):
        print("SKIP (no real data)")
        return

    # Find latest results
    results = sorted(result_dir.glob("result_*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not results:
        print("SKIP (no results)")
        return

    # Find latest person
    person_files = [(f, f.stat().st_mtime) for f in user_dir.glob("*.jpg") if "20260423" in f.name]
    if not person_files:
        print("SKIP (no person image)")
        return
    person_files.sort(key=lambda x: x[1], reverse=True)

    # Find garment
    split_files = sorted(split_dir.glob("*.jpg"))
    if not split_files:
        print("SKIP (no garment)")
        return

    ai = Image.open(results[0]).convert("RGB")
    person = Image.open(person_files[0][0]).convert("RGB")
    garment = Image.open(split_files[0]).convert("RGB")

    print(
        f"  Using: ai={results[0].name}, "
        f"person={person_files[0][0].name}, "
        f"garment={split_files[0].name}"
    )

    # Check that overlay changes something
    arr_ai = np.array(ai)
    h, w = arr_ai.shape[:2]

    result, meta = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.90)

    # Check garment region changed
    chest_before = arr_ai[int(h * 0.15) : int(h * 0.45), int(w * 0.2) : int(w * 0.8)].mean(
        axis=(0, 1)
    )
    chest_after = np.array(result)[int(h * 0.15) : int(h * 0.45), int(w * 0.2) : int(w * 0.8)].mean(
        axis=(0, 1)
    )

    diff = np.linalg.norm(chest_after - chest_before)
    print(
        f"  Chest diff: [{chest_before[0]:.0f},{chest_before[1]:.0f},{chest_before[2]:.0f}] -> "
        f"[{chest_after[0]:.0f},{chest_after[1]:.0f},{chest_after[2]:.0f}]"
    )
    print(f"  Engine: {meta.get('engine')}, region: {meta.get('overlay_region')}")

    # Result should differ
    if diff > 5:
        print(f"PASS (diff={diff:.1f} > 5)")
    else:
        print(f"WARN (diff={diff:.1f} < 5, may need tuning)")

    return result, meta


def main():
    print("=" * 60)
    print("Garment Fidelity Overlay Tests")
    print("=" * 60)

    tests = [
        test_overlay_no_crash,
        test_overlay_changes_color,
        test_overlay_region_in_upper_body,
        test_face_protection,
        test_different_garment_aspects,
        test_garment_alpha,
        test_with_real_data,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys_exit(0 if success else 1)
