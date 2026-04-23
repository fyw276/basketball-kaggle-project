"""
Debug script: 检查 warp 引擎的衣服分割和阴影问题。
直接运行: python backend/debug_garment.py
"""

import os
import sys
import traceback
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image


def diagnose_garment_cutout():
    """检查 garment cutout 是否正确提取了衣服像素。"""

    # 找一张最近的衣服图测试
    upload_dir = Path("D:/Users/omen/OneDrive/桌面/clothing-assistant/backend/uploads")
    garment_files = list(upload_dir.glob("**/*garment*"))
    garment_files += list(upload_dir.glob("**/*cloth*"))
    garment_files += list(upload_dir.glob("**/*.jpg"))
    garment_files += list(upload_dir.glob("**/*.png"))
    garment_files = [f for f in garment_files if f.is_file()][:5]

    print(f"=== Garment Cutout Diagnostic ===")
    print(f"Found {len(garment_files)} candidate garment files")
    for f in garment_files[:3]:
        print(f"  - {f.name} ({f.stat().st_size // 1024}KB)")

    # 使用 backend 的 garment_struct
    from app.services.tryon_v2.garment_struct import cutout_garment_rgba

    for garment_path in garment_files[:2]:
        print(f"\n--- Testing: {garment_path.name} ---")
        try:
            img = Image.open(garment_path).convert("RGB")
            print(f"  Image size: {img.size}, mode: {img.mode}")

            cutout = cutout_garment_rgba(img)
            rgba = cutout.rgba
            cropped = cutout.cropped

            print(f"  Cutout rgba size: {rgba.size}")
            print(f"  Cropped size: {cropped.size}")

            # 检查 alpha 通道统计
            a = np.array(cropped.split()[3])
            print(
                f"  Alpha stats: min={a.min()}, max={a.max()}, mean={a.mean():.1f}, nonzero={int((a > 10).sum())}"
            )

            # 检查 RGB 在有 alpha 的区域
            r, g, b, a_ch = cropped.split()
            r_arr = np.array(r)
            g_arr = np.array(g)
            b_arr = np.array(b)
            a_arr = np.array(a_ch)

            # 只看有衣服像素的地方 (alpha > 200 = 前景)
            fg_mask = a_arr > 200
            if fg_mask.sum() > 0:
                r_fg = r_arr[fg_mask].mean()
                g_fg = g_arr[fg_mask].mean()
                b_fg = b_arr[fg_mask].mean()
                print(f"  Foreground RGB mean: R={r_fg:.1f}, G={g_fg:.1f}, B={b_fg:.1f}")
                if r_fg < 30 and g_fg < 30 and b_fg < 30:
                    print("  *** WARNING: Foreground pixels are BLACK or near-black! ***")
                elif r_fg < 80 and g_fg < 80 and b_fg < 80:
                    print("  *** WARNING: Foreground pixels are very dark! ***")
            else:
                print("  *** WARNING: No solid foreground pixels (alpha > 200)! ***")
                fg_mask2 = a_arr > 10
                if fg_mask2.sum() > 0:
                    r_arr2 = r_arr[fg_mask2]
                    g_arr2 = g_arr[fg_mask2]
                    b_arr2 = b_arr[fg_mask2]
                    print(
                        f"  (alpha>10) RGB: R={r_arr2.mean():.1f}, G={g_arr2.mean():.1f}, B={b_arr2.mean():.1f}"
                    )

        except Exception as e:
            print(f"  Error: {e}")
            traceback.print_exc()


def diagnose_cast_shadow():
    """检查 _add_cast_shadow 是否已移除（该函数有 bug 导致衣服变黑）。"""
    print("\n=== Cast Shadow Diagnostic ===")
    try:
        from app.services.tryon_v2.warp_engine import _add_cast_shadow

        print("  WARNING: _add_cast_shadow still exists (it has a bug that darkens garments)")
    except ImportError:
        print("  OK: _add_cast_shadow removed (this is correct - the function had a bug)")


def diagnose_warp_result():
    """检查最近生成的 warp 结果。"""
    print("\n=== Warp Result Diagnostic ===")

    result_dir = Path("D:/Users/omen/OneDrive/桌面/clothing-assistant/backend/uploads")
    result_files = list(result_dir.glob("**/*result*.jpg"))
    result_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    for result_path in result_files[:2]:
        print(f"\n--- {result_path.name} ({result_path.stat().st_size // 1024}KB) ---")
        try:
            img = Image.open(result_path).convert("RGB")
            arr = np.array(img)
            print(f"  Size: {img.size}")
            # 检查中心区域的衣服
            h, w = arr.shape[:2]
            center = arr[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
            mean_rgb = center.mean(axis=(0, 1))
            print(f"  Center region mean RGB: {mean_rgb}")
            # 找暗色区域
            dark = arr.mean(axis=2) < 40
            print(
                f"  Dark pixels (avg<40): {int(dark.sum())} / {arr.shape[0]*arr.shape[1]} ({100*dark.mean():.1f}%)"
            )
        except Exception as e:
            print(f"  Error: {e}")


def test_warp_top_direct():
    """直接测试 tryon_top_warp 输出颜色是否正确。"""
    print("\n=== Direct Warp Test ===")

    try:
        from app.services.tryon_v2.warp_engine import tryon_top_warp

        result_dir = Path("D:/Users/omen/OneDrive/桌面/clothing-assistant/backend/uploads")
        person_files = list(result_dir.glob("**/person*"))
        person_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        garment_files = list(result_dir.glob("**/garment*"))
        garment_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        if not person_files or not garment_files:
            print("  No test images found")
            return

        person_path = person_files[0]
        garment_path = garment_files[0]

        print(f"  Person: {person_path.name}")
        print(f"  Garment: {garment_path.name}")

        person_img = Image.open(person_path).convert("RGB")
        garment_img = Image.open(garment_path).convert("RGB")

        result, meta = tryon_top_warp(person_img, garment_img)
        arr = np.array(result)

        # 检查结果图的衣服区域（中心偏上）
        h, w = arr.shape[:2]
        chest_area = arr[int(h * 0.15) : int(h * 0.45), int(w * 0.25) : int(w * 0.75)]
        mean_rgb = chest_area.mean(axis=(0, 1))
        print(f"  Chest area mean RGB: [{mean_rgb[0]:.1f}, {mean_rgb[1]:.1f}, {mean_rgb[2]:.1f}]")

        # 找有衣服的区域（非背景）
        # 背景通常很白或很黑，衣服有颜色
        if mean_rgb.mean() > 30:
            print(f"  PASS: Warp result looks good (garment colors preserved)")
        else:
            print(f"  FAIL: Warp result too dark ({mean_rgb.mean():.1f})")

        # 保存测试结果
        import os
        import tempfile

        fd, test_out_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        result.save(test_out_path)
        print(f"  Saved: {test_out_path}")

    except Exception as e:
        print(f"  Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    diagnose_garment_cutout()
    diagnose_cast_shadow()
    diagnose_warp_result()
    test_warp_top_direct()
