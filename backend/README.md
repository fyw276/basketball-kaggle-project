# Smart Outfit Assistant - Backend

更新时间：2026-05-02

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
- `quick_start_py314.bat` 会自动使用 `requirements-py314.txt`

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
pip install -r requirements-py314.txt

# Python 3.9-3.12 安装
pip install -r requirements.txt
```

**依赖文件说明**：
- `requirements-py314.txt` - Python 3.14 兼容版本 ⭐
- `requirements.txt` - Python 3.9-3.12 依赖
- `requirements-dev.txt` - 开发工具与测试增强依赖

详细说明请查看 `DEPENDENCIES.md`

### 3. 配置环境变量

```bash
# 复制示例配置文件
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# 暂时使用默认配置即可
```

> 模型相关提示：
> - FashionCLIP / 虚拟试衣首次运行可能会下载权重（弱网易超时）。
> - 在 `.env` 中设置 `HF_ENDPOINT=https://hf-mirror.com`（及可选 `HF_HUB_DOWNLOAD_TIMEOUT` 等）；这些键已在 `app.core.config.Settings` 中声明，启动时会注入 `os.environ`。详见仓库根目录 [docs/WEATHER_DISPLAY_AND_HF_ENV.md](../docs/WEATHER_DISPLAY_AND_HF_ENV.md)。
> - **扩散试衣依赖**：`torch` 与 `torchvision` 须版本匹配（同一轮 `pip install`）；可选表单字段 `garment_category` 改善 fallback 粘贴。CatVTON realistic/professional 模式见 [docs/VTON_INTEGRATION.md](../docs/VTON_INTEGRATION.md)。

### 4. 启动开发服务器

以下命令须在 **`backend` 当前目录**执行（在仓库根目录运行会 `No module named 'app'`）。可使用仓库根的 **`.venv`**：`..\.venv\Scripts\python.exe`（Windows）。

若 **`WinError 10048`**，表示 **8010** 已被占用，请结束旧进程或改用 `--port 8011`。

```bash
python run.py
```

或使用 uvicorn（端口与 `PORT` / `.env` 一致，**默认 8010**，与 Flutter `kApiPort` 对齐）：

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 5. 访问 API 文档

- Swagger UI: http://127.0.0.1:8010/docs
- ReDoc: http://127.0.0.1:8010/redoc
- 健康检查: http://127.0.0.1:8010/health
- 根端点: http://127.0.0.1:8010/

若 `.env` 中 `PORT` 不是 `8010`，请把上面 URL 中的端口改成当前值。

## ⚠️ 遇到问题？

1. **运行诊断工具**: `diagnose.bat`
2. **查看故障排查指南**: `TROUBLESHOOTING.md`
3. **Python 3.14 环境使用兼容依赖**: `pip install -r requirements-py314.txt`

## 项目结构

```
backend/
├── app/
│   ├── api/                    # 20 个路由模块（含 tryon_v2）
│   ├── core/                  # 配置、错误处理、日志、超参
│   ├── db/                    # 数据库配置
│   ├── models/               # SQLAlchemy 模型
│   ├── ml/                   # 模型加载（CLIP）
│   ├── observability/         # 指标收集
│   ├── schemas/              # Pydantic schemas
│   └── services/             # 50 个服务模块
│       └── tryon_v2/         # 14 个虚拟试衣 v2 管线模块
├── scripts/                   # 诊断与测试脚本
├── tests/                    # pytest 套件
├── uploads/                  # 上传图片
├── .env.example              # 环境变量示例
├── requirements.txt           # Python 3.9-3.12 依赖
├── requirements-py314.txt    # Python 3.14 兼容依赖
├── requirements-dev.txt      # 开发依赖
└── pyproject.toml           # 项目配置
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

### 核心端点（`/api/v1`）

- `GET /` — 根端点
- `GET /health` — 健康检查
- `GET /release` — 发布台账
- `GET /health/ready` — 就绪探针（数据库探活）

**认证**（`/api/v1/auth/`）: register、login
**用户**（`/api/v1/users/`）: me (GET/DELETE)
**画像**（`/api/v1/profile/`）: POST/GET/PUT
**衣橱**（`/api/v1/wardrobe/`）: CRUD + split-outfit；简化版（`/api/v1/wardrobe/simple/`）
**识别**（`/api/v1/recognition/`）: analyze、category、colors、categories
**分析**（`/api/v1/analysis/`）: similarity、outfits（多图）、suitability（三维原因说明）
**智能穿搭**（`/api/v1/smart-outfit/`）: weather、weather-by-city、upload-reference、generate
**情绪**（`/api/v1/mood/`）: quick-recall、recommend
**虚拟试衣**（`/api/v1/tryon/`）: garment（v1，SD Inpainting + fallback）
**套装收藏**（`/api/v1/outfit-collections/`）: CRUD
**反馈**（`/api/v1/feedback/events`）: like/dislike/adopt/view
**分析**（`/api/v1/analytics/`）: summary、dependency-observability
**意图路由**（`/api/v1/agent/intent`）: 自然语言 → MCP 工具名
**记忆 RAG**（`/api/v1/memory/snippets`）: POST/GET/DELETE + 搜索
**订阅**（`/api/v1/subscription/`）: 管理；`/api/v1/subscription/usage`: 用量

### 虚拟试衣 v2（`/api/v2`）

- `POST /api/v2/tryon/garment` — 多模式试衣（mode: strict/balanced/replace/realistic/professional）
- `POST /api/v2/tryon/validate-input` — 输入门禁评估
- `POST /api/v2/tryon/preprocess` — 衣物预处理（自动品类检测）
- `POST /api/v2/tryon/preprocess-batch` — 批量预处理
- `GET /api/v2/tryon/capabilities` — 能力开关
- `GET /api/v2/tryon/model-status` — 引擎就绪诊断

### AI 穿搭风格分（无前缀）

- `POST /predict` — sklearn 风格分 + Top3 推荐

> 完整 API 以 http://127.0.0.1:8010/docs（Swagger）为准。业务路径均在 `/api/v1/...` 或 `/api/v2/...` 下。

## 环境变量

查看 `.env.example` 文件了解所有可配置的环境变量。

关键配置：
- `DATABASE_URL` - PostgreSQL 数据库连接
- `REDIS_URL` - Redis 缓存连接
- `JWT_SECRET_KEY` - JWT 密钥（生产环境必须修改）
- `CORS_ORIGINS` - 允许的跨域来源
- `AI_RECOMMENDER_ENABLED` - 是否启用 AI 推荐解释层
- `AI_RECOMMENDER_API_BASE_URL` - OpenAI 兼容接口地址
- `AI_RECOMMENDER_API_KEY` - AI 推荐接口密钥
- `AI_RECOMMENDER_MODEL` - AI 推荐模型名（默认 `gpt-4o-mini`）

## 模型说明

- **FashionCLIP**（`transformers` + `torch`）：零样本品类/风格/场景识别，非 TensorFlow/MobileNetV2
- **虚拟试衣**：`torch` + `torchvision` 须版本匹配；`diffusers` SD Inpainting 作 fallback
- **HuggingFace**：在 `.env` 设置 `HF_ENDPOINT=https://hf-mirror.com`（弱网加速）；`HF_HUB_DOWNLOAD_TIMEOUT` 等已在 Settings 声明
