"""
诊断 CatVTON 效果差的具体原因

分析调试目录中的所有图片，找出导致效果不好的原因
"""

import os
from pathlib import Path

import numpy as np
from PIL import Image


def analyze_debug_session(debug_dir: str):
    """详细分析一个调试会话目录"""
    debug_path = Path(debug_dir)

    if not debug_path.exists():
        print(f"目录不存在: {debug_dir}")
        return

    print(f"\n{'='*60}")
    print(f"详细分析: {debug_path.name}")
    print(f"{'='*60}\n")

    # 加载所有关键图片
    images = {}
    for f in debug_path.glob("*.*"):
        try:
            img = Image.open(f)
            images[f.name] = {
                "path": f,
                "size": img.size,
                "mode": img.mode,
                "arr": np.array(img) if img.mode in ("L", "RGB", "RGBA") else None,
            }
        except:
            pass

    # 1. 检查人物图
    person_orig = images.get("01_input_person.jpg", {})
    if person_orig:
        w, h = person_orig["size"]
        ratio = w / h
        print(f"1. 原始人物图: {w}x{h}, 宽高比={ratio:.3f}")
        if 0.72 <= ratio <= 0.78:
            print("   ✓ 宽高比正常 (接近 3:4)")
        else:
            print(f"   ⚠ 宽高比异常！期望 0.75 (3:4)，实际 {ratio:.3f}")
            print("   原因: 图片宽高比不正确会导致 resize 变形")
        print()

    # 2. 检查衣服图
    garment_orig = images.get("02_input_garment.jpg", {})
    if garment_orig:
        w, h = garment_orig["size"]
        ratio = w / h
        print(f"2. 原始衣服图: {w}x{h}, 宽高比={ratio:.3f}")
        if 0.8 <= ratio <= 1.2:
            print("   ✓ 衣服图宽高比正常")
        else:
            print(f"   ⚠ 衣服图宽高比异常！")
        print()

    # 3. 检查 Mask
    mask = images.get("03_mask.png", {})
    if mask and mask["arr"] is not None:
        arr = mask["arr"]
        if len(arr.shape) == 3:
            arr = arr[..., 0]  # 取第一个通道

        unique = len(np.unique(arr))
        white = (arr > 200).sum()
        black = (arr < 50).sum()
        total = arr.size
        white_ratio = white / total
        black_ratio = black / total

        print(f"3. 衣服遮罩 (03_mask.png):")
        print(f"   大小: {mask['size']}")
        print(f"   唯一值数量: {unique}")
        print(f"   白色(>200)比例: {white_ratio:.1%}")
        print(f"   黑色(<50)比例: {black_ratio:.1%}")

        if white_ratio < 0.02:
            print("   ❌ 问题: 白色区域极少！mask 没有正确覆盖衣服")
        elif white_ratio < 0.05:
            print("   ⚠ 警告: 白色区域偏少，可能覆盖不完整")
        elif white_ratio > 0.4:
            print("   ⚠ 警告: 白色区域过多，可能包含了背景")
        else:
            print("   ✓ Mask 覆盖比例正常")
        print()

    # 4. 检查缩放后的图片
    person_resized = images.get("06_person_resized.jpg", {})
    if person_resized:
        w, h = person_resized["size"]
        print(f"4. 缩放后人物图: {w}x{h}")
        if w == 768 and h == 1024:
            print("   ✓ 大小正确")
        else:
            print(f"   ⚠ 大小不正确！期望 768x1024，实际 {w}x{h}")
        print()

    mask_resized = images.get("08_mask_resized.png", {})
    if mask_resized:
        w, h = mask_resized["size"]
        print(f"5. 缩放后遮罩: {w}x{h}")
        if w == 768 and h == 1024:
            print("   ✓ 大小正确")
        else:
            print(f"   ⚠ 大小不正确！")
        print()

    # 6. 检查最终结果
    result = images.get("10_result_final.jpg", {})
    if result and result["arr"] is not None:
        arr = result["arr"]
        print(f"6. 最终结果 (10_result_final.jpg):")
        print(f"   大小: {result['size']}")

        # 分析结果图片的质量
        if result["mode"] == "RGB":
            # 检查是否有大面积纯色区域（可能是生成失败）
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            same_color = ((r == g) & (g == b)).mean()
            if same_color > 0.5:
                print(f"   ⚠ 警告: 图片中有 {same_color:.1%} 的像素是灰度的，可能是生成问题")
            else:
                print("   ✓ 颜色分布正常")

        print()

    # 7. 综合诊断
    print(f"{'='*60}")
    print("问题诊断总结")
    print(f"{'='*60}\n")

    issues = []

    if person_orig:
        w, h = person_orig["size"]
        ratio = w / h
        if not (0.72 <= ratio <= 0.78):
            issues.append(f"人物图宽高比异常 ({ratio:.3f}，应为 0.75)")

    if mask:
        arr = mask["arr"]
        if arr is not None:
            if len(arr.shape) == 3:
                arr = arr[..., 0]
            white_ratio = (arr > 200).sum() / arr.size
            if white_ratio < 0.02:
                issues.append("Mask 白色区域极少，无法正确覆盖衣服")
            elif white_ratio < 0.05:
                issues.append("Mask 白色区域偏少，可能覆盖不完整")

    if not issues:
        print("✓ 未发现明显问题，效果差可能是以下原因：")
        print()
        print("  1. 人物图背景不够干净（复杂背景会干扰生成）")
        print("  2. 人物图分辨率不足（建议 >= 768x1024）")
        print("  3. guidance_scale 过高（当前 3.5，建议尝试 2.0-2.5）")
        print("  4. 推理步数不足（当前 50 步，建议尝试 30 步但用 seed 固定）")
    else:
        print("❌ 发现以下问题：")
        for issue in issues:
            print(f"   - {issue}")

    print()
    print("优化建议:")
    print("=" * 60)
    print(
        """
1. 【最重要】使用标准宽高比的人物图
   - 推荐尺寸: 768x1024 或 1024x1365 (3:4 比例)
   - 宽高比应该在 0.72-0.78 之间

2. 使用纯白背景的人物图
   - 如果背景复杂，CatVTON 容易产生伪影
   - 可以用 remove.bg 等工具去除背景

3. 使用纯白背景的衣服商品图
   - 衣服图应该是平铺展示，背景干净

4. 调整参数（降低 guidance_scale）
   - 当前: guidance=3.5
   - 建议: guidance=2.0 或 2.5

5. 检查人物图质量
   - 分辨率越高越好（建议 >= 768x1024）
   - 人物应该居中，占图片 60-80%
   - 姿势尽量标准（正面站立）
"""
    )


def find_latest_debug_sessions(
    base_dir: str = r"D:\models\catvton_debug", limit: int = 5
) -> list[str]:
    """查找最近的调试会话"""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []

    sessions = [d for d in base_path.iterdir() if d.is_dir()]
    if not sessions:
        return []

    sessions.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return [str(s) for s in sessions[:limit]]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        debug_dirs = [sys.argv[1]]
    else:
        debug_dirs = find_latest_debug_sessions()
        if not debug_dirs:
            print("未找到调试目录")
            sys.exit(1)
        print(f"找到 {len(debug_dirs)} 个调试会话，分析最新的...")

    for debug_dir in debug_dirs:
        analyze_debug_session(debug_dir)
