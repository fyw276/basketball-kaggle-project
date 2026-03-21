# 修复 Python 版本问题

## 问题

Pre-commit 配置要求 Python 3.11，但你的系统安装的是 Python 3.12。

## ✅ 已修复

配置文件已更新为使用系统 Python 版本（兼容 3.12-3.14）。

## 🚀 快速修复

运行以下命令清理缓存并重新安装：

```powershell
# 方式 1: 使用修复脚本（推荐）
.\fix-hooks.ps1
```

或者手动执行：

```powershell
# 方式 2: 手动清理和重装
# 1. 清理缓存
pre-commit clean
pre-commit gc

# 2. 卸载旧 hooks
pre-commit uninstall --hook-type pre-commit
pre-commit uninstall --hook-type commit-msg
pre-commit uninstall --hook-type pre-push

# 3. 重新安装
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

# 4. 测试
pre-commit run --all-files
```

## 📝 更改内容

### 1. `.pre-commit-config.yaml`

```yaml
# 之前：
default_language_version:
  python: python3.11

# 现在：
default_language_version:
  python: python3  # 使用系统 Python
```

### 2. `backend/pyproject.toml`

```toml
# 之前：
[tool.black]
target-version = ['py311']

[tool.mypy]
python_version = "3.11"

# 现在：
[tool.black]
target-version = ['py312']

[tool.mypy]
python_version = "3.12"
```

## ✅ 验证修复

```powershell
# 检查 Python 版本
python --version
# 应该显示：Python 3.12.x

# 测试 pre-commit
pre-commit run --all-files
# 应该成功运行所有 hooks
```

## 🧪 测试提交

```powershell
# 创建测试提交
git commit --allow-empty -m "test: verify hooks with Python 3.12"
```

## ⚠️ 如果仍有问题

### 选项 1: 删除整个缓存

```powershell
# 删除 pre-commit 缓存目录
Remove-Item -Recurse -Force $env:USERPROFILE\.cache\pre-commit

# 重新运行
pre-commit run --all-files
```

### 选项 2: 跳过有问题的 hooks

临时跳过某些 hooks：

```powershell
# 跳过 mypy（如果它有问题）
$env:SKIP = "mypy"
pre-commit run --all-files
```

### 选项 3: 简化配置

如果问题持续，可以暂时禁用某些 hooks。编辑 `.pre-commit-config.yaml`，注释掉有问题的部分。

## 📚 相关文档

- Python 版本兼容性：Python 3.12 完全兼容本项目
- Pre-commit 文档：https://pre-commit.com/

---

**提示：** 修复后，hooks 会在每次 `git commit` 时自动运行。
