"""
Cascade XML 资源管理器（vton_inference_service 专用）

解决 Windows 中文路径下 OpenCV cv2.data.haarcascades 返回乱码的问题。
"""

import shutil
import tempfile
from pathlib import Path
from typing import Optional

import cv2

# 项目内嵌资源目录
ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "opencv"

# Cascade 文件名列表
CASCADE_FILES = [
    "haarcascade_frontalface_default.xml",
    "haarcascade_frontalface_alt.xml",
    "haarcascade_frontalface_alt2.xml",
]


def _get_temp_ascii_dir() -> Path:
    """获取 ASCII 临时目录（进程内单例）。"""
    temp_dir = Path(tempfile.gettempdir()) / "clothing_assistant_temp_ascii"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def init_cascades() -> bool:
    """
    启动时调用：将项目内嵌的 cascade XML 复制到 ASCII 临时目录。
    """
    assets_dir = ASSETS_DIR
    if not assets_dir.is_dir():
        print(f"[WARN] Cascade assets dir not found: {assets_dir}")
        return False

    temp_dir = _get_temp_ascii_dir()
    all_success = True

    for cascade_file in CASCADE_FILES:
        src = assets_dir / cascade_file
        dst = temp_dir / cascade_file

        if dst.is_file():
            continue

        if not src.is_file():
            print(f"[WARN] Cascade source file not found: {src}")
            all_success = False
            continue

        try:
            shutil.copyfile(src, dst)
            print(f"[DEBUG] Cascade copied: {src} -> {dst}")
        except OSError as e:
            print(f"[ERROR] Failed to copy cascade {cascade_file}: {e}")
            all_success = False

    if all_success:
        print(f"[INFO] Cascades initialized in ASCII temp dir: {temp_dir}")

    return all_success


def get_cascade_path(cascade_name: str = "haarcascade_frontalface_default.xml") -> Optional[str]:
    """获取 cascade XML 的 ASCII 路径。"""
    temp_dir = _get_temp_ascii_dir()
    cascade_path = temp_dir / cascade_name

    if not cascade_path.is_file():
        print(f"[WARN] Cascade file not found in temp: {cascade_path}")
        return None

    return str(cascade_path)


def load_cascade(cascade_name: str = "haarcascade_frontalface_default.xml") -> Optional[cv2.CascadeClassifier]:
    """加载 CascadeClassifier 并验证。"""
    path = get_cascade_path(cascade_name)
    if path is None:
        return None

    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        print(f"[ERROR] CascadeClassifier.empty() == True for: {path}")
        return None

    return cascade


def ensure_cascade_available() -> bool:
    """检查 cascade 是否可用。"""
    for name in CASCADE_FILES:
        cascade = load_cascade(name)
        if cascade is not None and not cascade.empty():
            return True

    print(f"[ERROR] No cascade available in: {_get_temp_ascii_dir()}")
    return False
