# 快速测试指南 - Flutter 登录修复

## 🚀 立即测试

### 步骤 1: 重启 Flutter Web

在运行 Flutter Web 的终端中：
1. 按 `r` 键进行热重载（Hot Reload）
2. 如果热重载不起作用，按 `R` 键进行热重启（Hot Restart）
3. 如果仍然不行，按 `Ctrl+C` 停止，然后重新运行：
   ```bash
   flutter run -d chrome
   ```

### 步骤 2: 测试登录

#### 选项 A: 使用新用户注册
1. 点击"立即注册"
2. 填写信息：
   - 用户名: `test_user_002`
   - 邮箱: `test002@example.com`
   - 密码: `Test123!@#`
3. 点击"注册"
4. **预期结果**: 自动跳转到主页，显示功能卡片

#### 选项 B: 使用已有用户登录
1. 在登录页面填写：
   - 用户名: `test_user_001`（或您之前注册的用户名）
   - 密码: `Test123!@#`
2. 点击"登录"
3. **预期结果**: 立即跳转到主页

### 步骤 3: 查看调试信息

打开浏览器开发者工具（按 F12），切换到 Console 标签，应该看到：

```
📝 表单验证通过，开始登录...
🔐 开始登录: test_user_002
✅ 登录成功: eyJhbGciOiJIUzI1NiIs...
✅ 认证状态已更新: true
🔄 登录结果: true
✅ 登录成功，准备跳转到 /home
✅ 已调用 context.go('/home')
```

## ✅ 成功标志

- [ ] 登录后 URL 从 `/login` 变为 `/home`
- [ ] 看到主页标题"智能穿搭助手"
- [ ] 看到功能卡片（用户画像、衣橱管理等）
- [ ] 浏览器控制台显示成功日志

## ❌ 如果仍然失败

### 检查清单

1. **后端是否运行？**
   - 访问 http://localhost:8000/health
   - 应该看到 `{"status":"healthy","version":"1.0.0"}`

2. **Flutter Web 是否重启？**
   - 确保按了 `R` 键或重新运行了 `flutter run`
   - 旧代码可能仍在浏览器中运行

3. **浏览器缓存？**
   - 按 `Ctrl+Shift+R` 强制刷新
   - 或清除浏览器缓存

4. **查看完整错误？**
   - 打开浏览器开发者工具
   - 查看 Console 标签的错误信息
   - 查看 Network 标签的 API 请求

### 常见错误及解决方案

#### 错误 1: "CORS policy" 错误
```
Access to XMLHttpRequest at 'http://localhost:8000/api/v1/auth/login'
from origin 'http://localhost:61742' has been blocked by CORS policy
```

**解决方案**: 重启后端服务
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 错误 2: "密码不符合要求"
```
{"detail":"密码必须至少8个字符，包含字母、数字和特殊字符"}
```

**解决方案**: 使用包含特殊字符的密码，如 `Test123!@#`

#### 错误 3: "用户名已存在"
```
{"detail":"用户名已存在"}
```

**解决方案**: 使用不同的用户名，或直接登录

#### 错误 4: 页面空白
**解决方案**:
1. 检查浏览器控制台是否有 JavaScript 错误
2. 尝试硬刷新（Ctrl+Shift+R）
3. 重启 Flutter Web

## 🔍 调试技巧

### 查看 API 请求

1. 打开开发者工具（F12）
2. 切换到 Network 标签
3. 点击"登录"按钮
4. 查看 `login` 请求：
   - Status 应该是 `200 OK`
   - Response 应该包含 `access_token`

### 查看本地存储

1. 开发者工具 → Application 标签
2. 左侧 Storage → Local Storage → http://localhost:xxxxx
3. 应该看到 `flutter.access_token` 键

## 📝 修复内容总结

### 修改的文件

1. **mobile/lib/main.dart**
   - 将 `MyApp` 改为 `StatefulWidget`
   - 在 `initState` 中创建 `GoRouter`
   - 使用 `refreshListenable` 监听认证状态

2. **mobile/lib/core/providers/auth_provider.dart**
   - 添加调试日志
   - 确保 `notifyListeners()` 被正确调用

3. **mobile/lib/features/auth/screens/login_screen.dart**
   - 添加调试日志
   - 确保 `context.go('/home')` 被调用

### 核心修复

**问题**: `GoRouter` 在每次状态变化时被重新创建，导致路由状态丢失

**解决**: 只创建一次 `GoRouter`，使用 `refreshListenable` 监听状态变化

## 🎯 下一步

修复成功后，可以测试：
1. 创建用户画像
2. 添加衣橱单品
3. 测试图像识别功能
4. 测试搭配推荐功能

## 📞 需要帮助？

如果问题仍然存在，请提供：
1. 浏览器控制台的完整日志（Console 标签）
2. Network 标签中 `login` 请求的详细信息
3. Flutter Web 终端的输出
4. 后端日志（`backend/logs/app.log`）
