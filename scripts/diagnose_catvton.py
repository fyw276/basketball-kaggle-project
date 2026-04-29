"""
CatVTON Diagnostic Tool
Check mask and intermediate results to help diagnose quality issues
"""

import sys
from pathlib import Path
from PIL import Image
import numpy as np

def diagnose_session(debug_dir: str):
    """Diagnose a CatVTON debug session"""
    debug_path = Path(debug_dir)

    print(f"\n{'='*60}")
    print(f"Diagnosing session: {debug_path.name}")
    print(f"{'='*60}\n")

    files = {
        "person_input": "01_input_person.jpg",
        "garment_input": "02_input_garment.jpg",
        "mask": "03_mask.png",
        "pose": "04_pose_keypoints.jpg",
        "mask_overlay": "05_mask_overlay.png",
        "person_resized": "06_person_resized.jpg",
        "garment_resized": "07_garment_resized.jpg",
        "result_raw": "09_result_raw.jpg",
        "result_final": "10_result_final.jpg",
    }

    found = {}
    for key, filename in files.items():
        filepath = debug_path / filename
        if filepath.exists():
            found[key] = filepath
            print(f"[OK] {filename}")
        else:
            print(f"[MISSING] {filename}")

    print()

    # Analyze mask
    if "mask" in found:
        mask_path = found["mask"]
        mask_img = Image.open(mask_path).convert("L")
        mask_arr = np.array(mask_img)

        total_pixels = mask_arr.size
        mask_pixels = (mask_arr > 127).sum()
        mask_ratio = mask_pixels / total_pixels

        print(f"Mask Analysis:")
        print(f"  - Size: {mask_img.size}")
        print(f"  - Mask Coverage: {mask_ratio:.1%}")

        if mask_ratio < 0.05:
            print(f"  [WARNING] Coverage too low, mask may not be generated correctly")
        elif mask_ratio > 0.5:
            print(f"  [WARNING] Coverage too high, mask may cover the entire image")
        else:
            print(f"  [OK] Coverage is normal")

        # Check person size
        if "person_input" in found:
            person_img = Image.open(found["person_input"])
            person_size = person_img.size
            print(f"\nPerson image:")
            print(f"  - Size: {person_size}")
            orient = "Portrait" if person_size[1] > person_size[0] else "Landscape"
            print(f"  - Orientation: {orient}")

        # Check garment
        if "garment_input" in found:
            garment_img = Image.open(found["garment_input"])
            garment_size = garment_img.size
            print(f"\nGarment image:")
            print(f"  - Size: {garment_size}")
            is_square = "Yes" if garment_size[0] == garment_size[1] else "No"
            print(f"  - Is square: {is_square}")

        # Check CatVTON output
        if "result_raw" in found:
            result_img = Image.open(found["result_raw"])
            result_size = result_img.size
            print(f"\nCatVTON Raw Output:")
            print(f"  - Size: {result_size}")

            if "person_input" in found:
                person_size = Image.open(found["person_input"]).size
                if result_size == (768, 1024):
                    print(f"  - CatVTON output is fixed size 768x1024")
                    print(f"  - Original person size: {person_size}")
                    if person_size[0] != 768 or person_size[1] != 1024:
                        print(f"  [WARNING] Size mismatch, post-processing needs size adjustment")

    print("\n" + "="*60)
    print("Diagnosis Conclusion and Suggestions")
    print("="*60)

    issues = []

    if "garment_input" in found:
        garment = Image.open(found["garment_input"])
        garment_arr = np.array(garment)
        gray = garment_arr.mean(axis=2)
        white_pixels = (gray > 240).sum()
        white_ratio = white_pixels / gray.size
        if white_ratio < 0.3:
            issues.append("Garment image has low white background ratio, suggest using PNG with white background")

    if "mask_overlay" in found:
        overlay = Image.open(found["mask_overlay"])
        print("\nMask Overlay Check:")
        print(f"  - Size: {overlay.size}")
        print(f"  - Action: Manually check 05_mask_overlay.png to confirm green mask covers the upper body area correctly")

    if issues:
        print("\nIssues found:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("\nNo obvious issues found. Poor results may be due to:")
        print("  1. CatVTON model limitations")
        print("  2. Generated garment has slight deformation or color difference")
        print("  3. Try adjusting steps or guidance parameters")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        debug_dir = sys.argv[1]
    else:
        debug_base = Path(r"D:\models\catvton_debug")
        if debug_base.exists():
            dirs = sorted(debug_base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
            if dirs:
                debug_dir = str(dirs[0])
            else:
                print("[DEBUG] No debug directory found")
                sys.exit(1)
        else:
            print(f"[DEBUG] Debug directory does not exist: {debug_base}")
            sys.exit(1)

    diagnose_session(debug_dir)
