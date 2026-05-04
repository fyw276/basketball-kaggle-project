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

    # 定义要检查的文件及其描述（序号与 catvton_runner.py save_debug_image() 一致）
    files_to_check = {
        "01_input_person.jpg": "原始人物图（输入）",
        "02_input_garment.jpg": "原始衣服图（输入）",
        "03_mask.png": "衣服遮罩 ★ 关键 ★",
        "04_pose_keypoints.jpg": "人体姿态关键点图",
        "09_mask_overlay.png": "遮罩叠加人物图（白=AI编辑区，黑=保留区）",
        "06_person_resized.jpg": "缩放后人物图",
        "07_garment_resized.jpg": "缩放后衣服图",
        "08_mask_resized.png": "缩放后遮罩",
        "10_result_raw.jpg": "CatVTON 扩散原始输出",
        "11_result_final.jpg": "CatVTON 最终结果（羽化重绘后）",
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

                # 对 mask 进行特殊分析（03_mask.png 和 08_mask_resized.png）
                if filename in ("03_mask.png", "08_mask_resized.png"):
                    # 分析 mask 的特点
                    if img.mode == "L":
                        unique_vals = len(np.unique(arr))
                        white_ratio = (arr > 200).sum() / arr.size
                        black_ratio = (arr < 50).sum() / arr.size
                        mid_ratio = 1.0 - white_ratio - black_ratio

                        print(f"  - 唯一值数量: {unique_vals}")
                        print(f"  - 白色比例 (>200): {white_ratio:.2%}")
                        print(f"  - 灰色比例 (50-200): {mid_ratio:.2%}")
                        print(f"  - 黑色比例 (<50): {black_ratio:.2%}")

                        # 判断 mask 质量
                        if white_ratio < 0.05:
                            print(f"  [ERROR] 白色区域太少 (<5%)，mask 没有正确覆盖衣服！")
                            print(
                                f"           原因：MediaPipe 分割失败 / rembg 崩溃 / 人物图片质量差"
                            )
                            print(
                                f"           建议：检查 01_input_person.jpg 和 04_pose_keypoints.jpg"
                            )
                        elif white_ratio > 0.7:
                            print(f"  [ERROR] 白色区域过多 (>70%)，mask 覆盖范围过大！")
                            print(f"           原因：mask 可能覆盖了整个图像或背景区域")
                        elif unique_vals == 2:
                            print(f"  [OK] mask 为纯二值图，质量良好")
                        elif unique_vals > 2 and unique_vals < 10:
                            print(f"  [WARN] mask 有 {unique_vals} 个唯一值，有轻微羽化但仍可接受")
                        else:
                            print(
                                f"  [WARN] mask 有 {unique_vals} 个唯一值，灰度值过多，边缘可能模糊"
                            )

                        analysis_results[filename] = {
                            "unique_vals": unique_vals,
                            "white_ratio": white_ratio,
                            "black_ratio": black_ratio,
                        }
                    else:
                        print(f"  - 格式: RGB (应该是灰度 L 模式)")

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
        print(
            f"[Mask 诊断] 03_mask.png 白色比例: {mask_info['white_ratio']:.1%}, 二值性: {mask_info['unique_vals']} 值"
        )
        if mask_info["white_ratio"] < 0.05:
            print()
            print("[ERROR] 衣服遮罩(03_mask.png)白色区域太少 (<5%)")
            print("  原因: MediaPipe 人体分割失败 / rembg 崩溃 / 人物图质量问题")
            print("  诊断步骤:")
            print("  1. 检查 01_input_person.jpg — 人物是否正面、全身、背景简单？")
            print("  2. 检查 04_pose_keypoints.jpg — 关键点是否准确？")
            print("  3. 检查 02_input_garment.jpg — 衣服图是否清晰？")
            print()
        elif mask_info["white_ratio"] > 0.7:
            print()
            print("[ERROR] 衣服遮罩(03_mask.png)白色区域过多 (>70%)")
            print("  原因: mask 覆盖范围过大，可能包含背景")
            print()
        else:
            print("[OK] 衣服遮罩 03_mask.png 质量正常")

    # 检查 CatVTON 输出
    existing_files = {f.name for f in debug_path.iterdir()}
    if "10_result_raw.jpg" in existing_files:
        print()
        print("[INFO] CatVTON 扩散推理已完成（10_result_raw.jpg 存在）")
        if "11_result_final.jpg" not in existing_files:
            print("[WARN] 11_result_final.jpg 不存在，可能是 repaint 步骤失败")
    else:
        print()
        print("[ERROR] 10_result_raw.jpg 不存在 — CatVTON 推理阶段失败")
        print("  原因: GPU OOM / CUDA 错误 / 模型加载失败")
        print("  建议:")
        print("  1. 开启低显存模式: CATVTON_LOW_VRAM_MODE=true")
        print("  2. 强制 fp16: CATVTON_FORCE_FP16=true")
        print("  3. 减少推理步数: CATVTON_STEPS=30")
        print('  4. 检查 CUDA: python -c "import torch; print(torch.cuda.is_available())"')

    print()
    print("=" * 60)
    print("快速修复建议（按优先级）")
    print("=" * 60)
    print()
    print("1. [最重要] 检查 03_mask.png 的白色区域是否覆盖了正确的衣服位置")
    print("   白色=将被AI编辑的区域。如果位置错误，调整衣服类型参数。")
    print()
    print("2. 如果 03_mask.png 白色区域太少:")
    print("   - 使用纯色背景的人物图（白墙/单色背景）")
    print("   - 确保人物为正面全身照")
    print("   - 确保衣服与背景颜色对比明显")
    print()
    print("3. 如果 CatVTON 推理失败 (10_result_raw.jpg 不存在):")
    print("   - 开启低显存模式: CATVTON_LOW_VRAM_MODE=true")
    print("   - 强制 fp16: CATVTON_FORCE_FP16=true")
    print("   - 减少步数: CATVTON_STEPS=30")
    print('   - 检查 CUDA: python -c "import torch; print(torch.cuda.is_available())"')
    print()
    print("4. 如果结果质量差但推理成功:")
    print("   - 降低 guidance: CATVTON_GUIDANCE=2.5 (默认 3.5)")
    print("   - 增加步数: CATVTON_STEPS=80")
    print("   - 检查 09_mask_overlay.png 遮罩是否正确")


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
