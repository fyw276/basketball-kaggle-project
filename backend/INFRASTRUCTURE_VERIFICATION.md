# 基础设施验证指南

本文档说明如何验证 Smart Outfit Assistant 的基础设施是否正确配置。

## 前置要求

在运行验证之前，请确保：

1. PostgreSQL 数据库已安装并运行
2. Redis 服务已安装并运行
3. Python 依赖已安装 (`pip install -r requirements.txt`)
4. 环境变量已配置（`.env` 文件）

## 快速验证

运行综合验证脚本：

```bash
cd backend
python scripts/verify_infrastructure.py
```

该脚本将测试：
- ✓ 数据库连接
- ✓ 数据库表结构
- ✓ Redis 缓存连接
- ✓ Redis 操作（set/get/delete）
- ✓ 密码加密和验证
- ✓ JWT Token 生成和解码
- ✓ 数据模型导入
- ✓ API Schemas 验证

## 单独测试

### 1. 测试数据库连接

```bash
python scripts/test_db_connection.py
```

预期输出：
```
Testing database connection to: postgresql://...
------------------------------------------------------------
✓ Engine connection successful!
  PostgreSQL version: PostgreSQL 14.x...
✓ Session connection successful!
------------------------------------------------------------
All database connection tests passed!
```

### 2. 测试 Redis 连接

```bash
python scripts/test_redis_connection.py
```

预期输出：
```
Testing Redis connection to: redis://localhost:6379/0
------------------------------------------------------------
✓ Redis connection successful!
✓ Set operation successful!
✓ Get operation successful!
✓ Exists operation successful!
✓ TTL operation successful! (TTL: 60s)
✓ Delete operation successful!
✓ Deletion verified!
------------------------------------------------------------
All Redis tests passed!
```

### 3. 初始化数据库表

如果数据库表不存在，运行：

```bash
python scripts/init_db.py
```

预期输出：
```
Initializing database at: postgresql://...
Creating tables...
✓ All tables created successfully!

Created tables:
  - users
  - user_profiles
  - garments
```

## 测试 API 端点

### 启动开发服务器

```bash
python run.py
```

或使用 uvicorn：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 访问 API 文档

打开浏览器访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 测试用户注册

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "password123"
  }'
```

预期响应：
```json
{
  "user_id": "uuid-here",
  "username": "testuser",
  "email": "test@example.com",
  "created_at": "2024-01-01T00:00:00",
  "is_active": true
}
```

### 测试用户登录

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "password123"
  }'
```

预期响应：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 测试受保护端点

使用获取的 token 访问受保护端点：

```bash
curl -X GET "http://localhost:8000/api/v1/users/me" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 测试用户画像

创建用户画像：

```bash
curl -X POST "http://localhost:8000/api/v1/profile" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "height": 170,
    "body_type": "矩形",
    "skin_tone": "黄皮",
    "style_preference": ["简约", "通勤"],
    "budget_range": "中等",
    "avoid_body_parts": ["腰"]
  }'
```

## 常见问题

### 数据库连接失败

**问题**: `could not connect to server`

**解决方案**:
1. 确保 PostgreSQL 服务正在运行
2. 检查 `.env` 文件中的 `DATABASE_URL` 配置
3. 验证数据库用户名和密码
4. 确保数据库已创建

### Redis 连接失败

**问题**: `Error connecting to Redis`

**解决方案**:
1. 确保 Redis 服务正在运行
2. 检查 `.env` 文件中的 `REDIS_URL` 配置
3. 验证 Redis 端口（默认 6379）

### 表不存在

**问题**: `relation "users" does not exist`

**解决方案**:
运行数据库初始化脚本：
```bash
python scripts/init_db.py
```

### 导入错误

**问题**: `ModuleNotFoundError: No module named 'app'`

**解决方案**:
确保从 `backend` 目录运行脚本，或者设置 PYTHONPATH：
```bash
export PYTHONPATH="${PYTHONPATH}:/path/to/backend"
```

## 验证清单

在继续开发之前，确保以下所有项目都已完成：

- [ ] PostgreSQL 数据库已安装并运行
- [ ] Redis 服务已安装并运行
- [ ] 数据库表已创建（users, user_profiles, garments）
- [ ] 数据库连接测试通过
- [ ] Redis 连接测试通过
- [ ] 密码加密功能正常
- [ ] JWT Token 生成和验证正常
- [ ] API 服务器可以启动
- [ ] 用户注册 API 正常工作
- [ ] 用户登录 API 正常工作
- [ ] 受保护端点需要认证
- [ ] 用户画像 API 正常工作

## 下一步

基础设施验证通过后，可以继续开发：

1. 图像识别模块（任务 6-11）
2. 衣橱管理模块（任务 13）
3. 相似度分析模块（任务 14）
4. 搭配推荐模块（任务 15-16）
5. 适合度评分模块（任务 18）

## 参考资料

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [Redis Python 文档](https://redis-py.readthedocs.io/)
- [JWT 文档](https://jwt.io/)
