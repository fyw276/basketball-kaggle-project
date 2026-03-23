# 🔐 Swagger UI 认证指南

## 问题：创建用户画像时返回 401 Unauthorized

如果你在 Swagger UI 中测试 `POST /api/v1/profile` 时遇到 401 错误，最常见的原因是 **Authorize 对话框中的 Token 格式不正确**。

---

## ✅ 正确的认证步骤

### 步骤 1: 登录获取 Token

1. 展开 `POST /api/v1/auth/login`
2. 点击 "Try it out"
3. 输入登录信息：
   ```json
   {
     "username": "your_username",
     "password": "your_password"
   }
   ```
4. 点击 "Execute"
5. 在响应中找到 `access_token`，**完整复制整个 Token**

**响应示例**：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmNzI4NDY1Yi1lMjhiLTQyZTctYTA2Mi0zNDg5ZWM3NDQyOWUiLCJ1c2VybmFtZSI6Im1hbnVhbF90ZXN0X3VzZXIiLCJleHAiOjE3NDI3MzYwNTh9.example",
  "token_type": "bearer"
}
```

### 步骤 2: 在 Swagger UI 中授权

1. 点击页面右上角的 **"Authorize" 🔓** 按钮
2. 在弹出的对话框中：
   - **只粘贴 Token 本身**
   - **不要包含 "Bearer" 前缀**
   - **不要包含引号**
   - **确保 Token 完整（没有被截断）**

#### ❌ 错误示例：

```
Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

```
"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

#### ✅ 正确示例：

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmNzI4NDY1Yi1lMjhiLTQyZTctYTA2Mi0zNDg5ZWM3NDQyOWUiLCJ1c2VybmFtZSI6Im1hbnVhbF90ZXN0X3VzZXIiLCJleHAiOjE3NDI3MzYwNTh9.example
```

3. 点击 **"Authorize"** 按钮
4. 点击 **"Close"** 关闭对话框
5. **确认右上角的锁图标变为 🔒（已授权状态）**

### 步骤 3: 测试认证端点

现在你可以测试需要认证的端点了：

1. 展开 `POST /api/v1/profile`
2. 点击 "Try it out"
3. 输入画像信息
4. 点击 "Execute"
5. 应该返回 **201 Created** 状态码

---

## 🔍 诊断工具

如果仍然遇到问题，运行诊断脚本：

```bash
cd backend
python diagnose_auth.py
```

这个脚本会：
- 测试完整的认证流程
- 验证 Token 是否有效
- 测试创建用户画像
- 提供详细的错误诊断

---

## 🐛 常见问题

### Q1: 仍然返回 401 错误

**可能原因**：
1. Token 被截断或复制不完整
2. Token 已过期（24 小时有效期）
3. 在 Authorize 对话框中包含了 "Bearer" 前缀

**解决方案**：
1. 重新登录获取新 Token
2. 确保复制完整的 Token（通常很长，200+ 字符）
3. 在 Authorize 对话框中只粘贴 Token 本身

### Q2: 如何验证 Token 是否有效？

运行 Token 测试脚本：

```bash
python test_token.py "your_token_here"
```

这会显示：
- Token 是否能正确解码
- Token 是否已过期
- Token 包含的用户信息

### Q3: curl 命令可以工作，但 Swagger UI 不行

这通常是因为：
- curl 命令中使用 `Bearer <token>` 格式（正确）
- Swagger UI 的 Authorize 对话框会自动添加 "Bearer" 前缀
- 如果你手动输入 "Bearer <token>"，会变成 "Bearer Bearer <token>"（错误）

**解决方案**：在 Swagger UI 中只输入 Token 本身。

---

## 📝 验证步骤

完成授权后，验证是否成功：

1. 右上角的锁图标应该是 🔒（已锁定）
2. 测试 `GET /api/v1/users/me` 端点：
   - 点击 "Try it out"
   - 点击 "Execute"
   - 应该返回 200 状态码和你的用户信息

如果这个端点返回 200，说明认证成功，可以继续测试其他端点。

---

## 🎯 快速测试

使用 curl 命令快速测试（替换 YOUR_TOKEN）：

```bash
# 测试认证
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer YOUR_TOKEN"

# 创建用户画像
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "height": 170,
    "body_type": "矩形",
    "skin_tone": "冷白",
    "style_preference": ["通勤", "简约"],
    "budget_range": "中等",
    "avoid_body_parts": ["肩部"]
  }'
```

如果 curl 命令成功但 Swagger UI 失败，问题一定是 Swagger UI 的授权配置。

---

## 💡 提示

- Token 有效期为 24 小时，过期后需要重新登录
- 每次重新登录都会获得新的 Token
- 可以在多个标签页中使用同一个 Token
- Token 包含用户 ID 和用户名信息

---

**如果按照以上步骤仍然无法解决问题，请运行 `python diagnose_auth.py` 获取详细诊断信息。**
