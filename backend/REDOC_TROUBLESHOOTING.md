# ReDoc 空白页面故障排除

## 问题现象

访问 http://127.0.0.1:8010/redoc 时页面完全空白，但 Swagger UI 正常工作。

## 根本原因

ReDoc 页面空白通常是因为：

1. **CDN 资源无法加载** - ReDoc 的 JavaScript 文件从 CDN 加载失败
2. **网络限制** - 防火墙、代理或网络策略阻止了 CDN 访问
3. **浏览器缓存** - 缓存了损坏的资源

## 立即解决方案

### 方案 1: 使用 Swagger UI（推荐）✅

Swagger UI 和 ReDoc 提供相同的 API 文档，只是展示方式不同。

**直接使用 Swagger UI**：
```
http://127.0.0.1:8010/docs
```

**优点**：
- 功能更强大（可以直接测试 API）
- 不依赖外部 CDN
- 加载更快

### 方案 2: 检查浏览器控制台

1. 在 ReDoc 页面按 `F12` 打开开发者工具
2. 切换到 "Console" 标签
3. 刷新页面（`Ctrl+F5` 强制刷新）
4. 查看错误信息

**常见错误及解决方案**：

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `Failed to load resource: net::ERR_BLOCKED_BY_CLIENT` | 广告拦截器阻止 | 禁用广告拦截器 |
| `Failed to load resource: net::ERR_CONNECTION_REFUSED` | CDN 无法访问 | 使用方案 3 |
| `Failed to load resource: net::ERR_NAME_NOT_RESOLVED` | DNS 问题 | 检查网络连接 |
| `CORS policy` | 跨域问题 | 检查 CORS 配置 |

### 方案 3: 测试 HTML 响应

访问测试端点验证 HTML 响应是否正常：
```
http://127.0.0.1:8010/test-html
```

如果看到 "HTML Response Test" 页面，说明服务器配置正常，问题在 ReDoc 的 CDN 加载。

### 方案 4: 清除浏览器缓存

**Chrome/Edge**：
1. 按 `Ctrl+Shift+Delete`
2. 选择"缓存的图片和文件"
3. 时间范围选择"全部时间"
4. 点击"清除数据"
5. 重新访问 ReDoc

**Firefox**：
1. 按 `Ctrl+Shift+Delete`
2. 选择"缓存"
3. 点击"立即清除"
4. 重新访问 ReDoc

### 方案 5: 使用无痕模式

1. 按 `Ctrl+Shift+N` (Chrome) 或 `Ctrl+Shift+P` (Firefox)
2. 在无痕窗口访问 http://127.0.0.1:8010/redoc
3. 如果可以正常显示，说明是浏览器扩展或缓存问题

### 方案 6: 检查网络连接

测试是否可以访问 ReDoc CDN：

**Windows PowerShell**：
```powershell
Test-NetConnection cdn.redoc.ly -Port 443
```

**或在浏览器中直接访问**：
```
https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js
```

如果无法访问，说明网络有限制。

## 深度排查

### 步骤 1: 运行诊断脚本

```bash
cd backend
python diagnose_redoc.py
```

这会检查：
- FastAPI 配置
- OpenAPI 规范
- CDN 连接
- 服务状态

### 步骤 2: 检查服务器日志

查看后端服务器的控制台输出，看是否有错误信息。

### 步骤 3: 验证 OpenAPI 规范

访问 OpenAPI JSON 端点：
```
http://127.0.0.1:8010/openapi.json
```

应该看到完整的 JSON 规范。如果这个端点有问题，ReDoc 也无法工作。

## 为什么 Swagger UI 可以工作但 ReDoc 不行？

**Swagger UI**：
- 使用本地打包的 JavaScript 文件
- 不依赖外部 CDN
- 更稳定

**ReDoc**：
- 默认从 CDN 加载 JavaScript
- 需要访问外部资源
- 可能被网络限制

## 最终建议

### 如果你需要美观的文档展示：
使用 Swagger UI，它同样提供清晰的 API 文档。

### 如果你必须使用 ReDoc：
1. 检查网络和防火墙设置
2. 尝试使用 VPN 或代理
3. 联系网络管理员解除 CDN 限制

### 如果是开发环境：
Swagger UI 完全够用，它还支持直接测试 API，比 ReDoc 更实用。

## 快速参考

| 端点 | 用途 | 状态 |
|------|------|------|
| http://127.0.0.1:8010/docs | Swagger UI（推荐） | ✅ 正常 |
| http://127.0.0.1:8010/redoc | ReDoc | ❌ 空白 |
| http://127.0.0.1:8010/test-html | HTML 测试 | ✅ 测试用 |
| http://127.0.0.1:8010/openapi.json | OpenAPI 规范 | ✅ 正常 |

## 总结

**最简单的解决方案**：使用 Swagger UI 代替 ReDoc

**访问**：http://127.0.0.1:8010/docs

Swagger UI 提供：
- ✅ 完整的 API 文档
- ✅ 交互式测试功能
- ✅ 更好的兼容性
- ✅ 不依赖外部 CDN

---

**需要更多帮助？** 运行 `python diagnose_redoc.py` 获取详细诊断信息。
