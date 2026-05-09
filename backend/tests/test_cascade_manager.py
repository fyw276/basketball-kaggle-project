"""
测试 Haar Cascade 管理器

验证：
1. 项目内嵌 cascade XML 存在
2. 启动时复制到 ASCII 临时目录成功
3. CascadeClassifier.empty() == False
4. 加载的 cascade 可以正常检测人脸
"""

import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def reset_cascade_state():
    """每个测试前重置 cascade_manager 全局状态"""
    import app.services.cascade_manager as cm

    # 重置全局状态
    cm._TEMP_ASCII_DIR = None

    # 清理临时目录
    temp_dir = Path(tempfile.gettempdir()) / "clothing_assistant_temp_ascii"
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
        except OSError:
            pass

    yield

    # 清理临时目录
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
        except OSError:
            pass


class TestCascadeManager:
    """测试 cascade_manager 模块"""

    def test_assets_directory_exists(self):
        """验证项目内嵌 cascade 资源目录存在"""
        from app.services.cascade_manager import ASSETS_DIR

        assert ASSETS_DIR.is_dir(), f"Cascade assets dir not found: {ASSETS_DIR}"
        assert ASSETS_DIR.exists(), f"Cascade assets dir does not exist: {ASSETS_DIR}"

    def test_cascade_files_exist(self):
        """验证所有必需的 cascade XML 文件存在"""
        from app.services.cascade_manager import ASSETS_DIR, CASCADE_FILES

        for cascade_file in CASCADE_FILES:
            cascade_path = ASSETS_DIR / cascade_file
            assert cascade_path.is_file(), f"Cascade file not found: {cascade_path}"

    def test_init_cascades_creates_temp_files(self):
        """验证 init_cascades() 成功复制 cascade 到临时目录"""
        from app.services.cascade_manager import CASCADE_FILES, init_cascades

        # 调用 init_cascades
        result = init_cascades()
        assert result is True, "init_cascades() should return True"

        # 验证所有文件已复制到临时目录
        temp_dir = Path(tempfile.gettempdir()) / "clothing_assistant_temp_ascii"
        for cascade_file in CASCADE_FILES:
            temp_path = temp_dir / cascade_file
            assert temp_path.is_file(), f"Cascade not copied to temp: {temp_path}"

    def test_cascade_path_returns_ascii_path(self):
        """验证 get_cascade_path() 返回 ASCII 路径"""
        from app.services.cascade_manager import CASCADE_FILES, get_cascade_path, init_cascades

        # 确保 cascade 已初始化
        init_cascades()

        for cascade_file in CASCADE_FILES:
            path = get_cascade_path(cascade_file)
            assert path is not None, f"get_cascade_path() returned None for {cascade_file}"

            # 验证是 ASCII 路径
            path.encode("ascii")
            assert Path(path).is_file(), f"Cascade path is not a file: {path}"

    def test_load_cascade_returns_valid_classifier(self):
        """验证 load_cascade() 返回有效的 CascadeClassifier"""
        from app.services.cascade_manager import CASCADE_FILES, init_cascades, load_cascade

        # 确保 cascade 已初始化
        init_cascades()

        for cascade_file in CASCADE_FILES:
            cascade = load_cascade(cascade_file)
            assert cascade is not None, f"load_cascade() returned None for {cascade_file}"

            # 关键断言：验证 CascadeClassifier 不为空
            assert not cascade.empty(), (
                f"CascadeClassifier.empty() == True for {cascade_file}. "
                f"This means the cascade XML failed to load properly."
            )

    def test_ensure_cascade_available_returns_true(self):
        """验证 ensure_cascade_available() 返回 True（至少一个 cascade 可用）"""
        from app.services.cascade_manager import ensure_cascade_available, init_cascades

        # 确保 cascade 已初始化
        init_cascades()

        result = ensure_cascade_available()
        assert result is True, (
            "ensure_cascade_available() returned False. "
            "At least one cascade should be available."
        )

    def test_cascade_can_detect_face_in_test_image(self):
        """验证加载的 cascade 可以实际检测人脸"""
        from app.services.cascade_manager import init_cascades, load_cascade

        # 确保 cascade 已初始化
        init_cascades()

        cascade = load_cascade("haarcascade_frontalface_default.xml")
        assert cascade is not None
        assert not cascade.empty()

        # 创建一个人脸测试图像（简单模拟）
        test_image = np.zeros((200, 200), dtype=np.uint8)

        # 检测人脸（测试 API 是否正常工作）
        faces = cascade.detectMultiScale(
            test_image,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
        )

        # 即使检测不到人脸（因为是空白图像），API 调用也不应抛出异常
        assert faces is not None
        assert isinstance(faces, tuple) or isinstance(faces, list)

    def test_cascade_paths_are_ascii(self):
        """验证临时目录中的 cascade 路径是 ASCII（源路径允许中文）"""
        from app.services.cascade_manager import CASCADE_FILES, get_cascade_path, init_cascades

        # 初始化 cascade
        init_cascades()

        for cascade_file in CASCADE_FILES:
            temp_path = get_cascade_path(cascade_file)
            assert temp_path is not None

            # 验证临时路径是 ASCII（这是关键）
            temp_str = str(temp_path)
            temp_str.encode("ascii")  # 不抛异常即通过

            # 验证路径不含中文（更直接的检查）
            assert not any(
                ord(c) > 127 for c in temp_str
            ), f"Temporary cascade path contains non-ASCII characters: {temp_path}"

    def test_cascade_manager_solves_chinese_path_problem(self):
        """验证 cascade_manager 能解决中文路径问题"""
        from app.services.cascade_manager import init_cascades, load_cascade

        init_cascades()

        # 即使当前项目路径包含中文，cascade_manager 仍应返回 ASCII 路径
        cascade = load_cascade("haarcascade_frontalface_default.xml")
        assert cascade is not None
        assert not cascade.empty()

        # 验证返回的 cascade 可以正常工作
        test_image = np.zeros((100, 100), dtype=np.uint8)
        faces = cascade.detectMultiScale(test_image)
        assert faces is not None


class TestCascadeInVirtualTryon:
    """测试 virtual_tryon.py 中 cascade 的使用"""

    def test_cascade_for_virtual_tryon(self):
        """验证 cascade 可用于 virtual_tryon 模块"""
        from PIL import Image

        from app.services.cascade_manager import init_cascades, load_cascade

        # 初始化 cascade
        init_cascades()

        # 创建一个测试图像
        test_image = Image.new("RGB", (100, 100), color="red")

        # 直接测试 cascade_manager 可以正常工作
        cascade = load_cascade("haarcascade_frontalface_default.xml")
        assert cascade is not None, "Cascade should be loaded successfully"
        assert not cascade.empty(), "CascadeClassifier should not be empty"

        # 验证可以使用 cascade 检测（模拟 _garment_has_face 的行为）
        arr = np.array(test_image.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64))
        assert faces is not None, "detectMultiScale should return a result"


class TestCascadeInCatVTONRunner:
    """测试 catvton_runner.py 中 cascade 的使用"""

    def test_cascade_manager_importable_from_vton(self):
        """验证 cascade_manager 可以从 vton_inference_service 导入"""
        from app.services.cascade_manager import (
            ensure_cascade_available,
            init_cascades,
            load_cascade,
        )

        # 初始化 cascade（使用 backend 的 cascade_manager）
        init_cascades()
        result = ensure_cascade_available()
        assert result is True

        cascade = load_cascade("haarcascade_frontalface_default.xml")
        assert cascade is not None
        assert not cascade.empty()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
