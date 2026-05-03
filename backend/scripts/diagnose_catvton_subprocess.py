"""
CatVTON 子进程诊断 - FP16 低显存模式 (无编码参数)
"""

import io
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

CATVTON_PATH = r"D:\models\CatVTON_full"
HF_HOME = r"D:\hf-cache"
HF_ENDPOINT = "https://hf-mirror.com"
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
DEBUG_DIR = r"D:\models\catvton_debug_subprocess_fp16"

print("=" * 60)
print("CatVTON 诊断 (FP16 低显存模式)")
print("=" * 60)

from PIL import Image, ImageDraw

person = Image.new("RGB", (768, 1024), (180, 185, 195))
draw = ImageDraw.Draw(person)
draw.ellipse([350, 80, 430, 180], fill=(230, 200, 180))
draw.rectangle([320, 200, 450, 600], fill=(100, 100, 120))
draw.rectangle([320, 600, 380, 950], fill=(80, 80, 100))
draw.rectangle([390, 600, 450, 950], fill=(80, 80, 100))

garment = Image.new("RGB", (768, 1024), (255, 255, 255))
draw2 = ImageDraw.Draw(garment)
draw2.rectangle([150, 100, 600, 800], fill=(200, 30, 30))

fd_person, person_path = tempfile.mkstemp(suffix=".jpg")
fd_garment, garment_path = tempfile.mkstemp(suffix=".jpg")
fd_output, output_path = tempfile.mkstemp(suffix=".jpg")
os.close(fd_person)
os.close(fd_garment)
os.close(fd_output)

person.save(person_path, format="JPEG", quality=95)
garment.save(garment_path, format="JPEG", quality=95)

runner_path = WORKSPACE_ROOT / "vton_inference_service" / "catvton_runner.py"

cmd = [
    sys.executable,
    str(runner_path),
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
    "20",
    "--guidance",
    "3.5",
    "--force-fp16",
    "--vae-slicing",
    "--xformers",
    "--catvton-path",
    CATVTON_PATH,
    "--debug-dir",
    DEBUG_DIR,
]

print(f"Command: {' '.join(cmd)}")

env = dict(os.environ)
env["HF_HOME"] = HF_HOME
env["HF_ENDPOINT"] = HF_ENDPOINT
env["PYTHONUNBUFFERED"] = "1"

print("Starting CatVTON subprocess...")
start = time.time()

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=str(WORKSPACE_ROOT),
    env=env,
)


def read_stream(stream, prefix):
    try:
        for line in iter(stream.readline, b""):
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            with threading.Lock():
                print(f"  [{prefix}] {text}")
    except Exception as e:
        print(f"  [{prefix}] error: {e}")


lock = threading.Lock()
t_out = threading.Thread(target=read_stream, args=(proc.stdout, "OUT"), daemon=True)
t_err = threading.Thread(target=read_stream, args=(proc.stderr, "ERR"), daemon=True)
t_out.start()
t_err.start()

try:
    returncode = proc.wait(timeout=300)
except subprocess.TimeoutExpired:
    print("TIMEOUT - killing process")
    proc.kill()
    returncode = -1

elapsed = time.time() - start
t_out.join(timeout=5)
t_err.join(timeout=5)

print(f"\nDone: returncode={returncode}, elapsed={elapsed:.1f}s")

print("\n-- Output file --")
print(f"exists: {os.path.exists(output_path)}")
if os.path.exists(output_path):
    size = os.path.getsize(output_path)
    print(f"size: {size} bytes")
    if size > 0:
        img = Image.open(output_path)
        print(f"  Image: {img.size}, mode={img.mode}")

print("\n-- Debug dir --")
if os.path.exists(DEBUG_DIR):
    for root, dirs, files in os.walk(DEBUG_DIR):
        for f in sorted(files):
            fpath = os.path.join(root, f)
            print(f"  {os.path.basename(fpath)} ({os.path.getsize(fpath)} bytes)")
else:
    print(f"  Not found: {DEBUG_DIR}")

try:
    os.unlink(person_path)
    os.unlink(garment_path)
    print(f"\nOutput: {output_path}")
except Exception:
    pass
