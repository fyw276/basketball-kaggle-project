"""
ReDoc 修复脚本

这个脚本会修改 main.py，添加自定义 ReDoc HTML 以解决 CDN 加载问题
"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def fix_redoc():
    """修复 ReDoc 配置"""
    main_py_path = Path(__file__).parent / "app" / "main.py"

    print("=" * 60)
    print("ReDoc 修复脚本")
    print("=" * 60)
    print()

    # 读取当前 main.py
    with open(main_py_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已经有自定义 ReDoc
    if "custom_redoc_html" in content:
        print("✓ ReDoc 已经配置了自定义 HTML")
        print()
        print("如果仍然有问题，请尝试：")
        print("1. 清除浏览器缓存")
        print("2. 使用无痕模式访问")
        print("3. 检查网络连接")
        return

    # 查找插入位置（在 health_check 端点之后）
    insert_marker = '@app.get("/health")'
    if insert_marker not in content:
        print("✗ 无法找到插入位置")
        print("请手动添加自定义 ReDoc HTML")
        return

    # 准备要插入的代码
    custom_redoc_code = '''

@app.get("/redoc-custom", include_in_schema=False)
async def custom_redoc_html():
    """
    Custom ReDoc HTML with multiple CDN fallbacks

    This endpoint provides a custom ReDoc page that tries multiple CDN sources
    to ensure ReDoc loads even if the default CDN is blocked or slow.
    """
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Smart Outfit Assistant - API Documentation</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                margin: 0;
                padding: 0;
            }
            #loading {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-family: Arial, sans-serif;
                font-size: 18px;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div id="loading">正在加载 API 文档...</div>
        <redoc spec-url="/openapi.json"></redoc>

        <script>
            // Try multiple CDN sources
            const cdnSources = [
                'https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js',
                'https://unpkg.com/redoc@latest/bundles/redoc.standalone.js',
                'https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js'
            ];

            let currentIndex = 0;

            function loadScript(src) {
                return new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = src;
                    script.onload = resolve;
                    script.onerror = reject;
                    document.body.appendChild(script);
                });
            }

            async function tryLoadRedoc() {
                for (let i = 0; i < cdnSources.length; i++) {
                    try {
                        console.log('Trying CDN:', cdnSources[i]);
                        await loadScript(cdnSources[i]);
                        document.getElementById('loading').style.display = 'none';
                        console.log('ReDoc loaded successfully from:', cdnSources[i]);
                        return;
                    } catch (error) {
                        console.warn('Failed to load from:', cdnSources[i]);
                        if (i === cdnSources.length - 1) {
                            document.getElementById('loading').innerHTML =
                                '无法加载 API 文档。<br><br>' +
                                '请尝试：<br>' +
                                '1. 检查网络连接<br>' +
                                '2. 使用 <a href="/docs">Swagger UI</a> 代替<br>' +
                                '3. 清除浏览器缓存后重试';
                        }
                    }
                }
            }

            tryLoadRedoc();
        </script>
    </body>
    </html>
    """)
'''

    # 找到 health_check 函数的结束位置
    health_check_end = content.find("}", content.find(insert_marker))
    if health_check_end == -1:
        print("✗ 无法找到插入位置")
        return

    # 插入自定义 ReDoc 代码
    new_content = (
        content[: health_check_end + 1] + custom_redoc_code + content[health_check_end + 1 :]
    )

    # 备份原文件
    backup_path = main_py_path.with_suffix(".py.backup")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✓ 已备份原文件到: {backup_path}")

    # 写入新内容
    with open(main_py_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"✓ 已更新: {main_py_path}")

    print()
    print("=" * 60)
    print("修复完成！")
    print("=" * 60)
    print()
    print("下一步:")
    print("1. 重启后端服务: python run.py")
    print("2. 访问新的 ReDoc 页面: http://localhost:8000/redoc-custom")
    print("3. 如果仍有问题，访问 Swagger UI: http://localhost:8000/docs")
    print()
    print("注意:")
    print("- 原始 /redoc 端点仍然可用")
    print("- 新的 /redoc-custom 端点使用多个 CDN 备份")
    print("- 如果需要恢复，使用备份文件: main.py.backup")


if __name__ == "__main__":
    try:
        fix_redoc()
    except Exception as e:
        print(f"✗ 修复失败: {e}")
        sys.exit(1)
