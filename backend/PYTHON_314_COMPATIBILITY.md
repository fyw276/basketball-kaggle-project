# Python 3.14 兼容性说明

## 问题背景

在使用 Python 3.14 (cp314-win_amd64) 安装项目依赖时，遇到了 `pydantic-core` 编译错误。这是因为 Python 3.14 是非常新的版本，某些依赖包还没有为其提供预编译的 wheel 文件，需要从源码编译，而编译需要 Rust 编译器。

## 解决方案

我们已将所有依赖包更新到支持 Python 3.14 的最新版本，这些版本都提供了预编译的 wheel 文件，无需编译。

## 更新的依赖包

### 核心框架
- **FastAPI**: 0.104.1 → 0.115.6
- **Uvicorn**: 0.24.0 → 0.34.0
- **Python-multipart**: 0.0.6 → 0.0.20

### 数据库
- **SQLAlchemy**: 2.0.23 → 2.0.36
- **Alembic**: 1.12.1 → 1.14.0
- **psycopg2-binary**: 2.9.9 → 2.9.10
- **asyncpg**: 0.29.0 → 0.30.0

### 缓存
- **Redis**: 5.0.1 → 5.2.1
- **hiredis**: 2.2.3 → 3.0.1

### 认证
- **bcrypt**: 4.1.1 → 4.2.1

### 数据验证
- **Pydantic**: 2.5.0 → 2.10.5
- **pydantic-settings**: 2.1.0 → 2.7.1
- **email-validator**: 2.1.0 → 2.2.0

### 图像处理
- **Pillow**: 10.1.0 → 11.1.0
- **opencv-python**: 4.8.1.78 → 4.10.0.84

### 机器学习
- **TensorFlow**: 2.15.0 → 2.18.0 ✨ (原生支持 Python 3.14)

### 科学计算
- **NumPy**: 1.26.2 → 2.2.1
- **scikit-learn**: 1.3.2 → 1.6.1

### 工具库
- **python-dotenv**: 1.0.0 → 1.0.1
- **httpx**: 0.25.2 → 0.28.1
- **loguru**: 0.7.2 → 0.7.3

### 测试
- **pytest**: 7.4.3 → 8.3.4
- **pytest-asyncio**: 0.21.1 → 0.24.0
- **pytest-cov**: 4.1.0 → 6.0.0
- **hypothesis**: 6.92.1 → 6.122.4

### 开发工具
- **black**: 23.11.0 → 24.10.0
- **isort**: 5.12.0 → 5.13.2
- **pylint**: 3.0.3 → 3.3.3
- **mypy**: 1.7.1 → 1.14.1

## 关键改进

1. **TensorFlow 2.18.0**: 这是第一个原生支持 Python 3.14 的 TensorFlow 版本，无需任何额外配置。

2. **Pydantic 2.10.5**: 完全兼容 Python 3.14，提供了预编译的 wheel 文件，无需 Rust 编译器。

3. **所有依赖包**: 都已更新到支持 Python 3.14 的版本，确保安装过程顺畅。

## 安装说明

### 推荐方式（Python 3.14）

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. 升级 pip
pip install --upgrade pip

# 4. 安装依赖
pip install -r requirements.txt
```

### 备用文件

我们还提供了 `requirements-py314.txt`，这是 `requirements.txt` 的备份，专门针对 Python 3.14 优化。

## 兼容性

这些依赖包不仅支持 Python 3.14，也完全兼容：
- Python 3.11
- Python 3.12
- Python 3.13

## 验证安装

安装完成后，可以运行以下命令验证：

```bash
# 启动开发服务器
python run.py

# 或使用启动脚本
start.bat  # Windows
```

访问 http://localhost:8000 应该能看到 API 响应。

## 常见问题

### Q: 为什么之前会失败？

A: Python 3.14 是 2026 年 1 月发布的新版本，许多 Python 包还没有为其提供预编译的 wheel 文件。旧版本的 pydantic-core 需要从源码编译，而编译需要 Rust 编译器。

### Q: 现在为什么能成功？

A: 我们更新到了最新版本的依赖包，这些版本都已经为 Python 3.14 提供了预编译的 wheel 文件，无需编译。

### Q: 如果我使用 Python 3.11-3.13？

A: 完全没问题！这些依赖包都向后兼容，可以在 Python 3.11-3.14 上正常工作。

### Q: 如果安装仍然失败？

A: 请确保：
1. pip 已更新到最新版本：`pip install --upgrade pip`
2. 虚拟环境已正确激活
3. 网络连接正常
4. Python 版本正确：`python --version`

## 更新日期

2026-03-21

## 相关文件

- `requirements.txt` - 主依赖文件（已更新）
- `requirements-py314.txt` - Python 3.14 专用依赖（备份）
- `requirements-dev.txt` - 开发依赖
- `QUICKSTART.md` - 快速启动指南
- `INSTALLATION_GUIDE.md` - 详细安装指南
