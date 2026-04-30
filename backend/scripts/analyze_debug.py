"""
CatVTON 调试图片分析工具

检查 CatVTON 生成的中间产物，分析效果差的原因
"""

import os
from pathlib import Path

import numpy as np
from PIL import Image


def analyze_debug_session(debug_dir: str):
    """分析一个调试会话目录"""
    debug_path = Path(debug_dir)

    if not debug_path.exists():
        print(f"目录不存在: {debug_dir}")
        return

    print(f"\n{'='*60}")
    print(f"分析调试目录: {debug_dir}")
    print(f"{'='*60}\n")

    # 定义要检查的文件及其描述
    files_to_check = {
        "01_input_person.jpg": "原始人物图",
        "02_input_garment.jpg": "原始衣服图",
        "03_mask.png": "衣服遮罩（关键！）",
        "04_pose_keypoints.jpg": "人体姿态关键点",
        "05_mask_overlay.png": "遮罩叠加图",
        "06_person_resized.jpg": "缩放后人物图",
        "07_garment_resized.jpg": "缩放后衣服图",
        "08_mask_resized.png": "缩放后遮罩",
        "09_result_raw.jpg": "CatVTON原始输出",
        "10_result_final.jpg": "最终结果（羽化后）",
    }

    analysis_results = {}

    for filename, description in files_to_check.items():
        filepath = debug_path / filename
        if filepath.exists():
            try:
                img = Image.open(filepath)
                arr = np.array(img)

                print(f"✓ {filename}: {description}")
                print(f"  - 大小: {img.size}")
                print(f"  - 模式: {img.mode}")

                # 对 mask 进行特殊分析
                if filename.endswith(".png") and filename.startswith(("03", "08")):
                    # 分析 mask 的特点
                    if img.mode == "L":
                        unique_vals = len(np.unique(arr))
                        white_ratio = (arr > 200).sum() / arr.size
                        black_ratio = (arr < 50).sum() / arr.size

                        print(f"  - 唯一值数量: {unique_vals}")
                        print(f"  - 白色比例: {white_ratio:.2%}")
                        print(f"  - 黑色比例: {black_ratio:.2%}")

                        # 判断 mask 质量
                        if white_ratio < 0.05:
                            print(f"  ⚠ 警告: 白色区域太少，mask 可能没有正确覆盖衣服！")
                        elif white_ratio > 0.5:
                            print(f"  ⚠ 警告: 白色区域太多，mask 可能覆盖了整个图像！")

                        analysis_results[filename] = {
                            "unique_vals": unique_vals,
                            "white_ratio": white_ratio,
                            "black_ratio": black_ratio,
                        }
                    else:
                        print(f"  - 格式: RGB (需要是灰度)")

                print()

            except Exception as e:
                print(f"✗ {filename}: 读取失败 - {e}\n")
        else:
            print(f"- {filename}: 不存在\n")

    # 总结分析
    print(f"\n{'='*60}")
    print("问题诊断")
    print(f"{'='*60}\n")

    # 检查 mask 质量
    if "03_mask.png" in analysis_results:
        mask_info = analysis_results["03_mask.png"]
        if mask_info["white_ratio"] < 0.05:
            print("❌ 问题: 衣服遮罩(03_mask.png)白色区域太少")
            print("   原因: MediaPipe 人体分割失败，mask 生成不正确")
            print("   解决: ")
            print("   1. 确保人物图是全身正面照")
            print("   2. 确保背景尽量简单（纯色背景最佳）")
            print("   3. 确保人物穿着紧身或合身的衣服（容易分割）")
        elif mask_info["white_ratio"] > 0.5:
            print("❌ 问题: 衣服遮罩(03_mask.png)白色区域太多")
            print("   原因: mask 覆盖范围过大，可能包含了背景")
        else:
            print("✓ 衣服遮罩看起来正常")

    print("\n通用优化建议:")
    print("1. 使用纯白背景的人物照片（如果可能）")
    print("2. 使用纯白背景的衣服商品图")
    print("3. 确保衣服颜色与背景有足够对比度")
    print("4. 深色衣服可能需要调整 guidance_scale 参数（降低到 2.5）")


def find_latest_debug_session(base_dir: str = r"D:\models\catvton_debug") -> str | None:
    """查找最新的调试会话"""
    base_path = Path(base_dir)
    if not base_path.exists():
        return None

    sessions = [d for d in base_path.iterdir() if d.is_dir()]
    if not sessions:
        return None

    # 按修改时间排序
    sessions.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(sessions[0])


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        debug_dir = sys.argv[1]
    else:
        # 自动查找最新的调试目录
        debug_dir = find_latest_debug_session()
        if debug_dir:
            print(f"找到最新的调试目录: {debug_dir}")
        else:
            print("未找到调试目录，请手动指定路径")
            print("用法: python analyze_debug.py <调试目录路径>")
            sys.exit(1)

    analyze_debug_session(debug_dir)
