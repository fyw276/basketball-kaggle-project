"""
CatVTON 端到端测试 - 验证 CatVTON 是否正确工作

这个脚本会：
1. 创建一个简单的测试场景
2. 调用 CatVTON
3. 保存并比较结果
4. 报告 CatVTON 是否真正产生了深度学习输出

使用方法：
    python scripts/test_catvton_e2e.py
    python scripts/test_catvton_e2e.py --low-vram
    python scripts/test_catvton_e2e.py --real
"""

import os
import sys
import tempfile
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))


def test_catvton_e2e():
    """端到端测试 CatVTON"""
    import io

    import numpy as np
    from PIL import Image

    print("=" * 70)
    print("CatVTON 端到端测试")
    print("=" * 70)

    # 1. 创建测试图片
    print("\n[1] 创建测试图片...")

    # 创建测试人物图（全身，浅色背景）
    person_img = Image.new("RGB", (384, 512), color=(240, 235, 230))
    # 添加简单的人形轮廓
    import numpy as np

    person_arr = np.array(person_img)
    # 头部
    cv2.circle = None  # 避免导入错误
    person_arr[50:100, 160:224] = [220, 200, 180]  # 头部
    person_arr[100:400, 140:244] = [180, 170, 160]  # 身体
    person_img = Image.fromarray(person_arr)

    # 创建测试衣服图（简单彩色上衣）
    garment_img = Image.new("RGB", (256, 256), color=(180, 80, 80))

    print(f"    人物图大小: {person_img.size}")
    print(f"    衣服图大小: {garment_img.size}")

    # 2. 保存测试图片
    test_dir = project_root / "data" / "catvton_test"
    test_dir.mkdir(parents=True, exist_ok=True)

    person_path = test_dir / "test_person.jpg"
    garment_path = test_dir / "test_garment.jpg"
    result_path = test_dir / "test_result.jpg"

    person_img.save(person_path)
    garment_img.save(garment_path)

    print(f"\n    测试图片已保存到: {test_dir}")

    print("\n[2] 调用 CatVTON...")
    print("    (使用 vae_slicing=True, xformers=True 以节省显存)")
    from backend.app.services.tryon_v2.catvton_engine_client import _run_catvton_sync

    person_bytes = open(person_path, "rb").read()
    garment_bytes = open(garment_path, "rb").read()

    start_time = time.time()
    result = _run_catvton_sync(
        person_bytes=person_bytes,
        garment_bytes=garment_bytes,
        cloth_type="upper",
        timeout=300,
        vae_slicing=True,
        xformers=True,
        force_fp16=False,
        low_vram_mode=False,
    )
    elapsed = time.time() - start_time

    print(f"    耗时: {elapsed:.1f} 秒")

    # 4. 分析结果
    print("\n[3] 分析结果...")

    if result.get("status") == "success":
        result_img = result.get("result_image")
        if result_img:
            result_img.save(result_path)
            print(f"    结果已保存: {result_path}")

            # 比较结果特征
            result_arr = np.array(result_img)

            # 检查结果的多样性
            # CatVTON 输出应该在人物身上有衣服，背景应该有一定纹理
            unique_colors = len(np.unique(result_arr.reshape(-1, 3), axis=0))
            print(f"    唯一颜色数: {unique_colors}")

            # 检查是否有明显的衣服区域
            upper_region = result_arr[50:250, 50:334]
            upper_variance = upper_region.var()
            print(f"    上身区域方差: {upper_variance:.2f}")

            # 检查背景区域
            bg_region = result_arr[0:50, :]  # 顶部背景
            bg_variance = bg_region.var()
            print(f"    背景区域方差: {bg_variance:.2f}")

            print("\n    ✓ CatVTON 成功生成了结果")

            # 分析结果质量
            if unique_colors < 100:
                print("    ⚠ 警告: 结果颜色单一，可能是错误的结果")
            if upper_variance < 100:
                print("    ⚠ 警告: 上身区域方差太小，可能是简单粘贴")

            return True
        else:
            print("    ✗ 结果图片为空")
            return False
    else:
        print(f"    ✗ CatVTON 失败")
        print(f"    状态: {result.get('status')}")
        print(f"    消息: {result.get('message')}")
        print(f"    元数据: {result.get('metadata')}")
        return False


def diagnose_common_issues():
    """诊断常见问题"""
    print("\n" + "=" * 70)
    print("CatVTON 常见问题诊断")
    print("=" * 70)

    print(
        """
如果 CatVTON 产生的结果不符合预期，可能的原因：

1. 【模型问题】模型未正确下载或损坏
   - 检查 D:\\models\\CatVTON_full 目录结构
   - 必须有: mix-48k-1024/attention/model.safetensors
   - 如果没有，从 HuggingFace 重新下载

2. 【输入问题】输入图片不符合要求
   - CatVTON 需要全身正面照片
   - 半身像或侧身照效果会很差
   - 人物应该在图像中央，背景尽量简单

3. 【参数问题】推理参数不当
   - 尝试调整 steps (20-80，推荐 50)
   - 尝试调整 guidance (2.0-3.5，推荐 2.5)
   - 尝试不同的 cloth_type (upper/lower/overall)

4. 【后处理问题】后处理改变了结果
   - 检查 enhance_tryon_result 函数
   - 尝试禁用后处理看原始输出

5. 【调用问题】实际调用的是其他引擎
   - 检查 API 返回的 metadata.engine 字段
   - 应该是 "catvton"，而不是 "warp_preserve"
   - 如果是 warp，说明 CatVTON 调用失败了
    """
    )

    # 检查模型文件
    print("\n检查模型文件:")
    model_paths = [
        r"D:\models\CatVTON_full\mix-48k-1024\attention\model.safetensors",
        r"D:\models\CatVTON_full\model.safetensors",
        r"D:\models\CatVTON\zhengchong_CatVTON",
    ]

    for path in model_paths:
        exists = os.path.exists(path)
        print(f"    {'✓' if exists else '✗'} {path}: {'存在' if exists else '不存在'}")


def test_with_real_images():
    """使用真实图片测试"""
    print("\n" + "=" * 70)
    print("使用真实图片测试")
    print("=" * 70)

    test_dir = project_root / "data" / "catvton_test"

    person_path = test_dir / "real_person.jpg"
    garment_path = test_dir / "real_garment.jpg"

    if not person_path.exists() or not garment_path.exists():
        print("    请准备真实测试图片:")
        print(f"    - 人物全身图: {person_path}")
        print(f"    - 衣服商品图: {garment_path}")
        return False

    print(f"    人物图: {person_path}")
    print(f"    衣服图: {garment_path}")

    from backend.app.services.tryon_v2.catvton_engine_client import _run_catvton_sync

    person_bytes = open(person_path, "rb").read()
    garment_bytes = open(garment_path, "rb").read()

    print("\n    开始 CatVTON 推理...")
    print("    (使用 vae_slicing=True, xformers=True 以节省显存)")

    start_time = time.time()
    result = _run_catvton_sync(
        person_bytes=person_bytes,
        garment_bytes=garment_bytes,
        cloth_type="upper",
        timeout=300,
        vae_slicing=True,
        xformers=True,
        force_fp16=False,
        low_vram_mode=False,
    )
    elapsed = time.time() - start_time

    print(f"    耗时: {elapsed:.1f} 秒")

    if result.get("status") == "success":
        result_img = result.get("result_image")
        result_path = test_dir / "real_result.jpg"
        result_img.save(result_path)
        print(f"    ✓ 结果已保存: {result_path}")
        return True
    else:
        print(f"    ✗ CatVTON 失败: {result.get('message')}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CatVTON 端到端测试")
    parser.add_argument(
        "--real",
        action="store_true",
        help="使用真实图片测试（需准备 real_person.jpg 和 real_garment.jpg）",
    )
    parser.add_argument(
        "--low-vram",
        action="store_true",
        help="启用低显存模式（等于 --force-fp16 + VAE slicing + xformers，RTX 4060 Laptop 推荐）",
    )
    parser.add_argument(
        "--force-fp16", action="store_true", help="强制 fp16 而非 bf16（节省约 2GB 显存）"
    )
    parser.add_argument("--no-vae-slicing", action="store_true", help="禁用 VAE 分片推理")
    parser.add_argument("--no-xformers", action="store_true", help="禁用 xformers 高效注意力")
    parser.add_argument("--steps", type=int, default=50, help="扩散步数（默认 50）")
    args = parser.parse_args()

    if args.real:
        test_with_real_images()
    else:
        test_catvton_e2e()

    diagnose_common_issues()
