"""
OOTDiffusion inference engine for VTON service.

This module provides a wrapper around OOTDiffusion for virtual try-on inference.
Requires OOTDiffusion to be installed separately.

Installation:
    1. Clone OOTDiffusion: git clone https://github.com/levihsu/OOTDiffusion.git
    2. Install dependencies: pip install -r requirements.txt
    3. Download checkpoints from Hugging Face
    4. Set OOTD_PATH environment variable

Usage:
    from ootd_engine import get_engine

    engine = get_engine()
    result = engine.infer(
        person_image=person_img,
        garment_image=garment_img,
        category=0,  # 0=upper, 1=lower, 2=dress
    )
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import torch
from PIL import Image

logger = logging.getLogger(__name__)

# 添加OOTDiffusion路径
OOTD_PATH = os.environ.get("OOTD_PATH", str(Path.home() / "OOTDiffusion"))

# 尝试导入OOTDiffusion模块
OOTDiffusionModel = None
try:
    sys.path.insert(0, OOTD_PATH)
    # 根据实际的OOTDiffusion API调整导入
    # 这里是示例，实际API可能不同
    from run.run_ootd import OOTDiffusionModel as _OOTDModel
    OOTDiffusionModel = _OOTDModel
    logger.info(f"OOTDiffusion loaded from {OOTD_PATH}")
except ImportError as e:
    logger.warning(f"OOTDiffusion not available: {e}")
    logger.warning(f"Expected path: {OOTD_PATH}")
    logger.warning("Set OOTD_PATH environment variable to OOTDiffusion directory")


class OOTDEngine:
    """
    OOTDiffusion inference wrapper.

    This class provides a high-level interface for OOTDiffusion inference,
    handling model initialization, image preprocessing, and result generation.
    """

    def __init__(
        self,
        checkpoint_path: Optional[str] = None,
        device: Optional[str] = None,
    ):
        """
        Initialize OOTDEngine.

        Args:
            checkpoint_path: Path to OOTDiffusion checkpoints directory.
                           Defaults to $OOTD_PATH/checkpoints
            device: Device to run inference on ('cuda' or 'cpu').
                   Defaults to 'cuda' if available, else 'cpu'

        Raises:
            ImportError: If OOTDiffusion is not installed
            RuntimeError: If CUDA is not available but required
        """
        if OOTDiffusionModel is None:
            raise ImportError(
                "OOTDiffusion not found. Please install it first.\n"
                f"Expected path: {OOTD_PATH}\n"
                "Set OOTD_PATH environment variable to OOTDiffusion directory.\n"
                "Installation: git clone https://github.com/levihsu/OOTDiffusion.git"
            )

        self.checkpoint_path = checkpoint_path or os.path.join(OOTD_PATH, "checkpoints")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        if self.device == "cpu":
            logger.warning(
                "Running OOTDiffusion on CPU. This will be very slow. "
                "GPU is strongly recommended."
            )

        logger.info(f"Initializing OOTDEngine on {self.device}")
        logger.info(f"Checkpoint path: {self.checkpoint_path}")

        # 初始化模型
        # 注意：实际的初始化代码需要根据OOTDiffusion的API调整
        try:
            self.model = OOTDiffusionModel(
                checkpoint_path=self.checkpoint_path,
                device=self.device,
            )
            logger.info("OOTDEngine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OOTDEngine: {e}")
            raise

    def infer(
        self,
        person_image: Image.Image,
        garment_image: Image.Image,
        category: int = 0,
        num_inference_steps: int = 20,
        guidance_scale: float = 2.0,
        seed: Optional[int] = None,
    ) -> Image.Image:
        """
        Run OOTDiffusion inference for virtual try-on.

        Args:
            person_image: Person full-body image (PIL Image)
            garment_image: Garment product image (PIL Image)
            category: Garment category
                     0 = upper body (上装)
                     1 = lower body (下装)
                     2 = dress (裙装)
            num_inference_steps: Number of diffusion steps (default: 20)
                               Higher = better quality but slower
            guidance_scale: Guidance scale for diffusion (default: 2.0)
                          Higher = more faithful to prompt
            seed: Random seed for reproducibility (optional)

        Returns:
            Result image with person wearing the garment (PIL Image)

        Raises:
            ValueError: If category is invalid
            RuntimeError: If inference fails
        """
        if category not in {0, 1, 2}:
            raise ValueError(f"Invalid category: {category}. Must be 0, 1, or 2.")

        logger.info(
            f"Running OOTDiffusion inference: category={category}, "
            f"steps={num_inference_steps}, guidance={guidance_scale}"
        )

        try:
            # 预处理图像
            person_image = person_image.convert("RGB")
            garment_image = garment_image.convert("RGB")

            # 调用OOTDiffusion推理
            # 注意：实际的API调用需要根据OOTDiffusion的实现调整
            result = self.model.generate(
                person_image=person_image,
                garment_image=garment_image,
                category=category,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                seed=seed,
            )

            logger.info("OOTDiffusion inference completed successfully")
            return result

        except Exception as e:
            logger.error(f"OOTDiffusion inference failed: {e}")
            raise RuntimeError(f"Inference failed: {e}") from e

    def warmup(self):
        """
        Warm up the model by running a dummy inference.

        This can help reduce the latency of the first real inference.
        """
        logger.info("Warming up OOTDEngine...")
        try:
            # 创建dummy图像
            dummy_person = Image.new("RGB", (768, 1024), color=(128, 128, 128))
            dummy_garment = Image.new("RGB", (768, 1024), color=(200, 200, 200))

            # 运行dummy推理
            self.infer(
                person_image=dummy_person,
                garment_image=dummy_garment,
                category=0,
                num_inference_steps=1,  # 最少步数
            )

            logger.info("OOTDEngine warmup completed")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")


# 全局单例
_engine: Optional[OOTDEngine] = None
_engine_lock = None


def get_engine(
    checkpoint_path: Optional[str] = None,
    device: Optional[str] = None,
    warmup: bool = False,
) -> OOTDEngine:
    """
    Get or create OOTDEngine singleton.

    This function ensures only one instance of OOTDEngine is created,
    which is important for memory efficiency.

    Args:
        checkpoint_path: Path to checkpoints (only used on first call)
        device: Device to use (only used on first call)
        warmup: Whether to warm up the model (only used on first call)

    Returns:
        OOTDEngine instance

    Raises:
        ImportError: If OOTDiffusion is not installed
        RuntimeError: If initialization fails
    """
    global _engine, _engine_lock

    # 简单的线程安全（生产环境建议使用threading.Lock）
    if _engine is None:
        logger.info("Creating OOTDEngine singleton")
        _engine = OOTDEngine(
            checkpoint_path=checkpoint_path,
            device=device,
        )

        if warmup:
            _engine.warmup()

    return _engine


def is_available() -> bool:
    """
    Check if OOTDiffusion is available.

    Returns:
        True if OOTDiffusion can be imported, False otherwise
    """
    return OOTDiffusionModel is not None


def get_device_info() -> dict:
    """
    Get device information.

    Returns:
        Dictionary with device information
    """
    return {
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "ootd_path": OOTD_PATH,
        "ootd_available": is_available(),
    }


if __name__ == "__main__":
    # 测试代码
    print("OOTDEngine Test")
    print("=" * 50)

    # 打印设备信息
    info = get_device_info()
    print("Device Info:")
    for key, value in info.items():
        print(f"  {key}: {value}")

    # 测试是否可用
    if is_available():
        print("\n✓ OOTDiffusion is available")

        # 尝试初始化
        try:
            engine = get_engine(warmup=True)
            print("✓ OOTDEngine initialized successfully")
        except Exception as e:
            print(f"✗ Failed to initialize OOTDEngine: {e}")
    else:
        print("\n✗ OOTDiffusion is not available")
        print(f"  Set OOTD_PATH to OOTDiffusion directory (current: {OOTD_PATH})")
