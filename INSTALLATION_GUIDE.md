# 安装指南

## 目录
- [Python 3.14 用户](#python-314-用户)
- [Python 3.9-3.12 用户](#python-39-312-用户)
- [常见问题](#常见问题)
- [故障排查](#故障排查)

---

## Python 3.14 用户

### 🎯 一键启动（推荐）

```bash
cd backend
quick_start_py314.bat
```

这个脚本会自动：
1. 检测 Python 版本
2. 创建/激活虚拟环境
3. 安装兼容 Python 3.14 的依赖
4. 创建配置文件
5. 启动服务器

**预计时间**: 2-3 分钟

### 📋 手动安装

如果你想手动执行每一步：

```bash
# 1. 进入后端目录
cd backend

# 2. 创建虚拟环境
python -m venv venv

# 3. 激活虚拟环境
venv\Scripts\activate

# 4. 升级 pip
python -m pip install --upgrade pip

# 5. 安装 Python 3.14 兼容依赖
pip install -r requirements-simple.txt

# 6. 创建配置文件
copy .env.example .env

# 7. 启动服务器
python run.py
```

### ⚠️ 为什么需要特殊处理？

Python 3.14 是最新版本，某些依赖包（如 `pydantic-core`）还没有提供预编译的二进制文件（wheel），需要从源代码编译，这需要 Rust 编译器。

**解决方案**: 使用 `requirements-simple.txt`，它包含了兼容 Python 3.14 的更新版本。

### 📦 requirements-simple.txt 包含什么？

```
fastapi==0.115.0          # Web 框架
uvicorn==0.32.0           # ASGI 服务器
pydantic==2.10.3          # 数据验证（兼容 Python 3.14）
pydantic-settings==2.6.1  # 配置管理
python-dotenv==1.0.1      # 环境变量
loguru==0.7.3             # 日志
pytest==8.3.4             # 测试框架
```

### 🎉 验证安装

启动成功后，访问：
- **主页**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

---

## Python 3.9-3.12 用户

### 🎯 一键启动（推荐）

```bash
cd backend
start.bat
```

或使用完全自动化脚本：

```bash
cd backend
fix_everything.bat
```

### 📋 手动安装

```bash
# 1. 进入后端目录
cd backend

# 2. 创建虚拟环境
python -m venv venv

# 3. 激活虚拟环境
venv\Scripts\activate

# 4. 升级 pip
python -m pip install --upgrade pip

# 5. 安装依赖（选择一个）
pip install -r requirements.txt           # 完整依赖
pip install -r requirements-minimal.txt   # 最小依赖（推荐）

# 6. 创建配置文件
copy .env.example .env

# 7. 启动服务器
python run.py
```

### 📦 依赖文件选择

| 文件 | 说明 | 适用场景 |
|------|------|----------|
| `requirements.txt` | 完整依赖，包含所有功能 | 生产环境、完整开发 |
| `requirements-minimal.txt` | 最小依赖，不含图像处理 | 快速测试、任务 1-4 |

**推荐**: 先使用 `requirements-minimal.txt`，等到任务 5（图像识别）时再安装完整依赖。

---

## 常见问题

### Q1: 如何检查 Python 版本？

```bash
python --version
```

### Q2: 虚拟环境激活失败（PowerShell）

**错误**:
```
无法加载文件 venv\Scripts\Activate.ps1，因为在此系统上禁止运行脚本
```

**解决**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q3: pip 安装速度慢

使用国内镜像：

```bash
pip install -r requirements-simple.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q4: 依赖安装失败

**步骤 1**: 升级 pip
```bash
python -m pip install --upgrade pip
```

**步骤 2**: 使用正确的依赖文件
- Python 3.14 → `requirements-simple.txt`
- Python 3.9-3.12 → `requirements-minimal.txt`

**步骤 3**: 运行诊断
```bash
cd backend
diagnose.bat
```

### Q5: 端口 8000 被占用

**方法 1**: 修改端口

编辑 `backend/.env`:
```
PORT=8001
```

**方法 2**: 释放端口

查找占用进程：
```bash
netstat -ano | findstr :8000
```

终止进程（管理员权限）：
```bash
taskkill /PID <进程ID> /F
```

### Q6: 导入错误 (ModuleNotFoundError)

确保：
1. 虚拟环境已激活（命令提示符显示 `(venv)`）
2. 在 `backend` 目录下运行
3. 依赖已安装（`pip list` 检查）

### Q7: 应该降级到 Python 3.11 吗？

**不需要**！`requirements-simple.txt` 已经解决了 Python 3.14 的兼容性问题。

但如果你想要最好的包兼容性和稳定性，Python 3.11 或 3.12 确实是更成熟的选择。

---

## 故障排查

### 自动诊断

```bash
cd backend
diagnose.bat
```

这个脚本会检查：
- ✓ Python 安装
- ✓ pip 工具
- ✓ 虚拟环境
- ✓ 配置文件
- ✓ 项目文件
- ✓ 依赖包

### 手动检查清单

1. **Python 版本**
   ```bash
   python --version
   ```
   应该显示 Python 3.9 或更高版本

2. **虚拟环境**
   ```bash
   cd backend
   venv\Scripts\activate
   ```
   命令提示符应该显示 `(venv)`

3. **依赖安装**
   ```bash
   pip show fastapi
   pip show pydantic
   ```
   应该显示版本信息

4. **配置文件**
   ```bash
   dir .env
   ```
   应该存在 `.env` 文件

5. **项目文件**
   ```bash
   dir app\main.py
   ```
   应该存在主应用文件

### 完全重置

如果遇到无法解决的问题，可以完全重置：

```bash
cd backend

# 删除虚拟环境
rmdir /s /q venv

# 删除配置文件
del .env

# 重新开始
fix_everything.bat
```

---

## 详细文档

- **backend/START_HERE.md** - 快速开始指南
- **backend/解决方案.md** - Python 3.14 完整解决方案
- **backend/立即运行.txt** - 一条命令解决
- **backend/QUICK_FIX.md** - 快速修复常见问题
- **backend/TROUBLESHOOTING.md** - 详细故障排查
- **backend/DEPENDENCIES.md** - 依赖安装策略

---

## 获取帮助

1. **查看文档** - 大多数问题在文档中都有解决方案
2. **运行诊断** - `diagnose.bat` 自动检查环境
3. **查看日志** - `backend/logs/app.log`（如果存在）
4. **简化问题** - 使用最小依赖文件测试

---

## 成功标志

当你看到以下输出时，说明安装成功：

```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

然后访问 http://localhost:8000/docs 查看 API 文档！🎉
