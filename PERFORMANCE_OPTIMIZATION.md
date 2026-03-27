# 性能优化指南

## 问题诊断

如果你遇到以下问题：
- ✗ VS Code/Kiro 聊天加载超时
- ✗ IDE 启动缓慢
- ✗ 文件搜索很慢
- ✗ CPU/内存占用高

**原因**：项目包含大量文件（60,000+ 文件，4+ GB），主要来自：
- `backend/venv/` - 30,000+ 文件
- `venv/` - 21,000+ 文件
- `mobile/.dart_tool/` - 大量缓存

## 快速修复

### 方案 1：清理缓存（推荐）

**Windows:**
```powershell
.\cleanup.ps1
```

**Linux/Mac:**
```bash
./cleanup.sh
```

然后重启 IDE。

### 方案 2：移动虚拟环境到项目外（最佳）

**为什么？** 虚拟环境不应该在项目目录内，这会导致 IDE 扫描大量不必要的文件。

#### Windows (PowerShell):
```powershell
# 1. 停用当前虚拟环境
deactivate

# 2. 移动虚拟环境到用户目录
Move-Item backend/venv $env:USERPROFILE\.virtualenvs\clothing-assistant-backend
Move-Item venv $env:USERPROFILE\.virtualenvs\clothing-assistant-root

# 3. 创建新的虚拟环境（推荐使用 venv 在项目外）
python -m venv $env:USERPROFILE\.virtualenvs\clothing-assistant

# 4. 激活新环境
& $env:USERPROFILE\.virtualenvs\clothing-assistant\Scripts\Activate.ps1

# 5. 安装依赖
pip install -r backend/requirements.txt
```

#### Linux/Mac (Bash):
```bash
# 1. 停用当前虚拟环境
deactivate

# 2. 移动虚拟环境到用户目录
mkdir -p ~/.virtualenvs
mv backend/venv ~/.virtualenvs/clothing-assistant-backend
mv venv ~/.virtualenvs/clothing-assistant-root

# 3. 创建新的虚拟环境
python3 -m venv ~/.virtualenvs/clothing-assistant

# 4. 激活新环境
source ~/.virtualenvs/clothing-assistant/bin/activate

# 5. 安装依赖
pip install -r backend/requirements.txt
```

### 方案 3：使用 Poetry 或 Conda（推荐）

**Poetry** (自动管理虚拟环境在项目外):
```bash
pip install poetry
cd backend
poetry install
```

**Conda**:
```bash
conda create -n clothing-assistant python=3.11
conda activate clothing-assistant
pip install -r backend/requirements.txt
```

## 验证修复

运行以下命令检查文件数：
```powershell
Get-ChildItem -Recurse -File | Measure-Object | Select-Object -ExpandProperty Count
```

**期望结果**：< 2,000 个文件

## 配置文件说明

项目已包含以下配置文件，确保跨平台兼容：

| 文件 | 用途 | 支持的工具 |
|------|------|-----------|
| `.vscode/settings.json` | VS Code 配置 | VS Code, Cursor |
| `.kiro/settings.json` | Kiro 配置 | Kiro |
| `.editorconfig` | 编辑器通用配置 | 所有主流编辑器 |
| `.gitignore` | Git 忽略规则 | Git |
| `.gitattributes` | Git 属性配置 | Git |

## 最佳实践

1. ✅ **始终在项目外创建虚拟环境**
2. ✅ **定期运行清理脚本**
3. ✅ **使用 .gitignore 排除大文件**
4. ✅ **配置 IDE 排除不必要的目录**
5. ✅ **使用 Poetry/Conda 管理依赖**

## 进一步优化

如果问题仍然存在：

1. **检查 backend 目录**：
   ```powershell
   Get-ChildItem backend -Recurse -File | Measure-Object | Select-Object -ExpandProperty Count
   ```
   应该 < 500 个文件

2. **检查 mobile 目录**：
   ```powershell
   Get-ChildItem mobile -Recurse -File | Measure-Object | Select-Object -ExpandProperty Count
   ```
   应该 < 200 个文件

3. **清理 Flutter 缓存**：
   ```bash
   cd mobile
   flutter clean
   ```

## 支持

如果按照以上步骤操作后问题仍未解决，请检查：
- IDE 版本是否最新
- 磁盘空间是否充足
- 防病毒软件是否干扰
