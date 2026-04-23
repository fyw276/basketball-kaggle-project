"""
Verify latest warp result color quality.
"""

from pathlib import Path

import numpy as np
from PIL import Image

result_dir = Path(
    "D:/Users/omen/OneDrive/桌面/clothing-assistant/backend/uploads/cb27466e-157d-47c7-8280-63915e062577/tryon_v2"
)
result_files = sorted(
    result_dir.glob("result_*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True
)

print(f"=== Latest Warp Results ===")
for f in result_files[:5]:
    img = Image.open(f).convert("RGB")
    arr = np.array(img)
    h, w = arr.shape[:2]

    # Check chest area (upper body garment region)
    chest = arr[int(h * 0.15) : int(h * 0.40), int(w * 0.20) : int(w * 0.80)]
    chest_mean = chest.mean(axis=(0, 1))

    # Check overall brightness
    overall_mean = arr.mean(axis=(0, 1))

    print(f"\n{f.name} ({f.stat().st_size//1024}KB)")
    print(f"  Size: {img.size}")
    print(f"  Chest area mean RGB: [{chest_mean[0]:.1f}, {chest_mean[1]:.1f}, {chest_mean[2]:.1f}]")
    print(
        f"  Overall mean RGB: [{overall_mean[0]:.1f}, {overall_mean[1]:.1f}, {overall_mean[2]:.1f}]"
    )

    if chest_mean.mean() > 50:
        print(f"  STATUS: Garment colors OK")
    else:
        print(f"  STATUS: Garment too dark")
