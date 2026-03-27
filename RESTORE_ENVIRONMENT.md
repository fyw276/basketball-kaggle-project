# 虚拟环境恢复指南

## 选择方案

### 方案 A：移动虚拟环境（安全，推荐）

**优点**：保留备份，可以随时恢复
**缺点**：占用磁盘空间

```powershell
.\move_venv.ps1
```

### 方案 B：删除虚拟环境（彻底）

**优点**：释放磁盘空间
**缺点**：需要重新下载依赖（约 5-10 分钟）

```powershell
.\remove_venv.ps1
```

## 重新创建虚拟环境

### 步骤 1：创建虚拟环境

**在项目根目录（不推荐，会再次导致性能问题）：**
```powershell
python -m venv venv
```

**在项目外（推荐）：**
```powershell
# 创建在用户目录
python -m venv $env:USERPROFILE\.virtualenvs\clothing-assistant

# 或使用 Poetry（最推荐）
pip install poetry
cd backend
poetry install
```

### 步骤 2：激活虚拟环境

**Windows (PowerShell):**
```powershell
# 如果在项目内
.\venv\Scripts\Activate.ps1

# 如果在项目外
& $env:USERPROFILE\.virtualenvs\clothing-assistant\Scripts\Activate.ps1

# 如果使用 Poetry
poetry shell
```

**Linux/Mac:**
```bash
# 如果在项目内
source venv/bin/activate

# 如果在项目外
source ~/.virtualenvs/clothing-assistant/bin/activate

# 如果使用 Poetry
poetry shell
```

### 步骤 3：安装依赖

```powershell
# 进入 backend 目录
cd backend

# 安装依赖
pip install -r requirements.txt

# 或使用 Poetry
poetry install
```

### 步骤 4：验证安装

```powershell
# 检查 Python 版本
python --version

# 检查已安装的包
pip list

# 测试 FastAPI
python -m uvicorn app.main:app --reload
```

## 验证性能改善

```powershell
# 检查文件数（应该 < 2000）
Get-ChildItem -Recurse -File | Measure-Object | Select-Object -ExpandProperty Count

# 检查项目大小（应该 < 500 MB）
Get-ChildItem -Recurse | Where-Object { $_.PSIsContainer -eq $false } | Measure-Object -Property Length -Sum | Select-Object @{Name="SizeMB";Expression={[math]::Round($_.Sum / 1MB, 2)}}
```

## 如果需要恢复原来的 venv

如果使用了方案 A（移动），可以恢复：

```powershell
# 恢复根目录 venv
Move-Item -Path "$env:USERPROFILE\.clothing-assistant-venv-backup\venv-root" -Destination "venv" -Force

# 恢复 backend/venv
Move-Item -Path "$env:USERPROFILE\.clothing-assistant-venv-backup\venv-backend" -Destination "backend/venv" -Force
```

## 最佳实践建议

**强烈建议使用 Poetry**，它会自动管理虚拟环境在项目外：

```powershell
# 安装 Poetry
pip install poetry

# 配置 Poetry 在项目外创建虚拟环境
poetry config virtualenvs.in-project false

# 初始化项目
cd backend
poetry install

# 以后使用
poetry shell  # 激活环境
poetry add package-name  # 添加依赖
poetry run python script.py  # 运行脚本
```

## 故障排除

### 问题：VS Code 找不到 Python 解释器

**解决**：
1. Ctrl+Shift+P
2. 输入 "Python: Select Interpreter"
3. 选择你的虚拟环境

### 问题：依赖安装失败

**解决**：
```powershell
# 升级 pip
python -m pip install --upgrade pip

# 清理缓存
pip cache purge

# 重新安装
pip install -r backend/requirements.txt
```

### 问题：Poetry 安装慢

**解决**：
```powershell
# 使用国内镜像（如果在中国）
poetry source add --priority=primary tsinghua https://pypi.tuna.tsinghua.edu.cn/simple/
```
