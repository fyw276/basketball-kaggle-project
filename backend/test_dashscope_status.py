#!/usr/bin/env python
"""
测试 DashScope 配置状态
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def test_dashscope_import():
    """测试 dashscope 包是否已安装"""
    print("=" * 60)
    print("测试 1: 检查 dashscope 包")
    print("=" * 60)
    try:
        from dashscope.aigc.image_synthesis import ImageSynthesis
        from dashscope.common.constants import TaskStatus

        print("✓ dashscope 包已安装")
        return True
    except ImportError as e:
        print(f"✗ dashscope 包未安装: {e}")
        print("\n解决方案:")
        print("  pip install 'dashscope>=1.20.0,<2.0.0'")
        print("  或运行: install_dashscope.bat (Windows) / install_dashscope.sh (Linux/Mac)")
        return False


def test_config():
    """测试配置"""
    print("\n" + "=" * 60)
    print("测试 2: 检查配置")
    print("=" * 60)
    try:
        from app.core.config import settings

        enabled = getattr(settings, "DASHSCOPE_TRYON_ENABLED", False)
        api_key = getattr(settings, "DASHSCOPE_API_KEY", None) or ""

        print(f"DASHSCOPE_TRYON_ENABLED: {enabled}")
        if api_key:
            masked_key = api_key[:10] + "..." + api_key[-4:] if len(api_key) > 14 else "***"
            print(f"DASHSCOPE_API_KEY: {masked_key}")
        else:
            print("DASHSCOPE_API_KEY: 未设置")

        if enabled and api_key:
            print("✓ 配置正确")
            return True
        else:
            print("✗ 配置不完整")
            if not enabled:
                print("\n解决方案: 在 .env 文件中设置 DASHSCOPE_TRYON_ENABLED=true")
            if not api_key:
                print("\n解决方案: 在 .env 文件中设置 DASHSCOPE_API_KEY=your-api-key")
            return False
    except Exception as e:
        print(f"✗ 配置检查失败: {e}")
        return False


def test_bailian_client():
    """测试百炼客户端"""
    print("\n" + "=" * 60)
    print("测试 3: 检查百炼客户端")
    print("=" * 60)
    try:
        from app.services.bailian_tryon_client import _bailian_configured

        configured = _bailian_configured()
        if configured:
            print("✓ 百炼客户端配置正确")
            return True
        else:
            print("✗ 百炼客户端未正确配置")
            return False
    except Exception as e:
        print(f"✗ 百炼客户端检查失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("虚拟试衣功能诊断工具")
    print("=" * 60 + "\n")

    results = []

    # 测试1: dashscope包
    results.append(("dashscope包", test_dashscope_import()))

    # 测试2: 配置
    results.append(("配置", test_config()))

    # 测试3: 百炼客户端
    results.append(("百炼客户端", test_bailian_client()))

    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)

    all_passed = all(result[1] for result in results)

    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有检查通过！虚拟试衣功能应该可以正常使用。")
        print("\n下一步:")
        print("1. 重启后端服务")
        print("2. 在Flutter应用中测试虚拟试衣功能")
    else:
        print("✗ 部分检查失败，请按照上述提示修复问题。")
        print("\n常见解决方案:")
        print("1. 安装 dashscope: pip install 'dashscope>=1.20.0,<2.0.0'")
        print("2. 配置 .env 文件:")
        print("   DASHSCOPE_TRYON_ENABLED=true")
        print("   DASHSCOPE_API_KEY=your-api-key-here")
        print("3. 重启后端服务")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
