# Smart Outfit Assistant - Backend

FastAPI 后端服务，提供智能穿搭助手的核心功能。

## 🚀 快速开始

### ⚠️ Python 3.14 用户必读

如果你使用 **Python 3.14**，请使用专门的启动脚本：

```bash
cd backend
quick_start_py314.bat
```

**为什么需要特殊处理？**
- Python 3.14 太新，某些包（如 `pydantic-core`）没有预编译版本
- 需要 Rust 编译器，但我们提供了兼容版本的依赖文件
- `quick_start_py314.bat` 会自动使用 `requirements-simple.txt`

**详细说明**：
- 查看 `backend/解决方案.md`（完整中文说明）
- 查看 `backend/START_HERE.md`（快速开始指南）
- 查看 `backend/立即运行.txt`（一条命令解决）

---

### Windows 用户（Python 3.9-3.12）

**方法 1: 诊断环境**（可选，检查配置）
```bash
diagnose.bat
```

**方法 2: 一键启动**
```bash
start.bat
```

这个脚本会自动完成所有设置步骤。

### 手动启动

### 1. 创建虚拟环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 2. 安装依赖

```bash
# Python 3.14 用户（推荐）
pip install -r requirements-simple.txt

# Python 3.9-3.12 完整安装
pip install -r requirements.txt

# Python 3.9-3.12 最小安装（快速测试，仅核心依赖）
pip install -r requirements-minimal.txt
```

**依赖文件说明**：
- `requirements-simple.txt` - Python 3.14 兼容版本 ⭐
- `requirements.txt` - 完整依赖（Python 3.9-3.12）
- `requirements-minimal.txt` - 最小依赖（Python 3.9-3.12）

详细说明请查看 `DEPENDENCIES.md`

### 3. 配置环境变量

```bash
# 复制示例配置文件
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# 暂时使用默认配置即可
```

### 4. 启动开发服务器

```bash
python run.py
```

或使用 uvicorn：

```bash
uvicorn app.main:app --reload
```

### 5. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/health
- 根端点: http://localhost:8000/

## ⚠️ 遇到问题？

1. **运行诊断工具**: `diagnose.bat`
2. **查看故障排查指南**: `TROUBLESHOOTING.md`
3. **使用最小依赖**: `pip install -r requirements-minimal.txt`

## 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── api/                 # API 路由
│   ├── core/                # 核心配置
│   │   ├── config.py        # 应用配置
│   │   └── logging.py       # 日志配置
│   ├── db/                  # 数据库配置
│   ├── models/              # SQLAlchemy 模型
│   ├── schemas/             # Pydantic 模式
│   └── services/            # 业务逻辑
├── tests/                   # 测试文件
├── .env.example             # 环境变量示例
├── requirements.txt         # 生产依赖
├── requirements-dev.txt     # 开发依赖
└── pyproject.toml          # 项目配置
```

## 开发工具

### 代码格式化

```bash
# 格式化代码
black .
isort .
```

### 代码检查

```bash
# 运行 linter
flake8 app/
pylint app/

# 类型检查
mypy app/
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/unit/

# 查看覆盖率
pytest --cov=app --cov-report=html
```

### Pre-commit Hooks

```bash
# 安装 pre-commit hooks
pre-commit install

# 手动运行所有 hooks
pre-commit run --all-files
```

## API 端点

### 当前可用端点

- `GET /` - 根端点，返回 API 信息
- `GET /health` - 健康检查

### 即将添加的端点

- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/login` - 用户登录
- `POST /api/v1/wardrobe/garments` - 添加服饰
- `GET /api/v1/wardrobe/garments` - 查询衣橱
- `POST /api/v1/analysis/similarity` - 相似度分析
- `POST /api/v1/recommendations/outfits` - 搭配推荐
- `POST /api/v1/analysis/suitability` - 适合度评分

## 环境变量

查看 `.env.example` 文件了解所有可配置的环境变量。

关键配置：
- `DATABASE_URL` - PostgreSQL 数据库连接
- `REDIS_URL` - Redis 缓存连接
- `JWT_SECRET_KEY` - JWT 密钥（生产环境必须修改）
- `CORS_ORIGINS` - 允许的跨域来源

## 下一步

按照 `tasks.md` 继续实现：
- 任务 2: 数据库设计与初始化
- 任务 3: 用户认证与授权模块
- 任务 4: 用户画像管理模块
- ...
