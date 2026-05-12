"""
修复 CatVTON SD 模型缓存脚本

问题：runwayml/stable-diffusion-inpainting 使用了 .bin 格式而非 .safetensors
解决：删除旧缓存并重新下载正确格式
"""

import os
import shutil
from pathlib import Path

HF_CACHE = Path("D:/hf-cache/hub")
SD_INPAINTING_PATH = HF_CACHE / "models--runwayml--stable-diffusion-inpainting"


def main():
    print("=" * 60)
    print("CatVTON SD 模型缓存修复工具")
    print("=" * 60)

    # 1. 检查当前状态
    print("\n[1] 检查当前缓存状态...")
    if SD_INPAINTING_PATH.exists():
        unet_path = (
            SD_INPAINTING_PATH / "snapshots" / "8a4288a76071f7280aedbdb3253bdb9e9d5d84bb" / "unet"
        )
        if unet_path.exists():
            files = list(unet_path.glob("*"))
            print(f"    找到 UNet 目录: {unet_path}")
            for f in files:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"      - {f.name}: {size_mb:.1f} MB")

            bin_files = list(unet_path.glob("*.bin"))
            safetensors_files = list(unet_path.glob("*.safetensors"))

            if bin_files:
                print(f"\n    [!] 发现问题: 存在旧格式 .bin 文件 ({len(bin_files)} 个)")
                print(f"        这些文件使用 pickle 格式，可能导致 CatVTON 输出异常")

            if safetensors_files:
                print(f"\n    [OK] 找到新格式 .safetensors 文件 ({len(safetensors_files)} 个)")
    else:
        print("    [OK] 缓存不存在，无需清理")

    # 2. 删除损坏的缓存
    print("\n[2] 删除损坏的缓存...")
    print(f"    将删除: {SD_INPAINTING_PATH}")

    if SD_INPAINTING_PATH.exists():
        try:
            shutil.rmtree(SD_INPAINTING_PATH)
            print("    [OK] 缓存已删除")
        except Exception as e:
            print(f"    [ERROR] 删除失败: {e}")
            return
    else:
        print("    [OK] 缓存不存在")

    # 3. 重新下载模型
    print("\n[3] 重新下载 stable-diffusion-inpainting...")
    print("    这将从 HuggingFace 下载约 3-5GB 的模型文件")
    print("    设置 HF_ENDPOINT=https://hf-mirror.com 加速下载")

    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    os.environ["HF_HOME"] = "D:/hf-cache"

    try:
        from diffusers import UNet2DConditionModel

        print("\n    正在下载 UNet 模型 (可能需要几分钟)...")
        model = UNet2DConditionModel.from_pretrained(
            "runwayml/stable-diffusion-inpainting", subfolder="unet", cache_dir="D:/hf-cache"
        )
        print("    [OK] UNet 下载完成!")

        print("\n    正在下载 VAE 模型...")
        from diffusers import AutoencoderKL

        vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", cache_dir="D:/hf-cache")
        print("    [OK] VAE 下载完成!")

        print("\n[4] 验证下载...")
        if SD_INPAINTING_PATH.exists():
            unet_path = (
                SD_INPAINTING_PATH
                / "snapshots"
                / "8a4288a76071f7280aedbdb3253bdb9e9d5d84bb"
                / "unet"
            )
            if unet_path.exists():
                files = list(unet_path.glob("*.safetensors"))
                if files:
                    print(f"    [OK] 发现 .safetensors 文件: {files[0].name}")
                    print(f"         大小: {files[0].stat().st_size / (1024*1024):.1f} MB")
                else:
                    files = list(unet_path.glob("*.bin"))
                    if files:
                        print(f"    [!] 仍然只有 .bin 文件: {files[0].name}")

    except Exception as e:
        print(f"\n    [ERROR] 下载失败: {e}")
        print("\n    备选方案：手动下载")
        print("    1. 访问 https://huggingface.co/runwayml/stable-diffusion-inpainting")
        print("    2. 下载 unet 文件到本地")

    print("\n" + "=" * 60)
    print("修复完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
