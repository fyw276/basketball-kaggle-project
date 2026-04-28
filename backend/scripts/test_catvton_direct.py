"""
快速测试 CatVTON 是否能正确生成试衣结果。
运行：
    cd backend
    python scripts/test_catvton_direct.py

需要：
    1. 人物全身图 (person.jpg)
    2. 衣物商品图 (garment.jpg)
    可以用任意 JPEG 图片测试。
"""

import base64
import io
import os
import sys
from pathlib import Path

# 确保 backend 在 path 中（backend/ 目录包含 app/ 模块）
sys.path.insert(0, str(Path(__file__).parent.parent))  # backend/
os.environ.setdefault("HF_HOME", r"D:\hf-cache")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from PIL import Image


def test_catvton_direct(
    low_vram: bool = False,
    force_fp16: bool = False,
    vae_slicing: bool = True,
    xformers: bool = True,
    preprocess_only: bool = False,
    steps: int = 50,
    timeout: int = 2400,
    debug_dir: str | None = None,
):
    """直接调用 catvton_engine_client，绕过 API 层

    Args:
        low_vram: 一键低显存模式（等于 force_fp16 + vae_slicing + xformers）
        force_fp16: 强制 fp16 而非 bf16
        vae_slicing: 启用 VAE 分片推理
        xformers: 启用 xformers 高效注意力
        preprocess_only: 仅运行前处理（mask + pose 生成），跳过扩散推理
        steps: 扩散步数
        timeout: 超时秒数
        debug_dir: 白盒调试输出目录
    """

    # 查找测试图片
    test_dir = Path(__file__).parent
    person_path = test_dir / "test_person.jpg"
    garment_path = test_dir / "test_garment.jpg"

    # 如果没有测试图片，生成占位图
    if not person_path.exists():
        print("[WARN] test_person.jpg 不存在，创建占位图...")
        img = Image.new("RGB", (512, 768), color=(200, 180, 160))
        img.save(person_path)
        print(f"  已创建: {person_path}")

    if not garment_path.exists():
        print("[WARN] test_garment.jpg 不存在，创建占位图...")
        img = Image.new("RGB", (512, 640), color=(80, 120, 200))
        img.save(garment_path)
        print(f"  已创建: {garment_path}")

    person_img = Image.open(person_path).convert("RGB")
    garment_img = Image.open(garment_path).convert("RGB")

    print(f"人物图: {person_img.size}, 衣服图: {garment_img.size}")
    print()

    # 导入 CatVTON client
    import asyncio

    from app.services.tryon_v2.catvton_engine_client import call_local_catvton

    async def run():
        if preprocess_only:
            print("[1/2] 调用 CatVTON (preprocess_only 模式，只生成 mask，不跑扩散)...")
            result = await call_local_catvton(
                garment_bytes=garment_to_bytes(garment_img),
                person_bytes=person_to_bytes(person_img),
                garment_category="upper",
                preprocess_only=True,
                debug_dir=debug_dir,
            )

            print(f"    状态: {result.get('status')}")
            print(f"    消息: {result.get('message')}")
            if result.get("metadata"):
                print(f"    元数据: {result.get('metadata')}")
            debug_session_dir = result.get("metadata", {}).get("debug_session_dir")
            if debug_session_dir:
                print(f"    调试目录: {debug_session_dir}")
                print()
                print("[INFO] 请查看以下文件验证 mask 质量:")
                print(f"  - {debug_session_dir}/01_input_person.jpg")
                print(f"  - {debug_session_dir}/02_input_garment.jpg")
                print(f"  - {debug_session_dir}/03_mask.png  ← 关键：白色区域应为衣物区域")
                print(f"  - {debug_session_dir}/04_pose_keypoints.jpg  ← 关键：关键点是否准确")
                print(f"  - {debug_session_dir}/09_mask_overlay.jpg  ← mask 叠加到人物图")
            print()
            return result.get("status") in ("preprocess_only_success", "success")

        print("[1/2] 调用 CatVTON (preprocess_only 模式，验证 mask 质量)...")
        result_pre = await call_local_catvton(
            garment_bytes=garment_to_bytes(garment_img),
            person_bytes=person_to_bytes(person_img),
            garment_category="upper",
            preprocess_only=True,
            debug_dir=debug_dir,
        )
        debug_session_dir = result_pre.get("metadata", {}).get("debug_session_dir")
        if debug_session_dir:
            print(f"    mask 调试目录: {debug_session_dir}")
            print(f"    建议先检查 {debug_session_dir}/03_mask.png 确认 mask 质量")
        print()

        print(f"[2/2] 调用 CatVTON (完整推理，steps={steps}, low_vram={low_vram})...")
        print("    注意：这需要 GPU，约 30-120 秒...")

        # 内部实现：调用 _run_catvton_sync 以传递低显存参数
        from app.services.tryon_v2.catvton_engine_client import _run_catvton_sync

        person_bytes = person_to_bytes(person_img)
        garment_bytes = garment_to_bytes(garment_img)

        loop = asyncio.get_event_loop()
        result_full = await loop.run_in_executor(
            None,
            lambda: _run_catvton_sync(
                person_bytes=person_bytes,
                garment_bytes=garment_bytes,
                cloth_type="upper",
                seed=-1,
                timeout=timeout,
                debug_dir=debug_dir,
                preprocess_only=False,
                vae_slicing=vae_slicing,
                xformers=xformers,
                force_fp16=force_fp16,
                low_vram_mode=low_vram,
            ),
        )

        print(f"    状态: {result_full.get('status')}")
        print(f"    消息: {result_full.get('message')}")
        meta = result_full.get("metadata", {})
        if meta:
            import json

            print(
                f"    元数据: {json.dumps({k: v for k, v in meta.items() if k != 'debug_session_dir'}, indent=4, ensure_ascii=False)}"
            )
        print()

        if result_full.get("status") == "success" and result_full.get("result_image") is not None:
            result_img = result_full["result_image"]

            # 保存结果
            output_path = test_dir / "test_catvton_result.jpg"
            result_img.save(output_path, quality=95)
            print(f"[DONE] 结果已保存: {output_path}")
            print(f"    尺寸: {result_img.size}")

            # 显示 base64 缩略图描述
            print()
            print("[INFO] 如果结果不像 CatVTON 输出，可能的原因：")
            print("  1. CatVTON 推理实际没有运行（检查后端日志中的 [CATVTON-RUNNER]）")
            print("  2. Mask 错误导致衣物区域不对 → 查看 03_mask.png")
            print("  3. 其他引擎（如 bailian/warp）被降级使用")
            return True
        else:
            print(f"[ERROR] CatVTON 完整推理失败: {result_full.get('message')}")
            print(f"    stderr hint: {result_full.get('metadata', {}).get('stderr', 'N/A')[:200]}")
            return False

    return asyncio.run(run())


def person_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def garment_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


if __name__ == "__main__":
    import argparse

    # Fix Chinese encoding for print() output on Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="CatVTON 直接测试")
    parser.add_argument(
        "--low-vram",
        action="store_true",
        help="启用低显存模式（等于 --force-fp16 + VAE slicing + xformers）",
    )
    parser.add_argument(
        "--force-fp16",
        action="store_true",
        help="强制 fp16 而非 bf16（RTX 4060 Laptop 推荐，节省约 2GB 显存）",
    )
    parser.add_argument("--no-vae-slicing", action="store_true", help="禁用 VAE 分片推理")
    parser.add_argument("--no-xformers", action="store_true", help="禁用 xformers 高效注意力")
    parser.add_argument(
        "--preprocess-only",
        action="store_true",
        help="仅运行前处理（mask + pose 生成），跳过扩散推理，极大加快调试速度",
    )
    parser.add_argument("--steps", type=int, default=50, help="扩散步数（默认 50，推荐 20-80）")
    parser.add_argument("--timeout", type=int, default=2400, help="超时秒数（默认 2400）")
    parser.add_argument("--debug-dir", default=None, help="白盒调试输出目录")
    args = parser.parse_args()

    print("=" * 60)
    print("CatVTON 直接测试")
    print("=" * 60)
    print()
    print(f"VRAM 优化模式:")
    print(f"  --low-vram     = {args.low_vram}")
    print(f"  --force-fp16   = {args.force_fp16}")
    print(f"  --no-vae-slicing = {args.no_vae_slicing}")
    print(f"  --no-xformers  = {args.no_xformers}")
    print(f"  --preprocess-only = {args.preprocess_only}")
    print(f"  --steps        = {args.steps}")
    print()

    success = test_catvton_direct(
        low_vram=args.low_vram,
        force_fp16=args.force_fp16,
        vae_slicing=not args.no_vae_slicing,
        xformers=not args.no_xformers,
        preprocess_only=args.preprocess_only,
        steps=args.steps,
        timeout=args.timeout,
        debug_dir=args.debug_dir,
    )

    print()
    print("=" * 60)
    if success:
        print("CatVTON 推理完成！请查看输出图片是否像 CatVTON 的风格")
        print("(CatVTON 特点：衣物自然贴合、光影真实、边缘平滑)")
    else:
        print("CatVTON 推理失败，请检查错误信息")
    print("=" * 60)
