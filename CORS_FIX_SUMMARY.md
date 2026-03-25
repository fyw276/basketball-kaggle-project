# CORS 修复总结

## 问题诊断

### 原始问题
用户无法在 Flutter Web 中登录，使用凭据：
- 用户名: `manual_test_user`
- 邮箱: `manual@test.com`
- 密码: `Test123456`

### 根本原因
1. **CORS 限制**: 后端只允许特定端口（3000, 8080, 8000），但 Flutter Web 使用随机端口（如 50850）
2. **密码验证**: 密码 `Test123456` 缺少特殊字符，不符合后端要求

## 修复方案

### 1. 后端 CORS 配置更新

#### 修改的文件

**backend/.env**
```env
# 添加新配置
CORS_ALLOW_ALL_LOCALHOST=True
```

**backend/app/core/config.py**
```python
# 添加新字段
CORS_ALLOW_ALL_LOCALHOST: bool = Field(
    default=True,
    description="Allow all localhost ports (useful for Flutter Web development)",
)
```

**backend/app/main.py**
```python
# 使用正则表达式允许所有 localhost 端口
if settings.CORS_ALLOW_ALL_LOCALHOST:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

### 2. 密码要求说明

后端密码验证规则（在 `backend/app/services/auth.py`）：
- 最少 8 个字符
- 必须包含字母
- 必须包含数字
- 必须包含特殊字符

**推荐密码**: `Test123!@#`

## 重启指南

### 步骤 1: 重启后端

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 步骤 2: 测试 CORS 配置（可选）

```bash
cd backend
python test_cors_fix.py
```

### 步骤 3: 重启 Flutter Web

```bash
cd mobile
flutter run -d chrome
```

## 测试验证

### 方法 1: Flutter Web UI 测试

1. 打开 Flutter Web（例如 `http://localhost:50850`）
2. 注册新用户：
   - 用户名: `flutter_test`
   - 邮箱: `flutter@test.com`
   - 密码: `Test123!@#`
3. 登录验证

### 方法 2: PowerShell API 测试

```powershell
# 注册
$body = @{
    username = "api_test_user"
    email = "api@test.com"
    password = "Test123!@#"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/register" -Method Post -Body $body -ContentType "application/json"

# 登录
$loginBody = @{
    username = "api_test_user"
    password = "Test123!@#"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" -Method Post -Body $loginBody -ContentType "application/json"
Write-Host "Token: $($response.access_token)"
```

## 技术细节

### CORS 正则表达式解析

```python
allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?"
```

匹配规则：
- `http://localhost` - 无端口
- `http://localhost:3000` - 指定端口
- `http://localhost:50850` - Flutter Web 随机端口
- `http://127.0.0.1:8000` - IP 地址形式

### 为什么 Flutter Web 使用随机端口？

Flutter Web 在开发模式下会自动选择可用端口，避免端口冲突。这与 React、Vue 等框架不同（它们通常使用固定端口）。

## 生产环境配置

**重要**: 在生产环境中，必须禁用通配符 CORS：

```env
# .env (生产环境)
CORS_ALLOW_ALL_LOCALHOST=False
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

## 故障排查

### 问题 1: 仍然看到 CORS 错误

检查清单：
- [ ] 后端已重启
- [ ] Flutter Web 已重启
- [ ] 浏览器缓存已清除
- [ ] 检查后端日志确认配置已加载

### 问题 2: 密码验证失败

确保密码包含：
- [ ] 至少 8 个字符
- [ ] 大写字母
- [ ] 小写字母
- [ ] 数字
- [ ] 特殊字符（`!@#$%^&*` 等）

### 问题 3: 后端无法启动

检查：
```bash
# 检查端口占用
netstat -ano | findstr :8000

# 如果端口被占用，终止进程
taskkill /PID <进程ID> /F
```

## 验证成功标志

### 后端日志应显示：
```
INFO:     Starting Smart Outfit Assistant v1.0.0
INFO:     Environment: development
INFO:     Debug mode: True
```

### Flutter 控制台应显示：
```
✓ Built web/main.dart.js
Launching lib/main.dart on Chrome in debug mode...
Running on http://localhost:50850
```

### 浏览器 Network 标签应显示：
- 请求状态: `200 OK`
- Response Headers 包含: `Access-Control-Allow-Origin: http://localhost:50850`

## 相关文件

- `backend/.env` - 环境配置
- `backend/app/core/config.py` - 应用配置
- `backend/app/main.py` - CORS 中间件
- `mobile/lib/core/services/api_client.dart` - API 客户端
- `backend/test_cors_fix.py` - CORS 测试脚本
- `FLUTTER_LOGIN_FIX.md` - 详细修复指南

## 下一步

修复完成后，可以继续开发：
1. ✅ 用户注册和登录
2. ⏭️ 用户画像创建
3. ⏭️ 衣橱管理功能
4. ⏭️ 图像识别和分析
5. ⏭️ 搭配推荐功能

## 总结

通过配置 CORS 正则表达式，后端现在可以接受来自任何 localhost 端口的请求，完美支持 Flutter Web 的开发模式。同时明确了密码要求，避免用户使用不符合规则的密码。
