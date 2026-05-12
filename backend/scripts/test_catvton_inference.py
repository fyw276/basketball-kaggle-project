"""
CatVTON 推理诊断脚本
测试 CatVTON 是否正确工作
"""

import os
import sys
import tempfile

import numpy as np
from PIL import Image

# 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HOME"] = "D:/hf-cache"
os.environ["CATVTON_PATH"] = "D:/models/CatVTON_full"

# 添加项目路径
sys.path.insert(0, "D:/Users/omen/OneDrive/桌面/clothing-assistant/backend")
sys.path.insert(0, "D:/models/CatVTON_full")

print("=" * 60)
print("CatVTON 推理诊断")
print("=" * 60)

# 1. 加载 CatVTON Pipeline
print("\n[1] 加载 CatVTON Pipeline...")
try:
    import torch
    from model.pipeline import CatVTONPipeline

    print("    CatVTONPipeline 导入成功")

    # 检查 CUDA
    print(f"    CUDA 可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"    GPU: {torch.cuda.get_device_name(0)}")
        print(f"    显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    # 加载 Pipeline
    print("\n    加载模型 (这可能需要几分钟)...")
    pipeline = CatVTONPipeline(
        base_ckpt="runwayml/stable-diffusion-inpainting",
        attn_ckpt="D:/models/CatVTON_full",
        attn_ckpt_version="mix",
        weight_dtype=torch.float16,
        device="cuda",
        skip_safety_check=True,
        attention_slicing="auto",
        enable_xformers=False,
    )
    print("    [OK] Pipeline 加载成功")

except Exception as e:
    print(f"    [ERROR] 加载失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 2. 创建简单测试图像
print("\n[2] 创建测试图像...")

# 创建人物图像（简单渐变）
person = np.zeros((512, 768, 3), dtype=np.uint8)
for i in range(512):
    person[i, :] = [int(128 + i * 0.5), int(100 + i * 0.3), int(80 + i * 0.2)]
person_img = Image.fromarray(person)

# 创建衣服图像（红色方块）
garment = np.full((512, 768, 3), 255, dtype=np.uint8)
garment[100:400, 300:500] = [255, 0, 0]  # 红色方块
garment_img = Image.fromarray(garment)

# 创建遮罩（上部白色 = 要替换的区域）
mask = np.zeros((512, 768), dtype=np.uint8)
mask[0:256, :] = 255  # 上半部分是衣服区域

print(f"    人物图: {person_img.size}")
print(f"    衣服图: {garment_img.size}")
print(f"    遮罩: {mask.shape}, 白色像素: {(mask > 200).sum()}")

# 3. 运行推理
print("\n[3] 运行 CatVTON 推理...")
try:
    import torch
    from diffusers.utils.torch_utils import randn_tensor

    with torch.no_grad():
        result = pipeline(
            image=person_img,
            condition_image=garment_img,
            mask=Image.fromarray(mask),
            num_inference_steps=10,  # 快速测试用 10 步
            guidance_scale=1.0,
            height=512,
            width=768,
        )

    result_img = result[0]
    print(f"    [OK] 推理完成")
    print(f"    输出尺寸: {result_img.size}")

    # 4. 分析结果
    print("\n[4] 分析推理结果...")
    result_arr = np.array(result_img)
    person_arr = np.array(person_img)

    print(f"    输出 mean: {result_arr.mean():.2f}, std: {result_arr.std():.2f}")
    print(f"    输入 mean: {person_arr.mean():.2f}, std: {person_arr.std():.2f}")

    # 检查是否有红色（衣服颜色）
    red_channel = result_arr[:, :, 0]
    red_ratio = (red_channel > 200).sum() / red_channel.size
    print(f"    红色像素比例: {red_ratio:.2%}")

    if red_ratio > 0.1:
        print("    [OK] 检测到红色衣服，CatVTON 工作正常")
    else:
        print("    [!] 未检测到明显红色，可能有问题")

    # 计算相似度
    diff = np.abs(result_arr.astype(float) - person_arr.astype(float)).mean()
    print(f"    与输入相似度: {100 * (1 - diff/255):.1f}%")

    if diff < 5:
        print("    [!] 严重: 输出与输入几乎相同，CatVTON 未正常工作")

    # 5. 保存结果
    print("\n[5] 保存测试结果...")
    output_dir = "D:/Users/omen/OneDrive/桌面/clothing-assistant/debug_output/catvton_test"
    os.makedirs(output_dir, exist_ok=True)

    person_img.save(os.path.join(output_dir, "test_person.jpg"))
    garment_img.save(os.path.join(output_dir, "test_garment.jpg"))
    Image.fromarray(mask).save(os.path.join(output_dir, "test_mask.png"))
    result_img.save(os.path.join(output_dir, "test_result.jpg"))

    print(f"    结果保存到: {output_dir}")

except Exception as e:
    print(f"    [ERROR] 推理失败: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
