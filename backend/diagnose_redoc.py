"""
ReDoc 问题诊断脚本

这个脚本会检查 ReDoc 无法加载的可能原因
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def diagnose_redoc():
    """诊断 ReDoc 问题"""
    print("=" * 60)
    print("ReDoc 问题诊断")
    print("=" * 60)
    print()

    issues = []
    suggestions = []

    # 1. 检查 FastAPI 配置
    print("[1/5] 检查 FastAPI 配置...")
    try:
        from app.main import app

        if app.redoc_url:
            print(f"  ✓ ReDoc URL 已配置: {app.redoc_url}")
        else:
            print("  ✗ ReDoc URL 未配置")
            issues.append("ReDoc URL 未配置")
            suggestions.append("在 FastAPI 初始化时设置 redoc_url='/redoc'")

        if app.openapi_url:
            print(f"  ✓ OpenAPI URL 已配置: {app.openapi_url}")
        else:
            print("  ✗ OpenAPI URL 未配置")
            issues.append("OpenAPI URL 未配置")
    except Exception as e:
        print(f"  ✗ 无法加载 FastAPI 应用: {e}")
        issues.append(f"FastAPI 应用加载失败: {e}")

    print()

    # 2. 检查 OpenAPI 规范
    print("[2/5] 检查 OpenAPI 规范...")
    try:
        from app.main import app

        openapi_schema = app.openapi()
        if openapi_schema:
            print("  ✓ OpenAPI 规范生成成功")
            print(f"    - 标题: {openapi_schema.get('info', {}).get('title', 'N/A')}")
            print(f"    - 版本: {openapi_schema.get('info', {}).get('version', 'N/A')}")
            print(f"    - 路径数量: {len(openapi_schema.get('paths', {}))}")
        else:
            print("  ✗ OpenAPI 规范为空")
            issues.append("OpenAPI 规范为空")
    except Exception as e:
        print(f"  ✗ 无法生成 OpenAPI 规范: {e}")
        issues.append(f"OpenAPI 规范生成失败: {e}")

    print()

    # 3. 测试 CDN 连接
    print("[3/5] 测试 CDN 连接...")
    cdn_urls = [
        "https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js",
        "https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js",
        "https://unpkg.com/redoc@latest/bundles/redoc.standalone.js",
    ]

    try:
        import urllib.request

        for url in cdn_urls:
            try:
                response = urllib.request.urlopen(url, timeout=5)
                if response.status == 200:
                    print(f"  ✓ 可以访问: {url}")
                else:
                    print(f"  ✗ 无法访问: {url} (状态码: {response.status})")
                    issues.append(f"CDN 无法访问: {url}")
            except Exception as e:
                print(f"  ✗ 无法访问: {url}")
                print(f"    错误: {str(e)[:50]}...")
                issues.append(f"CDN 连接失败: {url}")
    except ImportError:
        print("  ⚠ 无法测试 CDN 连接（urllib 不可用）")

    print()

    # 4. 检查端口和服务
    print("[4/5] 检查服务状态...")
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", 8000))
        if result == 0:
            print("  ✓ 端口 8000 正在监听")
        else:
            print("  ✗ 端口 8000 未监听")
            issues.append("后端服务未运行")
            suggestions.append("运行: python run.py")
        sock.close()
    except Exception as e:
        print(f"  ✗ 无法检查端口: {e}")

    print()

    # 5. 检查备用端点
    print("[5/5] 检查备用端点...")
    try:
        from app.main import app

        routes = [route.path for route in app.routes if hasattr(route, "path")]
        if "/redoc-alt" in routes:
            print("  ✓ 备用 ReDoc 端点已配置: /redoc-alt")
            suggestions.append("尝试访问: http://127.0.0.1:8010/redoc-alt")
        else:
            print("  ⚠ 备用 ReDoc 端点未配置")
            suggestions.append("运行: python fix_redoc.py 添加备用端点")
    except Exception as e:
        print(f"  ✗ 无法检查端点: {e}")

    print()

    # 总结
    print("=" * 60)
    print("诊断总结")
    print("=" * 60)
    print()

    if not issues:
        print("✅ 未发现明显问题")
        print()
        print("ReDoc 空白可能是由于：")
        print("1. 浏览器缓存问题 - 清除缓存后重试")
        print("2. 浏览器扩展干扰 - 尝试无痕模式")
        print("3. 网络延迟 - 等待更长时间加载")
        print("4. 浏览器控制台有错误 - 按 F12 查看")
    else:
        print(f"⚠️  发现 {len(issues)} 个问题：")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")

    print()

    if suggestions:
        print("💡 建议操作：")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"  {i}. {suggestion}")

    print()
    print("其他解决方案：")
    print("  • 使用 Swagger UI 代替: http://127.0.0.1:8010/docs")
    print("  • 使用备用 ReDoc: http://127.0.0.1:8010/redoc-alt")
    print("  • 查看详细指南: REDOC_FIX.md")
    print()


if __name__ == "__main__":
    try:
        diagnose_redoc()
    except Exception as e:
        print(f"✗ 诊断失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
