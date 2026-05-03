"""
CatVTON 显存优化测试脚本
测试 512x768 和 768x1024 的推理显存占用和速度
"""

import os
import sys
import time
from pathlib import Path

CATVTON_PATH = r"D:\models\CatVTON_full"
HF_HOME = r"D:\hf-cache"
HF_ENDPOINT = "https://hf-mirror.com"
os.environ["HF_HOME"] = HF_HOME
os.environ["HF_ENDPOINT"] = HF_ENDPOINT

sys.path.insert(0, CATVTON_PATH)

import torch
from model.pipeline import CatVTONPipeline
from PIL import Image, ImageDraw
from utils import init_weight_dtype, resize_and_crop, resize_and_padding


def make_test_images():
    person = Image.new("RGB", (768, 1024), (180, 185, 195))
    draw = ImageDraw.Draw(person)
    draw.ellipse([350, 80, 430, 180], fill=(230, 200, 180))
    draw.rectangle([320, 200, 450, 600], fill=(100, 100, 120))
    draw.rectangle([320, 600, 380, 950], fill=(80, 80, 100))
    draw.rectangle([390, 600, 450, 950], fill=(80, 80, 100))

    garment = Image.new("RGB", (768, 1024), (255, 255, 255))
    draw2 = ImageDraw.Draw(garment)
    draw2.rectangle([150, 100, 600, 800], fill=(200, 30, 30))
    return person, garment


person, garment = make_test_images()

# Check xformers
has_xformers = False
try:
    import xformers

    has_xformers = True
    print(f"xformers: {xformers.__version__}")
except ImportError:
    print("xformers: NOT installed (will use PyTorch SDPA)")

# Check PyTorch version and CUDA
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    props = torch.cuda.get_device_properties(0)
    print(f"VRAM total: {props.total_memory / 1024**3:.1f} GB")

# Initialize pipeline once (FP16 + attention slicing + skip safety)
print("\n初始化 CatVTON Pipeline...")
start_init = time.time()
pipeline = CatVTONPipeline(
    base_ckpt="runwayml/stable-diffusion-inpainting",
    attn_ckpt=CATVTON_PATH,
    attn_ckpt_version="mix",
    weight_dtype=torch.float16,
    use_tf32=True,
    device="cuda",
    skip_safety_check=True,
    attention_slicing="auto",
    enable_xformers=has_xformers,
)
print(f"Pipeline 加载时间: {time.time()-start_init:.1f}s")

# Check VRAM after init
allocated = torch.cuda.memory_allocated(0) / 1024**3
reserved = torch.cuda.memory_reserved(0) / 1024**3
print(f"Pipeline 加载后 VRAM: allocated={allocated:.2f}GB, reserved={reserved:.2f}GB")

# Test 1: 512x768, 20 steps
print("\n" + "=" * 60)
print("测试 1: 512x768, 20步")
print("=" * 60)

person_512 = resize_and_crop(person, (512, 768))
garment_512 = resize_and_padding(garment, (512, 768))
mask_512 = Image.new("L", (512, 768), 0)
draw3 = ImageDraw.Draw(mask_512)
draw3.rectangle([100, 50, 400, 650], fill=255)

torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()

start = time.time()
result = pipeline(
    person_512, garment_512, mask_512, num_inference_steps=20, guidance_scale=3.5, seed=42
)
elapsed = time.time() - start

peak_vram = torch.cuda.max_memory_allocated(0) / 1024**3
print(f"推理时间: {elapsed:.1f}s ({elapsed/20:.1f}s/step)")
print(f"峰值 VRAM: {peak_vram:.2f}GB")
print(f"结果数量: {len(result)}")
if result:
    img = result[0] if isinstance(result, list) else result
    print(f"结果尺寸: {img.size}")
    img.save(r"D:\models\catvton_test_512x768.jpg", quality=95)
    print(f"已保存: D:\\models\\catvton_test_512x768.jpg")

# Cleanup
del result
torch.cuda.empty_cache()

# Test 2: 768x1024, 20 steps
print("\n" + "=" * 60)
print("测试 2: 768x1024, 20步 (检查是否 OOM)")
print("=" * 60)

person_768 = resize_and_crop(person, (768, 1024))
garment_768 = resize_and_padding(garment, (768, 1024))
mask_768 = Image.new("L", (768, 1024), 0)
draw4 = ImageDraw.Draw(mask_768)
draw4.rectangle([150, 50, 620, 850], fill=255)

torch.cuda.reset_peak_memory_stats()

start = time.time()
try:
    result = pipeline(
        person_768, garment_768, mask_768, num_inference_steps=20, guidance_scale=3.5, seed=42
    )
    elapsed = time.time() - start
    peak_vram = torch.cuda.max_memory_allocated(0) / 1024**3
    print(f"推理时间: {elapsed:.1f}s ({elapsed/20:.1f}s/step)")
    print(f"峰值 VRAM: {peak_vram:.2f}GB")
    print(f"结果数量: {len(result)}")
    if result:
        img = result[0] if isinstance(result, list) else result
        print(f"结果尺寸: {img.size}")
        img.save(r"D:\models\catvton_test_768x1024.jpg", quality=95)
        print(f"已保存: D:\\models\\catvton_test_768x1024.jpg")
except RuntimeError as e:
    if "out of memory" in str(e):
        print(f"OOM! 768x1024 在 8GB 卡上显存不足")
        peak_vram = torch.cuda.max_memory_allocated(0) / 1024**3
        print(f"峰值 VRAM: {peak_vram:.2f}GB")
        print("建议: 降低分辨率或减少步数")
    else:
        print(f"错误: {e}")

print("\n测试完成!")
