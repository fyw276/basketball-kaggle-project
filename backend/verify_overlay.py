"""Quick verification of the overlay fix."""

import sys

sys.path.insert(0, ".")

import numpy as np
from PIL import Image

from app.services.tryon_v2.warp_engine import overlay_top_onto_ai_result

# Real data
user_dir = "D:/Users/omen/OneDrive/桌面/clothing-assistant/backend/uploads/cb27466e-157d-47c7-8280-63915e062577"
result_dir = user_dir + "/tryon_v2"
split_dir = user_dir + "/split"

import os

results = sorted(
    [f for f in os.listdir(result_dir) if f.startswith("result_")],
    key=lambda f: os.path.getmtime(os.path.join(result_dir, f)),
    reverse=True,
)
person_files = [
    (f, os.path.getsize(os.path.join(user_dir, f)))
    for f in os.listdir(user_dir)
    if "20260423" in f and f.endswith(".jpg")
]
person_files.sort(key=lambda x: x[1], reverse=True)
split_files = sorted(os.listdir(split_dir))

ai = Image.open(os.path.join(result_dir, results[0])).convert("RGB")
person = Image.open(os.path.join(user_dir, person_files[0][0])).convert("RGB")
garment = Image.open(os.path.join(split_dir, split_files[0])).convert("RGB")

ai_w, ai_h = ai.size
arr_ai = np.array(ai)

print("AI size: {}, Person: {}, Garment: {}".format(ai.size, person.size, garment.size))

# Test different alphas
r1, m1 = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.90)
r2, m2 = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=0.50)
r3, m3 = overlay_top_onto_ai_result(ai, person, garment, garment_alpha=1.0)

chest_y0, chest_y1 = int(ai_h * 0.15), int(ai_h * 0.45)
chest_x0, chest_x1 = int(ai_w * 0.25), int(ai_w * 0.75)
print("Chest region: y=[{},{}], x=[{},{}]".format(chest_y0, chest_y1, chest_x0, chest_x1))

for label, arr in [
    ("AI base", arr_ai),
    ("alpha=0.90", np.array(r1)),
    ("alpha=0.50", np.array(r2)),
    ("alpha=1.0", np.array(r3)),
]:
    chest = arr[chest_y0:chest_y1, chest_x0:chest_x1]
    mean_rgb = chest.mean(axis=(0, 1))
    print("{}: chest=[{:.0f},{:.0f},{:.0f}]".format(label, mean_rgb[0], mean_rgb[1], mean_rgb[2]))

# Save comparison images
r1.save(os.path.join(result_dir, "compare_alpha090.jpg"), quality=95)
r3.save(os.path.join(result_dir, "compare_alpha100.jpg"), quality=95)
print("Saved compare images")
print("Region info: {}".format(m1.get("overlay_region")))
print(
    "All PASS" if m1.get("engine") == "ai_warp_hybrid" else "FAIL: engine=" + str(m1.get("engine"))
)
