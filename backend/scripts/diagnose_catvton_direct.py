"""
CatVTON 端到端诊断 - 直接导入测试（不用子进程）
测试 CatVTON Pipeline 能否正常加载和推理
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

print("=" * 60)
print("CatVTON 直接诊断")
print("=" * 60)
print(f"CatVTON_PATH: {CATVTON_PATH}")
print(f"sys.path[0]: {sys.path[0]}")
print()

# Step 1: Check paths
print("[STEP 1] 检查路径...")
paths_to_check = [
    Path(CATVTON_PATH) / "model" / "pipeline.py",
    Path(CATVTON_PATH) / "mix-48k-1024" / "attention" / "model.safetensors",
    Path(CATVTON_PATH) / "SCHP" / "exp-schp-201908301523-atr.pth",
    Path(CATVTON_PATH) / "DensePose" / "model_final_162be9.pkl",
    Path(CATVTON_PATH) / "utils.py",
]
for p in paths_to_check:
    exists = p.exists()
    size = p.stat().st_size if exists else 0
    print(f"  {'OK' if exists else 'MISSING'}: {p.name} ({size/1024/1024:.1f}MB)")

print()

# Step 2: Import CatVTON pipeline
print("[STEP 2] 导入 CatVTON Pipeline...")
try:
    from utils import init_weight_dtype, resize_and_crop, resize_and_padding

    print("  OK: utils imported")
except ImportError as e:
    print(f"  FAIL: utils import failed: {e}")
    sys.exit(1)

try:
    from model.pipeline import CatVTONPipeline

    print("  OK: CatVTONPipeline imported")
except ImportError as e:
    print(f"  FAIL: CatVTONPipeline import failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()

# Step 3: Initialize pipeline
print("[STEP 3] 初始化 CatVTON Pipeline (FP16 + VAE slicing)...")
import torch

print(f"  CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  GPU: {torch.cuda.get_device_name(0)}")
    props = torch.cuda.get_device_properties(0)
    print(f"  VRAM total: {props.total_memory / 1024**3:.1f} GB")

    # Check current memory usage
    try:
        allocated = torch.cuda.memory_allocated(0) / 1024**3
        reserved = torch.cuda.memory_reserved(0) / 1024**3
        print(f"  VRAM allocated: {allocated:.2f} GB")
        print(f"  VRAM reserved: {reserved:.2f} GB")
        print(f"  VRAM free (approx): {props.total_memory / 1024**3 - reserved:.2f} GB")
    except Exception as e:
        print(f"  VRAM check failed: {e}")

try:
    weight_dtype = init_weight_dtype("fp16")
    print(f"  weight_dtype: {weight_dtype}")

    # 检查 xformers
    has_xformers = False
    try:
        import xformers

        has_xformers = True
        print(f"  xformers: {xformers.__version__} (可用)")
    except ImportError:
        print(f"  xformers: 未安装 (将使用 PyTorch SDPA)")

    start = time.time()
    # 关键：传入 attention_slicing="auto" 和 enable_xformers 启用显存优化
    pipeline = CatVTONPipeline(
        base_ckpt="runwayml/stable-diffusion-inpainting",
        attn_ckpt=CATVTON_PATH,
        attn_ckpt_version="mix",
        weight_dtype=weight_dtype,
        use_tf32=True,
        device="cuda",
        skip_safety_check=True,  # 跳过安全检查器，节省显存
        attention_slicing="auto",  # 关键：启用 UNet attention slicing
        enable_xformers=has_xformers,  # 关键：启用 xformers 高效注意力
    )
    print(f"  OK: Pipeline loaded in {time.time()-start:.1f}s")
except Exception as e:
    print(f"  FAIL: Pipeline init failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Apply VAE slicing (check if it was applied)
print()
print("[STEP 4] 检查显存优化...")
try:
    # Check attention slicing
    if hasattr(pipeline.unet, "config"):
        print(
            f"  UNet config attention slicing: {getattr(pipeline.unet.config, 'attention_slicing', 'N/A')}"
        )
    # Check xformers
    print(f"  xformers enabled: {has_xformers}")
    # Check VRAM
    allocated = torch.cuda.memory_allocated(0) / 1024**3
    reserved = torch.cuda.memory_reserved(0) / 1024**3
    print(f"  VRAM allocated: {allocated:.2f} GB")
    print(f"  VRAM reserved: {reserved:.2f} GB")
except Exception as e:
    print(f"  VRAM check failed: {e}")

print()

# Step 5: Test inference
print("[STEP 5] 测试推理（低分辨率 512x768, 10步）...")
import numpy as np
from PIL import Image, ImageDraw

# 生成简单测试图片
person = Image.new("RGB", (512, 768), (180, 185, 195))
draw = ImageDraw.Draw(person)
draw.ellipse([250, 60, 310, 130], fill=(230, 200, 180))
draw.rectangle([220, 140, 350, 500], fill=(100, 100, 120))
draw.rectangle([220, 500, 270, 720], fill=(80, 80, 100))
draw.rectangle([300, 500, 350, 720], fill=(80, 80, 100))

garment = Image.new("RGB", (512, 768), (255, 255, 255))
draw2 = ImageDraw.Draw(garment)
draw2.rectangle([100, 50, 400, 650], fill=(200, 30, 30))

# 缩放
person_resized = resize_and_crop(person, (512, 768))
garment_resized = resize_and_padding(garment, (512, 768))
mask = Image.new("L", (512, 768), 0)
draw3 = ImageDraw.Draw(mask)
draw3.rectangle([100, 50, 400, 650], fill=255)

print(f"  person_resized: {person_resized.size}")
print(f"  garment_resized: {garment_resized.size}")
print(f"  mask: {mask.size}, sum={np.array(mask).sum()}")

try:
    start = time.time()
    result = pipeline(
        person_resized,
        garment_resized,
        mask,
        num_inference_steps=10,
        guidance_scale=2.5,
        seed=42,
    )
    elapsed = time.time() - start
    print(f"  OK: 推理完成 in {elapsed:.1f}s")
    print(f"  result type: {type(result)}")
    if hasattr(result, "images"):
        print(f"  result.images: {len(result.images)} image(s)")
        if result.images:
            print(f"  first image: {result.images[0].size}")
            result.images[0].save(r"D:\models\catvton_test_result.jpg", quality=95)
            print(f"  结果已保存: D:\\models\\catvton_test_result.jpg")
    elif isinstance(result, Image.Image):
        print(f"  result size: {result.size}")
        result.save(r"D:\models\catvton_test_result.jpg", quality=95)
        print(f"  结果已保存: D:\\models\\catvton_test_result.jpg")
except Exception as e:
    print(f"  FAIL: 推理失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 60)
print("诊断完成！")
print("=" * 60)
