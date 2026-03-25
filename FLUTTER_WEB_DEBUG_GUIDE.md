# 🔍 Flutter Web 登录问题调试指南

## 问题现象

从截图看到：
- ✅ Flutter Web 应用已启动 (localhost:49667)
- ❌ 注册失败: 400 (Bad Request)
- ❌ 登录失败: 401 (Unauthorized)

## 可能的原因

### 400 错误 (注册失败)

可能原因：
1. **用户名已存在** - 之前已经注册过这个用户名
2. **邮箱已存在** - 之前已经注册过这个邮箱
3. **数据格式错误** - 请求数据不符合要求

### 401 错误 (登录失败)

可能原因：
1. **用户不存在** - 注册失败导致用户未创建
2. **密码错误** - 输入的密码与注册时不一致
3. **用户未激活** - 用户账号被禁用

## 🔧 解决方案

### 方案 1: 使用全新的用户名和邮箱

**重要**: 每次测试都使用不同的用户名和邮箱

```
用户名: flutter_web_20260324  (加上日期时间)
邮箱: flutter20260324@test.com
密码: Test123!@#
```

### 方案 2: 查看浏览器详细错误

1. **打开开发者工具** (F12)
2. **切换到 Network 标签页**
3. **点击注册按钮**
4. **找到 `register` 请求**
5. **查看以下信息**:

#### Request (请求)
```
URL: http://localhost:8000/api/v1/auth/register
Method: POST
Headers:
  Content-Type: application/json
Payload:
  {
    "username": "...",
    "email": "...",
    "password": "..."
  }
```

#### Response (响应)
```json
{
  "error": {
    "type": "...",
    "message": "具体错误信息",
    "status_code": 400
  }
}
```

### 方案 3: 清空数据库中的测试用户

如果你一直使用相同的用户名测试，可以清空数据库：

```bash
cd backend
python -c "from app.db.session import SessionLocal; from app.models.user import User; db = SessionLocal(); db.query(User).filter(User.username.like('flutter%')).delete(); db.commit(); print('已删除所有 flutter 开头的测试用户')"
```

### 方案 4: 使用后端测试脚本创建用户

```bash
cd backend
python test_flutter_web.py
```

这会创建一个新的测试用户并显示凭据，然后你可以直接在 Flutter Web 中登录。

## 📊 详细调试步骤

### 步骤 1: 确认后端正在运行

打开浏览器访问: http://localhost:8000/health

应该看到:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### 步骤 2: 在浏览器中测试注册 API

打开浏览器开发者工具的 Console 标签页，运行:

```javascript
fetch('http://localhost:8000/api/v1/auth/register', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    username: 'browser_test_' + Date.now(),
    email: 'browser_' + Date.now() + '@test.com',
    password: 'Test123!@#'
  })
})
.then(response => response.json())
.then(data => console.log('注册结果:', data))
.catch(error => console.error('错误:', error));
```

### 步骤 3: 查看 Flutter 代码发送的数据

检查 `mobile/lib/core/services/api_client.dart` 中的 `register` 方法：

```dart
Future<Map<String, dynamic>> register({
  required String username,
  required String email,
  required String password,
}) async {
  final response = await _dio.post('/auth/register', data: {
    'username': username,
    'email': email,
    'password': password,
  });
  return response.data;
}
```

确认数据格式正确。

### 步骤 4: 添加调试日志

在 Flutter 代码中添加日志输出，查看实际发送的数据：

```dart
// 在 api_client.dart 的 register 方法中添加
print('注册数据: username=$username, email=$email, password=${password.length}个字符');
```

## 🎯 推荐的测试流程

### 1. 使用唯一的用户名

每次测试都使用不同的用户名，避免冲突：

```
用户名: test_${当前时间戳}
邮箱: test_${当前时间戳}@example.com
密码: Test123!@#
```

### 2. 先在浏览器 Console 测试

在 Flutter Web 的浏览器中，先用 JavaScript 测试注册：

```javascript
// 生成唯一用户名
const timestamp = Date.now();
const username = 'flutter_' + timestamp;
const email = 'flutter_' + timestamp + '@test.com';

// 测试注册
fetch('http://localhost:8000/api/v1/auth/register', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    username: username,
    email: email,
    password: 'Test123!@#'
  })
})
.then(r => r.json())
.then(d => {
  console.log('✅ 注册成功:', d);

  // 测试登录
  return fetch('http://localhost:8000/api/v1/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      username: username,
      password: 'Test123!@#'
    })
  });
})
.then(r => r.json())
.then(d => console.log('✅ 登录成功:', d))
.catch(e => console.error('❌ 错误:', e));
```

### 3. 如果浏览器测试成功

说明后端 API 正常，问题在 Flutter 代码中。检查：
- 数据格式是否正确
- 是否有额外的验证逻辑
- 错误处理是否正确

### 4. 如果浏览器测试也失败

说明是 CORS 或后端配置问题。检查：
- 后端是否正在运行
- CORS 配置是否正确
- 防火墙是否阻止连接

## 🐛 常见错误及解决方案

### 错误 1: "Username already registered"

```json
{
  "error": {
    "message": "Username already registered",
    "status_code": 400
  }
}
```

**解决方案**: 使用不同的用户名

### 错误 2: "Email already registered"

```json
{
  "error": {
    "message": "Email already registered",
    "status_code": 400
  }
}
```

**解决方案**: 使用不同的邮箱

### 错误 3: "Validation error"

```json
{
  "error": {
    "message": "Validation error",
    "status_code": 422,
    "details": {
      "errors": [...]
    }
  }
}
```

**解决方案**: 检查 details 中的具体错误，修正数据格式

### 错误 4: "Incorrect username or password"

```json
{
  "error": {
    "message": "Incorrect username or password",
    "status_code": 401
  }
}
```

**解决方案**:
- 确认用户已成功注册
- 确认密码输入正确（区分大小写）
- 尝试重新注册一个新用户

## 📝 下一步操作

1. **在浏览器 Console 中运行上面的 JavaScript 测试代码**
2. **查看结果**:
   - 如果成功 → Flutter 代码有问题
   - 如果失败 → 后端或 CORS 有问题
3. **提供详细错误信息**:
   - Network 标签页的 Request/Response
   - Console 标签页的错误信息
   - 后端日志（如果有）

## 🔗 相关文件

- `mobile/lib/core/services/api_client.dart` - API 客户端
- `mobile/lib/features/auth/screens/register_screen.dart` - 注册页面
- `mobile/lib/features/auth/screens/login_screen.dart` - 登录页面
- `backend/app/api/auth.py` - 后端认证 API
- `backend/app/schemas/user.py` - 数据验证规则

---

**提示**: 最快的解决方法是在浏览器 Console 中运行 JavaScript 测试代码，这样可以立即看到问题所在。
