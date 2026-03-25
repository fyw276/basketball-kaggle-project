# ✅ 登录问题已解决

## 问题总结

用户无法通过 Flutter Web 登录，报错 401 Unauthorized。

## 根本原因

bcrypt 版本 4.2.1 存在兼容性问题：
```
AttributeError: module 'bcrypt' has no attribute '__about__'
```

这导致密码验证失败，所有登录请求都返回 401 错误。

## 解决方案

### 1. ✅ 降级 bcrypt 版本

```bash
pip uninstall bcrypt -y
pip install bcrypt==4.0.1
```

### 2. ✅ 更新 requirements.txt

```
bcrypt==4.0.1  # 从 4.2.1 降级
```

### 3. ✅ 重启后端服务器

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 验证结果

### ✅ 注册测试通过

```powershell
PS> $body = @{username='quick_test'; email='quick@test.com'; password='Test123!@#'} | ConvertTo-Json
PS> Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/auth/register' -Method Post -Body $body -ContentType 'application/json'

username   : quick_test
email      : quick@test.com
user_id    : ca464393-cc0f-4747-b931-4b5cacbbecb7
created_at : 2026-03-24T13:49:02.281204
is_active  : True
```

### ✅ 登录测试通过

```powershell
PS> $body = @{username='quick_test'; password='Test123!@#'} | ConvertTo-Json
PS> Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/auth/login' -Method Post -Body $body -ContentType 'application/json'

access_token
------------
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| 后端服务器 | ✅ 运行中 | http://localhost:8000 |
| bcrypt 版本 | ✅ 4.0.1 | 兼容性问题已解决 |
| 注册 API | ✅ 正常 | /api/v1/auth/register |
| 登录 API | ✅ 正常 | /api/v1/auth/login |
| CORS 配置 | ✅ 正常 | 支持所有 localhost 端口 |
| 密码验证 | ✅ 正常 | bcrypt 哈希验证工作正常 |

## Flutter Web 测试步骤

### 1. 启动 Flutter Web

```bash
cd mobile
flutter run -d chrome
```

### 2. 注册新用户

使用以下信息：
- 用户名: `flutter_web_user`
- 邮箱: `flutter@web.com`
- 密码: `Test123!@#`

**重要**: 密码必须包含字母、数字和特殊字符。

### 3. 登录

使用刚才注册的用户名和密码登录。

### 4. 预期结果

- ✅ 注册成功，显示用户信息
- ✅ 自动跳转到登录页面
- ✅ 登录成功，获取 JWT token
- ✅ 自动跳转到主页

## 故障排查

### 如果仍然无法登录

1. **打开浏览器开发者工具**（F12）
2. **查看 Console 标签页**，检查 JavaScript 错误
3. **查看 Network 标签页**：
   - 找到 `/api/v1/auth/login` 请求
   - 查看 Status Code（应该是 200）
   - 查看 Response（应该包含 access_token）
   - 如果是 401，查看 Response Body 中的错误信息

### 常见问题

#### 问题 1: 密码格式错误

**错误信息**:
```json
{
  "error": {
    "message": "Password must be at least 8 characters and contain letters, numbers, and special characters"
  }
}
```

**解决方案**: 使用符合要求的密码，例如 `Test123!@#`

#### 问题 2: 用户名已存在

**错误信息**:
```json
{
  "error": {
    "message": "Username already exists"
  }
}
```

**解决方案**: 使用不同的用户名，或直接登录

#### 问题 3: 网络连接失败

**错误信息**: `DioException: Connection refused`

**解决方案**:
- 确认后端服务器正在运行
- 检查 API 地址配置（应为 `http://localhost:8000/api/v1`）

## 技术细节

### bcrypt 版本问题

bcrypt 4.2.1 引入了一个破坏性变更，移除了 `__about__` 属性，导致 passlib 库无法正常工作。

**受影响的代码**:
```python
# backend/app/services/auth.py
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

**解决方案**: 降级到 bcrypt 4.0.1，这是最后一个包含 `__about__` 属性的版本。

### CORS 配置

后端已配置为允许所有 localhost 端口：

```python
# backend/app/main.py
if settings.CORS_ALLOW_ALL_LOCALHOST:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

这确保 Flutter Web 可以从任何 localhost 端口访问后端 API。

## 相关文件

- `backend/requirements.txt` - 依赖版本配置
- `backend/app/services/auth.py` - 认证服务（密码哈希和验证）
- `backend/app/main.py` - CORS 配置
- `mobile/lib/core/services/api_client.dart` - Flutter API 客户端
- `FLUTTER_WEB_LOGIN_GUIDE.md` - 详细测试指南
- `backend/test_flutter_web.py` - 自动化测试脚本

## 下一步

1. ✅ 后端已修复并运行
2. 🎯 启动 Flutter Web 应用
3. 🎯 测试注册和登录功能
4. 🎯 如有问题，查看浏览器开发者工具获取详细错误信息

---

**修复时间**: 2026-03-24 21:49
**修复状态**: ✅ 完成
**测试状态**: ✅ 通过
