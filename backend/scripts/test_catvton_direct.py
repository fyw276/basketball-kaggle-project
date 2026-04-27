"""Direct CatVTON test with proper encoding."""

import os
import subprocess
import sys

os.environ["HF_HOME"] = r"D:\hf-cache"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

cmd = [
    sys.executable,
    r"D:\Users\omen\OneDrive\桌面\clothing-assistant\vton_inference_service\catvton_runner.py",
    "--catvton-path",
    r"D:\models\CatVTON",
    "--person",
    r"D:\Users\omen\OneDrive\桌面\clothing-assistant\data\test_person.jpg",
    "--garment",
    r"D:\Users\omen\OneDrive\桌面\clothing-assistant\data\test_garment.jpg",
    "--output",
    r"D:\models\catvton_debug\direct_test_output.jpg",
    "--type",
    "upper",
    "--width",
    "768",
    "--height",
    "1024",
    "--steps",
    "10",
    "--guidance",
    "3.5",
    "--precision",
    "fp16",
    "--no-vae-slicing",
    "--no-xformers",
    "--debug-dir",
    r"D:\models\catvton_debug\direct_test2",
    "--preprocess-only",
]

print("Running CatVTON subprocess directly...")

result = subprocess.run(
    cmd,
    capture_output=True,
    encoding="utf-8",
    errors="replace",
    timeout=120,
    env={k: v for k, v in os.environ.items()},
)

print(f"Return code: {result.returncode}")
print(f"\nSTDOUT:\n{result.stdout}")
print(f"\nSTDERR:\n{result.stderr[:2000]}")

# Check files
import glob

pattern = r"D:\models\catvton_debug\direct_test2\*"
sessions = glob.glob(pattern)
print(f"\nDebug sessions: {sessions}")
for s in sessions:
    files = os.listdir(s)
    print(f"  Session: {os.path.basename(s)}, files: {len(files)}")
    for f in sorted(files)[:20]:
        fp = os.path.join(s, f)
        sz = os.path.getsize(fp) // 1024
        print(f"    {f} ({sz}KB)")
