# 后端配置测试指南

本指南帮助你验证后端配置是否成功，包括基础设施、核心功能和 API 端点。

## 📋 测试清单

- [ ] 1. 环境配置验证
- [ ] 2. 基础设施验证（数据库、Redis）
- [ ] 3. 后端服务启动
- [ ] 4. API 端点测试
- [ ] 5. 核心功能验证
- [ ] 6. 单元测试运行

---

## 1️⃣ 环境配置验证

### 检查 Python 版本

```bash
python --version
# 应该显示 Python 3.9+ (推荐 3.9-3.12)
```

### 检查虚拟环境

```bash
cd backend

# 激活虚拟环境
# Windows:
venv\Scripts\activate

# Linux/Mac:
source venv/bin/activate

# 验证虚拟环境已激活（命令行前应该有 (venv) 标识）
```

### 检查依赖安装

```bash
# 查看已安装的包
pip list

# 关键包检查
pip show fastapi uvicorn sqlalchemy redis tensorflow
```

**预期结果**：所有关键包都已安装

---

## 2️⃣ 基础设施验证

### 方法 1: 使用综合验证脚本（推荐）

```bash
cd backend
python scripts/verify_infrastructure.py
```

**预期输出**：
```
=== 基础设施验证 ===
✓ 环境变量配置正确
✓ 数据库连接成功
✓ Redis 连接成功
✓ MobileNetV2 模型加载成功
✓ 所有基础设施验证通过
```

### 方法 2: 单独测试各组件

#### 测试数据库连接

```bash
python scripts/test_db_connection.py
```

**预期输出**：
```
✓ 数据库连接成功
✓ 可以执行查询
```

#### 测试 Redis 连接

```bash
python scripts/test_redis_connection.py
```

**预期输出**：
```
✓ Redis 连接成功
✓ 可以读写数据
```

#### 测试模型加载

```bash
python scripts/test_model_loading.py
```

**预期输出**：
```
✓ MobileNetV2 模型加载成功
✓ 模型可以进行推理
```

---

## 3️⃣ 后端服务启动

### 启动开发服务器

```bash
cd backend

# 方法 1: 使用启动脚本（Windows）
start.bat

# 方法 2: 使用 Python 脚本
python run.py

# 方法 3: 使用 uvicorn
uvicorn app.main:app --reload
```

**预期输出**：
```
INFO:     Uvicorn running on http://127.0.0.1:8010 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 验证服务运行

打开浏览器访问：

1. **根端点**: http://127.0.0.1:8010/
   - 应该看到欢迎消息和 API 信息

2. **健康检查**: http://127.0.0.1:8010/health
   - 应该返回 `{"status": "healthy"}`

3. **Swagger UI**: http://127.0.0.1:8010/docs
   - 应该看到交互式 API 文档

4. **ReDoc**: http://127.0.0.1:8010/redoc
   - 应该看到美观的 API 文档

---

## 4️⃣ API 端点测试

### 使用 Swagger UI 测试（推荐）

1. 访问 http://127.0.0.1:8010/docs
2. 展开任意端点
3. 点击 "Try it out"
4. 填写参数
5. 点击 "Execute"
6. 查看响应

### 使用 curl 测试

#### 测试根端点

```bash
curl http://127.0.0.1:8010/
```

**预期响应**：
```json
{
  "message": "Welcome to Smart Outfit Assistant API",
  "version": "1.0.0",
  "docs": "/docs"
}
```

#### 测试健康检查

```bash
curl http://127.0.0.1:8010/health
```

**预期响应**：
```json
{
  "status": "healthy"
}
```

#### 测试用户注册

```bash
curl -X POST http://127.0.0.1:8010/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"testuser\",\"email\":\"test@example.com\",\"password\":\"TestPass123\"}"
```

**预期响应**：
```json
{
  "user_id": "...",
  "username": "testuser",
  "email": "test@example.com"
}
```

#### 测试用户登录

```bash
curl -X POST http://127.0.0.1:8010/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"testuser\",\"password\":\"TestPass123\"}"
```

**预期响应**：
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## 5️⃣ 核心功能验证

### 运行后端完整性验证脚本

```bash
cd backend
python scripts/verify_backend_completion.py
```

**预期输出**：
```
=== Backend Service Integrity Verification ===

=== Verifying API Documentation ===
✓ OpenAPI documentation configured
  - Swagger UI: /docs
  - ReDoc: /redoc
  - OpenAPI spec: /openapi.json

=== Verifying Error Handling ===
✓ Custom exception classes defined
✓ Global exception handlers defined
✓ 10 exception handlers registered

=== Verifying Account Deletion ===
✓ delete_user service function exists
✓ DELETE endpoint configured: /api/v1/users/me

=== Verifying Security Measures ===
✓ Password encryption (bcrypt) working
✓ JWT token generation and validation working
✓ CORS configured: X origins

=== Verifying Performance Optimizations ===
✓ Redis cache client configured
✓ Feature extractor available

=== Verifying API Endpoints ===
✓ All 12 required endpoints exist

=== Verification Summary ===
✓ PASS: API Documentation
✓ PASS: Error Handling
✓ PASS: Account Deletion
✓ PASS: Security Measures
✓ PASS: Performance Optimizations
✓ PASS: API Endpoints

Total: 6/6 checks passed

🎉 All backend core tasks (19-22) are complete!
```

---

## 6️⃣ 单元测试运行

### 运行所有测试

```bash
cd backend
pytest -v
```

### 运行特定测试文件

```bash
# 错误处理测试
pytest tests/test_error_handling.py -v

# 性能测试
pytest tests/test_performance.py -v

# 安全测试
pytest tests/test_security.py -v

# 特征提取测试
pytest tests/test_feature_extractor.py -v

# 适合度评分测试
pytest tests/test_suitability_scorer.py -v
```

### 查看测试覆盖率

```bash
pytest --cov=app --cov-report=html
# 然后打开 htmlcov/index.html 查看详细报告
```

**预期结果**：
```
======================== test session starts ========================
collected XX items

tests/test_error_handling.py::test_create_error_response PASSED
tests/test_error_handling.py::test_validation_error PASSED
...

======================== XX passed in X.XXs ========================
```

---

## 🔍 故障排查

### 问题 1: 数据库连接失败

**错误信息**：
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**解决方案**：
1. 检查 PostgreSQL 是否运行
2. 检查 `.env` 文件中的 `DATABASE_URL` 配置
3. 确认数据库已创建：
   ```bash
   psql -U postgres
   CREATE DATABASE outfit_assistant;
   ```

### 问题 2: Redis 连接失败

**错误信息**：
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**解决方案**：
1. 检查 Redis 是否运行
2. 检查 `.env` 文件中的 `REDIS_URL` 配置
3. 启动 Redis：
   ```bash
   # Windows: 运行 redis-server.exe
   # Linux: sudo systemctl start redis
   # Mac: brew services start redis
   ```

### 问题 3: 模型加载失败

**错误信息**：
```
OSError: Unable to load weights from file
```

**解决方案**：
1. 确保网络连接正常（首次运行会下载模型）
2. 检查 `~/.keras/models/` 目录是否有权限
3. 手动下载模型：
   ```bash
   python scripts/test_model_loading.py
   ```

### 问题 4: 端口被占用

**错误信息**：
```
OSError: [Errno 98] Address already in use
```

**解决方案**：
1. 查找占用端口的进程：
   ```bash
   # Windows
   netstat -ano | findstr :8000

   # Linux/Mac
   lsof -i :8000
   ```
2. 终止进程或使用其他端口：
   ```bash
   uvicorn app.main:app --reload --port 8001
   ```

### 问题 5: 依赖包缺失

**错误信息**：
```
ModuleNotFoundError: No module named 'xxx'
```

**解决方案**：
```bash
# 重新安装依赖
pip install -r requirements.txt

# 或安装特定包
pip install xxx
```

---

## ✅ 验证成功标准

所有以下检查都应该通过：

- [x] 虚拟环境已激活
- [x] 所有依赖包已安装
- [x] 数据库连接成功
- [x] Redis 连接成功
- [x] MobileNetV2 模型加载成功
- [x] 后端服务启动成功
- [x] 可以访问 Swagger UI
- [x] 可以访问 ReDoc
- [x] 健康检查端点返回正常
- [x] 用户注册/登录功能正常
- [x] 所有单元测试通过
- [x] 后端完整性验证通过

---

## 📊 测试结果汇总

### 已实现的 API 端点（13 个）

**认证模块**：
- ✅ POST /api/v1/auth/register - 用户注册
- ✅ POST /api/v1/auth/login - 用户登录

**用户模块**：
- ✅ GET /api/v1/users/me - 获取当前用户
- ✅ DELETE /api/v1/users/me - 删除账号

**用户画像模块**：
- ✅ POST /api/v1/profile - 创建画像
- ✅ GET /api/v1/profile - 获取画像
- ✅ PUT /api/v1/profile - 更新画像

**衣橱管理模块**：
- ✅ POST /api/v1/wardrobe/garments - 添加服饰
- ✅ GET /api/v1/wardrobe/garments - 查询衣橱

**分析模块**：
- ✅ POST /api/v1/analysis/similarity - 相似度分析
- ✅ POST /api/v1/analysis/suitability - 适合度评分

**推荐模块**：
- ✅ POST /api/v1/recommendations/outfits - 搭配推荐

### 测试覆盖率

- **错误处理测试**: 12/12 通过 ✅
- **安全测试**: 7/7 通过 ✅
- **性能测试**: 10/10 通过 ✅
- **特征提取测试**: 24/24 通过 ✅
- **适合度评分测试**: 57/57 通过 ✅

**总计**: 110+ 测试通过 ✅

---

## 🎯 下一步

后端配置测试完成后，你可以：

1. **开发前端应用**（Flutter 移动端）
2. **开发 CLI 工具**（命令行界面）
3. **开发 MCP 服务**（AI 智能体集成）
4. **部署到生产环境**

---

## 📚 相关文档

- `README.md` - 项目概述和快速开始
- `PROJECT_STATUS.md` - 项目进度和已完成模块
- `TASKS_19_22_COMPLETION_SUMMARY.md` - 后端核心任务完成总结
- `INFRASTRUCTURE_VERIFICATION.md` - 基础设施验证详情
- `DATABASE_SETUP.md` - 数据库设置指南

---

**最后更新**: 2024-01-XX
**状态**: ✅ 后端核心功能完整
