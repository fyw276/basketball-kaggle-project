# Flutter Web 登录问题修复指南

## 问题原因

Flutter Web 在开发模式下使用随机端口（例如 `localhost:50850`），但后端 CORS 配置只允许特定端口（3000, 8080, 8000），导致跨域请求被阻止。

## 修复内容

### 1. 后端 CORS 配置更新

已更新以下文件以支持所有 localhost 端口：

- `backend/.env`: 添加 `CORS_ALLOW_ALL_LOCALHOST=True`
- `backend/app/core/config.py`: 添加 `CORS_ALLOW_ALL_LOCALHOST` 配置项
- `backend/app/main.py`: 使用正则表达式允许所有 localhost 端口

### 2. 密码要求

后端密码验证要求：
- 最少 8 个字符
- 必须包含字母、数字和特殊字符

**推荐测试密码**: `Test123!@#`（包含大小写字母、数字和特殊字符）

## 重启步骤

### 1. 重启后端服务

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 重启 Flutter Web 应用

在 Flutter 项目目录：

```bash
cd mobile
flutter run -d chrome
```

## 测试步骤

### 方法 1: 使用 Flutter Web 界面

1. 打开 Flutter Web 应用（例如 `http://localhost:50850`）
2. 点击 "注册" 按钮
3. 填写注册信息：
   - 用户名: `flutter_test_user`
   - 邮箱: `flutter@test.com`
   - 密码: `Test123!@#`（必须包含特殊字符）
4. 点击注册
5. 注册成功后，使用相同凭据登录

### 方法 2: 使用 PowerShell 测试 API

```powershell
# 1. 注册用户
$registerBody = @{
    username = "flutter_test_user"
    email = "flutter@test.com"
    password = "Test123!@#"
} | ConvertTo-Json

$registerResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/register" -Method Post -Body $registerBody -ContentType "application/json"
Write-Host "注册成功: $($registerResponse | ConvertTo-Json)"

# 2. 登录获取 Token
$loginBody = @{
    username = "flutter_test_user"
    password = "Test123!@#"
} | ConvertTo-Json

$loginResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" -Method Post -Body $loginBody -ContentType "application/json"
Write-Host "登录成功，Token: $($loginResponse.access_token)"
```

## 验证 CORS 配置

检查后端日志，应该看到类似以下内容：

```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Starting Smart Outfit Assistant v1.0.0
INFO:     Environment: development
INFO:     Debug mode: True
INFO:     Application startup complete.
```

## 常见问题

### Q1: 仍然无法连接？

检查：
1. 后端是否正在运行（访问 `http://localhost:8000/health`）
2. Flutter Web 的控制台是否显示 CORS 错误
3. 后端日志是否显示请求到达

### Q2: 密码验证失败？

确保密码包含：
- 至少 8 个字符
- 大小写字母
- 数字
- 特殊字符（如 `!@#$%^&*`）

### Q3: 如何查看 Flutter Web 运行端口？

Flutter Web 启动时会在终端显示：
```
Launching lib/main.dart on Chrome in debug mode...
...
Running on http://localhost:50850
```

## 技术细节

### CORS 正则表达式

```python
allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?"
```

这个正则表达式允许：
- `http://localhost` (任意端口或无端口)
- `http://localhost:3000`
- `http://localhost:50850`
- `http://127.0.0.1:8000`
- 等等所有 localhost 变体

### 生产环境注意事项

在生产环境中，应该：
1. 设置 `CORS_ALLOW_ALL_LOCALHOST=False`
2. 在 `CORS_ORIGINS` 中明确指定允许的域名
3. 不要使用通配符或正则表达式

## 下一步

修复完成后，您可以：
1. 测试用户注册和登录功能
2. 测试用户画像创建
3. 测试衣橱管理功能
4. 测试图像识别和分析功能

如有问题，请查看：
- 后端日志: `backend/logs/app.log`
- Flutter 控制台输出
- 浏览器开发者工具的 Network 标签
