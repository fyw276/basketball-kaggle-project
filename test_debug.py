import sys
import subprocess
import os
import tempfile
from PIL import Image
import time

env = dict(os.environ)
env["CATVTON_PATH"] = r"D:\models\CatVTON_full"
env["HF_HOME"] = r"D:\hf-cache"
env["HF_ENDPOINT"] = "https://hf-mirror.com"
env["PYTHONUNBUFFERED"] = "1"
env["PYTHONIOENCODING"] = "utf-8"

# Create test images with actual content
fd_person, person_path = tempfile.mkstemp(suffix=".jpg")
fd_garment, garment_path = tempfile.mkstemp(suffix=".jpg")
fd_output, output_path = tempfile.mkstemp(suffix=".jpg")
fd_debug, debug_dir = tempfile.mkstemp(suffix="", dir=os.path.dirname(person_path))

# Create person image - red gradient background
person_img = Image.new("RGB", (512, 768), color=(255, 100, 100))
# Add some features to simulate a person
from PIL import ImageDraw

draw = ImageDraw.Draw(person_img)
draw.rectangle([200, 200, 300, 300], fill=(255, 200, 180))  # Head
draw.rectangle([180, 300, 320, 500], fill=(100, 100, 200))  # Upper body

# Create garment image - blue
garment_img = Image.new("RGB", (300, 400), color=(50, 100, 200))

os.close(fd_person)
os.close(fd_garment)
os.close(fd_output)
os.close(fd_debug)

person_img.save(person_path, quality=95)
garment_img.save(garment_path, quality=95)

# Remove the debug file (it's a directory path now)
debug_path = debug_dir + "_debug"
os.unlink(debug_dir)

runner_path = r"D:\Users\omen\OneDrive\桌面\clothing-assistant\vton_inference_service\catvton_runner.py"

# Use preprocess_only first to see intermediate outputs
cmd = [
    sys.executable,
    runner_path,
    "--person",
    person_path,
    "--garment",
    garment_path,
    "--output",
    output_path,
    "--type",
    "upper",
    "--width",
    "512",
    "--height",
    "768",
    "--steps",
    "1",
    "--catvton-path",
    r"D:\models\CatVTON_full",
    "--debug-dir",
    debug_path,
    "--preprocess-only",
]

print("Running preprocess-only test to see intermediate outputs...")

result = subprocess.run(
    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=120
)

print("Return code:", result.returncode)
stdout = result.stdout.decode("utf-8", errors="replace")
stderr = result.stderr.decode("utf-8", errors="replace")

print("STDOUT:")
for line in stdout.split("\n")[:30]:
    if line.strip():
        print("  ", line)

# List debug directory
print()
print("Debug directory contents:")
if os.path.exists(debug_path):
    for f in os.listdir(debug_path):
        fpath = os.path.join(debug_path, f)
        size = os.path.getsize(fpath)
        print("  {} ({} bytes)".format(f, size))
else:
    print("  DEBUG DIR NOT CREATED!")

# Check if mask overlay exists
mask_overlay_path = os.path.join(debug_path, "09_mask_overlay.jpg")
if os.path.exists(mask_overlay_path):
    print()
    print("Mask overlay image analysis:")
    from PIL import Image

    img = Image.open(mask_overlay_path)
    import numpy as np

    arr = np.array(img)
    white_ratio = np.mean(arr > 128) * 100
    print(f"  Size: {img.size}")
    print(f"  White pixel ratio: {white_ratio:.2f}%")
    print(f"  (White = garment area, Black = preserved area)")

os.unlink(person_path)
os.unlink(garment_path)
