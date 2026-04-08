# ReDoc 空白页面问题修复指南

## 问题描述

访问 http://127.0.0.1:8010/redoc 时页面空白，但 Swagger UI (http://127.0.0.1:8010/docs) 正常工作。

## 可能的原因

1. **CDN 资源加载失败** - ReDoc 默认从 CDN 加载 JavaScript 和 CSS
2. **网络连接问题** - 无法访问 CDN 服务器
3. **浏览器缓存问题** - 缓存了错误的资源
4. **CORS 或安全策略** - 浏览器阻止了外部资源

## 解决方案

### 方案 1: 检查浏览器控制台（推荐首先尝试）

1. 在 ReDoc 页面按 `F12` 打开开发者工具
2. 切换到 "Console" (控制台) 标签
3. 刷新页面 (`Ctrl+F5` 或 `Cmd+Shift+R`)
4. 查看是否有错误信息，特别是：
   - `Failed to load resource`
   - `net::ERR_CONNECTION_REFUSED`
   - `CORS policy`
   - `Content Security Policy`

### 方案 2: 清除浏览器缓存

1. 按 `Ctrl+Shift+Delete` (Windows) 或 `Cmd+Shift+Delete` (Mac)
2. 选择清除缓存和 Cookie
3. 重新访问 http://127.0.0.1:8010/redoc

### 方案 3: 使用本地 ReDoc 资源

如果 CDN 无法访问，可以配置使用本地 ReDoc 资源：

```python
# 在 backend/app/main.py 中添加自定义 ReDoc HTML

from fastapi.responses import HTMLResponse

@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """Custom ReDoc HTML with local resources"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Smart Outfit Assistant - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                margin: 0;
                padding: 0;
            }
        </style>
    </head>
    <body>
        <redoc spec-url="/openapi.json"></redoc>
        <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """)
```

### 方案 4: 使用国内 CDN 镜像

如果是网络问题，可以使用国内 CDN：

```python
@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """Custom ReDoc HTML with China CDN"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Smart Outfit Assistant - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
        <redoc spec-url="/openapi.json"></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """)
```

### 方案 5: 完全禁用 ReDoc，只使用 Swagger UI

如果 ReDoc 不是必需的，可以禁用它：

```python
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="...",
    docs_url="/docs",
    redoc_url=None,  # 禁用 ReDoc
    openapi_url="/openapi.json",
)
```

### 方案 6: 验证 OpenAPI 规范

确保 OpenAPI 规范正确生成：

```bash
# 访问 OpenAPI JSON
curl http://127.0.0.1:8010/openapi.json

# 或在浏览器中访问
http://127.0.0.1:8010/openapi.json
```

如果 JSON 正确显示，说明问题在 ReDoc 前端加载。

## 快速测试

运行以下命令测试 ReDoc 是否可以加载：

```bash
# 测试 CDN 连接
curl -I https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js

# 测试备用 CDN
curl -I https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js
```

## 推荐操作步骤

1. **首先**：检查浏览器控制台错误信息
2. **然后**：清除浏览器缓存并刷新
3. **如果仍然失败**：使用方案 3 或 4 切换到备用 CDN
4. **最后**：如果不需要 ReDoc，使用方案 5 禁用它

## 注意事项

- Swagger UI 和 ReDoc 提供相同的 API 文档，只是展示方式不同
- Swagger UI 更适合交互式测试
- ReDoc 更适合阅读和展示
- 如果 Swagger UI 正常工作，说明后端 API 配置没有问题

## 验证修复

修复后，访问 http://127.0.0.1:8010/redoc 应该看到：
- 左侧：API 端点列表
- 右侧：详细的 API 文档
- 顶部：API 标题和版本信息

---

**需要帮助？** 请提供浏览器控制台的错误信息，我可以提供更具体的解决方案。
