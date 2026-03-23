"""
快速检查脚本 - 验证后端核心配置

这个脚本会快速检查：
1. Python 环境
2. 依赖包
3. 配置文件
4. 核心模块导入
"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_python_version():
    """检查 Python 版本"""
    print("\n[1/5] 检查 Python 版本...")
    version = sys.version_info
    print(f"  Python {version.major}.{version.minor}.{version.micro}")

    if version.major == 3 and version.minor >= 9:
        print("  ✓ Python 版本符合要求 (3.9+)")
        return True
    else:
        print("  ✗ Python 版本过低，需要 3.9+")
        return False


def check_dependencies():
    """检查关键依赖包"""
    print("\n[2/5] 检查关键依赖包...")

    required_packages = {
        "fastapi": "FastAPI 框架",
        "uvicorn": "ASGI 服务器",
        "sqlalchemy": "ORM 框架",
        "redis": "Redis 客户端",
        "tensorflow": "深度学习框架",
        "pydantic": "数据验证",
        "jose": "JWT 认证",
        "bcrypt": "密码加密",
    }

    missing = []
    for package, description in required_packages.items():
        try:
            __import__(package)
            print(f"  ✓ {package:15} - {description}")
        except ImportError:
            print(f"  ✗ {package:15} - {description} (缺失)")
            missing.append(package)

    if missing:
        print(f"\n  缺失 {len(missing)} 个包，请运行: pip install -r requirements.txt")
        return False

    print(f"  ✓ 所有 {len(required_packages)} 个关键包已安装")
    return True


def check_config_files():
    """检查配置文件"""
    print("\n[3/5] 检查配置文件...")

    config_files = {
        ".env": "环境变量配置",
        ".env.example": "环境变量示例",
        "requirements.txt": "依赖列表",
        "pyproject.toml": "项目配置",
    }

    missing = []
    for file, description in config_files.items():
        file_path = Path(__file__).parent.parent / file
        if file_path.exists():
            print(f"  ✓ {file:20} - {description}")
        else:
            print(f"  ✗ {file:20} - {description} (缺失)")
            if file != ".env":  # .env 可以不存在
                missing.append(file)

    if missing:
        print(f"\n  缺失 {len(missing)} 个配置文件")
        return False

    print("  ✓ 所有配置文件存在")
    return True


def check_core_modules():
    """检查核心模块导入"""
    print("\n[4/5] 检查核心模块...")

    modules = {
        "app.main": "FastAPI 应用",
        "app.core.config": "配置模块",
        "app.api.auth": "认证 API",
        "app.api.users": "用户 API",
        "app.api.profile": "画像 API",
        "app.api.wardrobe": "衣橱 API",
        "app.api.analysis": "分析 API",
        "app.services.auth": "认证服务",
        "app.ml.image_recognizer": "图像识别",
        "app.ml.feature_extractor": "特征提取",
    }

    failed = []
    for module, description in modules.items():
        try:
            __import__(module)
            print(f"  ✓ {module:30} - {description}")
        except Exception as e:
            print(f"  ✗ {module:30} - {description} ({str(e)[:30]}...)")
            failed.append(module)

    if failed:
        print(f"\n  {len(failed)} 个模块导入失败")
        return False

    print(f"  ✓ 所有 {len(modules)} 个核心模块可以导入")
    return True


def check_api_endpoints():
    """检查 API 端点配置"""
    print("\n[5/5] 检查 API 端点配置...")

    try:
        from app.main import app

        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method != "HEAD":
                        routes.append(f"{method} {route.path}")

        print(f"  ✓ 已配置 {len(routes)} 个 API 端点")

        # 显示前 10 个端点
        print("\n  主要端点:")
        for route in sorted(routes)[:10]:
            print(f"    - {route}")

        if len(routes) > 10:
            print(f"    ... 还有 {len(routes) - 10} 个端点")

        return True

    except Exception as e:
        print(f"  ✗ 无法加载 API 端点: {e}")
        return False


def main():
    """运行所有检查"""
    print("=" * 60)
    print("后端配置快速检查")
    print("=" * 60)

    checks = [
        check_python_version,
        check_dependencies,
        check_config_files,
        check_core_modules,
        check_api_endpoints,
    ]

    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            print(f"\n  ✗ 检查失败: {e}")
            results.append(False)

    # 总结
    print("\n" + "=" * 60)
    print("检查总结")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"\n通过: {passed}/{total} 项检查")

    if passed == total:
        print("\n✅ 所有检查通过！后端配置正确。")
        print("\n下一步:")
        print("  1. 启动服务: python run.py")
        print("  2. 访问文档: http://localhost:8000/docs")
        print("  3. 运行测试: pytest -v")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 项检查失败，请查看上面的详细信息。")
        print("\n故障排查:")
        print("  1. 确保虚拟环境已激活")
        print("  2. 安装依赖: pip install -r requirements.txt")
        print("  3. 查看详细指南: TESTING_GUIDE.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
