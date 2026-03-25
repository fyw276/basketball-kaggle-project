# Flutter Web 登录测试指南

## ✅ 后端修复完成

bcrypt 版本问题已修复，后端服务器正常运行。

### 修复内容
1. ✅ bcrypt 降级到 4.0.1 版本（解决 `__about__` 属性错误）
2. ✅ 后端服务器已重启并正常运行
3. ✅ 注册和登录 API 测试通过
4. ✅ CORS 配置支持所有 localhost 端口（包括 Flutter Web）

## 🧪 后端测试结果

```powershell
# 注册测试 - ✅ 成功
username   : test_user_new
email      : test_new@example.com
user_id    : 3069d8d6-b33b-40ce-80b2-a60483f4c19e
is_active  : True

# 登录测试 - ✅ 成功
access_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## 📱 Flutter Web 测试步骤

### 1. 确认后端运行状态

后端服务器已在运行：
- 地址: `http://localhost:8000`
- 状态: ✅ 正常运行
- CORS: ✅ 已配置支持所有 localhost 端口

### 2. 启动 Flutter Web 应用

```bash
cd mobile
flutter run -d chrome
```

### 3. 测试注册功能

使用以下信息注册新用户：

```
用户名: flutter_test_user
邮箱: flutter@test.com
密码: Test123!@#
```

**重要**: 密码必须包含：
- 至少 8 个字符
- 字母（大小写）
- 数字
- 特殊字符（如 !@#）

### 4. 测试登录功能

注册成功后，使用相同的用户名和密码登录：

```
用户名: flutter_test_user
密码: Test123!@#
```

## 🔍 故障排查

### 如果注册失败

1. **打开浏览器开发者工具**（F12）
2. **查看 Console 标签页**，检查是否有错误信息
3. **查看 Network 标签页**：
   - 找到 `/api/v1/auth/register` 请求
   - 查看 Request Headers（确认 Content-Type）
   - 查看 Request Payload（确认数据格式）
   - 查看 Response（查看错误信息）

### 常见错误及解决方案

#### 错误 1: 网络连接失败
```
DioException: Connection refused
```

**解决方案**:
- 确认后端服务器正在运行
- 检查 API 地址是否正确（应为 `http://localhost:8000/api/v1`）

#### 错误 2: CORS 错误
```
Access to XMLHttpRequest has been blocked by CORS policy
```

**解决方案**:
- 后端已配置 CORS，此错误不应出现
- 如果出现，请提供完整错误信息

#### 错误 3: 密码格式错误
```json
{
  "error": {
    "message": "Password must be at least 8 characters and contain letters, numbers, and special characters"
  }
}
```

**解决方案**:
- 使用符合要求的密码，例如: `Test123!@#`

#### 错误 4: 用户名已存在
```json
{
  "error": {
    "message": "Username already exists"
  }
}
```

**解决方案**:
- 使用不同的用户名
- 或直接使用该用户名登录

### 如果登录失败

#### 错误 1: 用户名或密码错误
```json
{
  "error": {
    "message": "Incorrect username or password"
  }
}
```

**解决方案**:
- 确认用户名和密码输入正确
- 密码区分大小写
- 确保使用注册时的完整密码

#### 错误 2: 401 Unauthorized
```
Status: 401
```

**解决方案**:
- 这通常表示密码验证失败
- 重新注册一个新用户进行测试

## 📊 API 端点测试

### 手动测试注册 API

```powershell
$body = @{
    username = 'manual_test'
    email = 'manual@test.com'
    password = 'Test123!@#'
} | ConvertTo-Json

Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/auth/register' `
    -Method Post `
    -Body $body `
    -ContentType 'application/json'
```

### 手动测试登录 API

```powershell
$body = @{
    username = 'manual_test'
    password = 'Test123!@#'
} | ConvertTo-Json

Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/auth/login' `
    -Method Post `
    -Body $body `
    -ContentType 'application/json'
```

## 🎯 预期结果

### 注册成功
- 返回用户信息（username, email, user_id, created_at, is_active）
- 自动跳转到登录页面

### 登录成功
- 返回 JWT access_token
- Token 自动保存到 SharedPreferences
- 自动跳转到主页（Home Screen）

## 📝 调试信息收集

如果问题仍然存在，请提供以下信息：

1. **浏览器控制台错误**（Console 标签页）
2. **网络请求详情**（Network 标签页）
   - Request URL
   - Request Method
   - Request Headers
   - Request Payload
   - Response Status
   - Response Body
3. **Flutter 应用运行的端口号**（例如: localhost:50850）

## 🔧 后端配置信息

当前后端配置：
- bcrypt 版本: 4.0.1 ✅
- CORS 配置: 允许所有 localhost 端口 ✅
- API 基础地址: http://localhost:8000/api/v1 ✅
- 服务器状态: 运行中 ✅

## 📞 下一步

1. 启动 Flutter Web 应用
2. 尝试注册新用户
3. 如果遇到问题，打开浏览器开发者工具查看详细错误
4. 提供错误信息以便进一步诊断
