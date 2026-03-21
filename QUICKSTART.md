# 快速启动指南

## ✅ 任务 1 已完成！

项目基础设施已搭建完成，依赖已更新为支持 Python 3.14。现在你可以启动开发服务器了。

## 🚀 立即运行

### 方法 A: 一键启动（推荐 Windows 用户）

1. 进入后端目录：
```bash
cd backend
```

2. 双击运行 `start.bat` 或在命令行执行：
```bash
start.bat
```

### 方法 B: 手动步骤

#### 步骤 1: 进入后端目录

```bash
cd backend
```

#### 步骤 2: 创建虚拟环境

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 步骤 3: 升级 pip 并安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**注意：** `requirements.txt` 已更新为支持 Python 3.14 的最新版本依赖，包括：
- FastAPI 0.115.6
- Pydantic 2.10.5
- TensorFlow 2.18.0（支持 Python 3.14）
- 其他兼容 Python 3.14 的依赖包

#### 步骤 4: 创建环境配置文件

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

暂时使用默认配置即可，后续任务会配置数据库。

#### 步骤 5: 启动服务器

```bash
python run.py
```

或者：

```bash
uvicorn app.main:app --reload
```

### 步骤 6: 访问 API

打开浏览器访问：

- **API 文档 (Swagger UI)**: http://localhost:8000/docs
- **API 文档 (ReDoc)**: http://localhost:8000/redoc
- **根端点**: http://localhost:8000/
- **健康检查**: http://localhost:8000/health

## 🧪 运行测试

```bash
# 确保在 backend 目录下
pytest

# 查看详细输出
pytest -v

# 查看覆盖率
pytest --cov=app
```

## 📁 项目结构

```
clothing-assistant/
├── backend/                    ✅ 已创建
│   ├── app/
│   │   ├── main.py            ✅ FastAPI 应用
│   │   ├── core/
│   │   │   ├── config.py      ✅ 配置管理
│   │   │   └── logging.py     ✅ 日志配置
│   │   ├── api/               📁 API 路由（待添加）
│   │   ├── models/            📁 数据库模型（待添加）
│   │   ├── schemas/           📁 数据模式（待添加）
│   │   ├── services/          📁 业务逻辑（待添加）
│   │   └── db/                📁 数据库配置（待添加）
│   ├── tests/
│   │   └── test_main.py       ✅ 基础测试
│   ├── requirements.txt       ✅ Python 3.14 兼容依赖
│   ├── requirements-py314.txt ✅ Python 3.14 专用依赖（备份）
│   ├── .env.example           ✅ 环境变量示例
│   └── run.py                 ✅ 启动脚本
├── mobile/                     📁 Flutter 应用（待开发）
├── cli/                        📁 CLI 工具（待开发）
├── mcp/                        📁 MCP 服务（待开发）
├── models/                     📁 AI 模型（待添加）
├── .kiro/specs/               ✅ 规格文档
└── README.md                  ✅ 项目说明
```

## 🎯 当前状态

✅ **已完成:**
- 项目目录结构
- FastAPI 基础应用
- 配置管理系统
- 日志系统
- 开发工具配置（Black, isort, pytest等）
- 基础测试
- Python 3.14 依赖兼容性更新

⏳ **下一步 (任务 2):**
- 数据库设计与初始化
- PostgreSQL 配置
- SQLAlchemy ORM 设置
- Alembic 迁移

## 💡 Python 3.14 兼容性说明

本项目已针对 Python 3.14 进行优化：

- ✅ 所有依赖包都使用支持 Python 3.14 的最新版本
- ✅ TensorFlow 2.18.0 原生支持 Python 3.14
- ✅ Pydantic 2.10.5 完全兼容 Python 3.14
- ✅ 无需 Rust 编译器，所有包都有预编译的 wheel

如果你使用的是 Python 3.11-3.13，这些依赖包同样兼容。

## 💡 开发提示

### 查看日志

日志会输出到：
- 控制台（彩色输出）
- `backend/logs/app.log` 文件

### 代码格式化

```bash
# 格式化代码
black .
isort .
```

### 热重载

使用 `--reload` 参数启动服务器后，修改代码会自动重启服务器。

### API 测试

使用 Swagger UI (http://localhost:8000/docs) 可以直接测试 API 端点。

## ❓ 常见问题

### Q: 端口 8000 被占用？

修改 `.env` 文件中的 `PORT` 值：
```
PORT=8001
```

### Q: 虚拟环境激活失败？

Windows PowerShell 可能需要修改执行策略：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q: 依赖安装失败？

1. 确保 Python 版本正确：
```bash
python --version
```

2. 升级 pip 到最新版本：
```bash
pip install --upgrade pip
```

3. 如果仍然失败，请检查错误信息并确保网络连接正常。

### Q: TensorFlow 安装问题？

TensorFlow 2.18.0 原生支持 Python 3.14，如果安装失败：
1. 确保 pip 已更新到最新版本
2. 检查网络连接
3. 尝试单独安装：`pip install tensorflow==2.18.0`

## 📚 相关文档

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [Uvicorn 文档](https://www.uvicorn.org/)
- [TensorFlow 文档](https://www.tensorflow.org/)

## 🎉 恭喜！

任务 1 完成！你现在有一个可运行的 FastAPI 应用了，并且所有依赖都兼容 Python 3.14。

**准备好继续任务 2 了吗？** 告诉我："开始任务 2"
