"""
Cascade XML 资源管理器

解决 Windows 中文路径下 OpenCV cv2.data.haarcascades 返回乱码的问题。
策略：
1. 使用项目内嵌的 XML 文件（backend/assets/opencv/）
2. 启动时自动复制到 ASCII 路径 temp_ascii/
3. 所有代码使用固定的 ASCII 路径加载 CascadeClassifier
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import cv2

logger = logging.getLogger(__name__)

# 项目内嵌资源目录
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "opencv"

# ASCII 临时目录（启动时创建）
_TEMP_ASCII_DIR: Optional[Path] = None

# Cascade 文件名列表
CASCADE_FILES = [
    "haarcascade_frontalface_default.xml",
    "haarcascade_frontalface_alt.xml",
    "haarcascade_frontalface_alt2.xml",
]


def _get_temp_ascii_dir() -> Path:
    """获取 ASCII 临时目录（懒加载，进程内单例）。"""
    global _TEMP_ASCII_DIR
    if _TEMP_ASCII_DIR is None:
        # 使用进程内临时目录，避免跨进程竞争
        _TEMP_ASCII_DIR = Path(tempfile.gettempdir()) / "clothing_assistant_temp_ascii"
        _TEMP_ASCII_DIR.mkdir(parents=True, exist_ok=True)
    return _TEMP_ASCII_DIR


def init_cascades() -> bool:
    """
    启动时调用：将项目内嵌的 cascade XML 复制到 ASCII 临时目录。

    Returns:
        True: 所有文件复制成功或已存在
        False: 至少有一个文件复制失败
    """
    global _TEMP_ASCII_DIR

    assets_dir = ASSETS_DIR
    if not assets_dir.is_dir():
        logger.warning("Cascade assets dir not found: %s", assets_dir)
        return False

    temp_dir = _get_temp_ascii_dir()
    all_success = True

    for cascade_file in CASCADE_FILES:
        src = assets_dir / cascade_file
        dst = temp_dir / cascade_file

        if dst.is_file():
            # 已存在，跳过
            continue

        if not src.is_file():
            logger.warning("Cascade source file not found: %s", src)
            all_success = False
            continue

        try:
            shutil.copyfile(src, dst)
            logger.debug("Cascade copied to ASCII temp: %s -> %s", src, dst)
        except OSError as e:
            logger.error("Failed to copy cascade %s: %s", cascade_file, e)
            all_success = False

    if all_success:
        logger.info("Cascades initialized in ASCII temp dir: %s", temp_dir)
    else:
        logger.warning("Some cascades failed to initialize")

    return all_success


def get_cascade_path(cascade_name: str = "haarcascade_frontalface_default.xml") -> Optional[str]:
    """
    获取 cascade XML 的 ASCII 路径（供 CascadeClassifier 使用）。

    Args:
        cascade_name: cascade 文件名

    Returns:
        ASCII 路径字符串，失败返回 None
    """
    temp_dir = _get_temp_ascii_dir()
    cascade_path = temp_dir / cascade_name

    if not cascade_path.is_file():
        logger.warning("Cascade file not found in temp: %s", cascade_path)
        return None

    return str(cascade_path)


def load_cascade(
    cascade_name: str = "haarcascade_frontalface_default.xml",
) -> Optional[cv2.CascadeClassifier]:
    """
    加载 CascadeClassifier 并验证。

    Args:
        cascade_name: cascade 文件名

    Returns:
        已加载的 CascadeClassifier，失败返回 None
    """
    path = get_cascade_path(cascade_name)
    if path is None:
        return None

    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        logger.error("CascadeClassifier.empty() == True for: %s", path)
        return None

    return cascade


def ensure_cascade_available() -> bool:
    """
    启动时检查 cascade 是否可用。

    Returns:
        True: 至少一个 cascade 可用
        False: 全部不可用
    """
    for name in CASCADE_FILES:
        cascade = load_cascade(name)
        if cascade is not None and not cascade.empty():
            logger.debug("Cascade available: %s", name)
            return True

    logger.error("No cascade available in: %s", _get_temp_ascii_dir())
    return False
