"""
安装验证脚本
检查所有依赖是否正确安装
"""
import sys


def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    print(f"✓ Python 版本: {version.major}.{version.minor}.{version.micro}")
    if version.major == 3 and version.minor >= 11:
        print("  ✓ Python 版本符合要求 (>= 3.11)")
        return True
    else:
        print("  ✗ Python 版本过低，需要 >= 3.11")
        return False


def check_package(package_name, import_name=None):
    """检查包是否已安装"""
    if import_name is None:
        import_name = package_name
    
    try:
        module = __import__(import_name)
        version = getattr(module, "__version__", "未知版本")
        print(f"✓ {package_name}: {version}")
        return True
    except ImportError:
        print(f"✗ {package_name}: 未安装")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("智能穿搭助手 - 安装验证")
    print("=" * 60)
    print()
    
    # 检查 Python 版本
    print("1. 检查 Python 版本")
    print("-" * 60)
    python_ok = check_python_version()
    print()
    
    # 检查核心依赖
    print("2. 检查核心依赖")
    print("-" * 60)
    
    packages = [
        ("FastAPI", "fastapi"),
        ("Uvicorn", "uvicorn"),
        ("Pydantic", "pydantic"),
        ("Pydantic Settings", "pydantic_settings"),
        ("Python-dotenv", "dotenv"),
        ("Loguru", "loguru"),
        ("HTTPX", "httpx"),
    ]
    
    core_ok = all(check_package(name, import_name) for name, import_name in packages)
    print()
    
    # 检查可选依赖（数据库、机器学习等）
    print("3. 检查可选依赖（如果未安装，后续任务会需要）")
    print("-" * 60)
    
    optional_packages = [
        ("SQLAlchemy", "sqlalchemy"),
        ("Alembic", "alembic"),
        ("Redis", "redis"),
        ("Pillow", "PIL"),
        ("NumPy", "numpy"),
        ("TensorFlow", "tensorflow"),
    ]
    
    for name, import_name in optional_packages:
        check_package(name, import_name)
    print()
    
    # 检查开发工具
    print("4. 检查开发工具")
    print("-" * 60)
    
    dev_packages = [
        ("Pytest", "pytest"),
        ("Black", "black"),
        ("isort", "isort"),
    ]
    
    for name, import_name in dev_packages:
        check_package(name, import_name)
    print()
    
    # 总结
    print("=" * 60)
    if python_ok and core_ok:
        print("✓ 核心依赖安装成功！可以启动开发服务器了。")
        print()
        print("下一步:")
        print("  1. 运行 'python run.py' 启动服务器")
        print("  2. 访问 http://localhost:8000/docs 查看 API 文档")
    else:
        print("✗ 安装不完整，请运行:")
        print("  pip install --upgrade pip")
        print("  pip install -r requirements.txt")
    print("=" * 60)


if __name__ == "__main__":
    main()
