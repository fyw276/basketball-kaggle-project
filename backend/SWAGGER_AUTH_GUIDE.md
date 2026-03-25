# Swagger UI 认证使用指南

## 问题说明

当你在 Swagger UI 中测试需要认证的 API（如相似度分析、搭配推荐等）时，如果没有提供 JWT token，会收到 403 Forbidden 错误：

```json
{
  "error": {
    "type": "JWTException",
    "message": "JWT token is required",
    "status_code": 403,
    "path": "/api/v1/analysis/similarity"
  }
}
```

## 解决方案：在 Swagger UI 中添加认证

### 步骤 1: 注册用户（如果还没有账号）

1. 在 Swagger UI 中找到 `POST /api/v1/auth/register` 端点
2. 点击 "Try it out"
3. 填写请求体：
   ```json
   {
     "username": "testuser",
     "email": "test@example.com",
     "password": "Test123!@#"
   }
   ```
4. 点击 "Execute"
5. 确认返回 201 Created

### 步骤 2: 登录获取 Token

1. 找到 `POST /api/v1/auth/login` 端点
2. 点击 "Try it out"
3. 填写请求体：
   ```json
   {
     "username": "testuser",
     "password": "Test123!@#"
   }
   ```
4. 点击 "Execute"
5. 从响应中复制 `access_token` 的值
   ```json
   {
     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "token_type": "bearer"
   }
   ```

### 步骤 3: 在 Swagger UI 中设置认证

1. 点击页面右上角的 **"Authorize"** 按钮（🔒 锁图标）
2. 在弹出的对话框中，找到 "HTTPBearer (http, Bearer)" 部分
3. 在 "Value" 输入框中输入：
   ```
   Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```
   **注意**：必须包含 "Bearer " 前缀（注意空格）
4. 点击 **"Authorize"** 按钮
5. 看到 "Authorized" 提示后，点击 **"Close"**

### 步骤 4: 测试需要认证的 API

现在你可以测试任何需要认证的 API 了，例如：

#### 测试相似度分析 API

1. 找到 `POST /api/v1/analysis/similarity` 端点
2. 点击 "Try it out"
3. 点击 "Choose File" 上传一张服饰图片
4. 点击 "Execute"
5. 应该返回 200 OK 和相似度分析结果

#### 测试搭配推荐 API

1. 找到 `POST /api/v1/analysis/outfits` 端点
2. 点击 "Try it out"
3. 上传图片，设置 `num_outfits` 参数（默认 3）
4. 点击 "Execute"
5. 应该返回 200 OK 和搭配推荐结果

#### 测试适合度评分 API

1. 找到 `POST /api/v1/analysis/suitability` 端点
2. 点击 "Try it out"
3. 上传图片
4. 点击 "Execute"
5. 应该返回 200 OK 和适合度评分结果

## 需要认证的 API 列表

以下 API 端点需要 JWT token 认证：

### 用户画像
- `POST /api/v1/profile` - 创建用户画像
- `GET /api/v1/profile` - 获取用户画像
- `PUT /api/v1/profile` - 更新用户画像

### 衣橱管理
- `POST /api/v1/wardrobe/garments` - 添加服饰
- `GET /api/v1/wardrobe/garments` - 查询衣橱
- `GET /api/v1/wardrobe/garments/{garment_id}` - 获取服饰详情
- `PUT /api/v1/wardrobe/garments/{garment_id}` - 更新服饰
- `DELETE /api/v1/wardrobe/garments/{garment_id}` - 删除服饰

### 分析功能
- `POST /api/v1/analysis/similarity` - 相似度分析
- `POST /api/v1/analysis/outfits` - 搭配推荐
- `POST /api/v1/analysis/suitability` - 适合度评分

## 不需要认证的 API

以下 API 端点不需要认证：

- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/login` - 用户登录
- `GET /` - 根路径
- `GET /health` - 健康检查
- `GET /docs` - API 文档
- `GET /redoc` - ReDoc 文档

## 使用 Python 脚本测试

如果你想使用脚本测试，可以运行：

```bash
cd backend
python test_similarity_api.py
```

这个脚本会：
1. 自动注册测试用户
2. 登录获取 token
3. 测试相似度分析 API
4. 显示如何在 Swagger UI 中使用 token

## 常见问题

### Q: Token 过期了怎么办？

A: Token 默认有效期是 24 小时。如果过期，需要重新登录获取新的 token。

### Q: 忘记在 "Bearer " 前缀怎么办？

A: 必须包含 "Bearer " 前缀（注意空格），否则会收到 403 错误。正确格式：
```
Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Q: 如何退出登录？

A: 在 Swagger UI 中：
1. 点击右上角的 "Authorize" 按钮
2. 点击 "Logout" 按钮
3. 点击 "Close"

### Q: 可以使用 Postman 测试吗？

A: 可以。在 Postman 中：
1. 在请求的 "Authorization" 标签页
2. 选择 "Bearer Token" 类型
3. 粘贴 token（不需要 "Bearer " 前缀）

## 测试流程示例

完整的测试流程：

```
1. 注册用户
   POST /api/v1/auth/register
   → 201 Created

2. 登录获取 token
   POST /api/v1/auth/login
   → 200 OK, access_token: "eyJ..."

3. 在 Swagger UI 中设置认证
   点击 Authorize → 输入 "Bearer eyJ..." → Authorize → Close

4. 创建用户画像（可选，适合度评分需要）
   POST /api/v1/profile
   → 201 Created

5. 测试相似度分析
   POST /api/v1/analysis/similarity
   → 200 OK, 返回相似度分析结果

6. 测试搭配推荐
   POST /api/v1/analysis/outfits
   → 200 OK, 返回搭配推荐

7. 测试适合度评分
   POST /api/v1/analysis/suitability
   → 200 OK, 返回适合度评分
```

## 技术说明

- 认证方式：JWT (JSON Web Token)
- Token 类型：Bearer Token
- Token 位置：HTTP Header `Authorization: Bearer <token>`
- Token 有效期：24 小时（可在配置中修改）
- 加密算法：HS256
