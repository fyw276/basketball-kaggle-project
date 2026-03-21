# Git Hooks 简化配置说明

## ✅ 问题已解决

Mypy 的 `types-all` 包在 Python 3.12 上有依赖问题，已从 pre-commit 配置中移除。

## 🎯 当前配置的 Hooks

### Pre-commit Hook（提交前）

✅ **文件检查**
- 移除行尾空格
- 确保文件以换行符结尾
- 检查 YAML/JSON/TOML 格式
- 检查大文件（>1MB）
- 检查合并冲突
- 检查 debug 语句

✅ **安全检查**
- 检测密钥和敏感信息（detect-secrets）

✅ **Python 代码质量**
- Black 格式化（自动修复）
- isort 导入排序（自动修复）
- flake8 代码检查

❌ **已移除**
- mypy 类型检查（因为依赖问题）

### Commit-msg Hook（提交消息）

✅ 强制使用 Conventional Commits 格式

### Pre-push Hook（推送前）

✅ 运行 pytest 测试

## 🚀 立即修复

运行修复脚本：

```powershell
.\fix-hooks.ps1
```

这个脚本会：
1. 清理所有缓存
2. 删除旧的 hooks
3. 重新安装 hooks
4. 测试运行

## 📝 手动运行 Mypy

虽然 mypy 不在 pre-commit hooks 中，你仍然可以手动运行：

```powershell
# 激活虚拟环境
.\backend\venv\Scripts\Activate.ps1

# 运行 mypy
mypy backend/app

# 或者在 backend 目录中
cd backend
mypy app
```

## ✅ 验证安装

```powershell
# 1. 运行修复脚本
.\fix-hooks.ps1

# 2. 检查 hooks 文件
ls .git\hooks

# 应该看到：
# - pre-commit
# - commit-msg
# - pre-push

# 3. 测试提交
git commit --allow-empty -m "test: verify simplified hooks"
```

## 🎯 为什么移除 Mypy？

1. **依赖问题**: `types-all` 包在 Python 3.12 上有依赖冲突
2. **速度**: Mypy 在 pre-commit 中运行较慢
3. **灵活性**: 手动运行 mypy 可以更好地控制检查范围

## 💡 最佳实践

### 提交前

```powershell
# 1. 格式化代码（hooks 会自动做）
black backend/
isort backend/

# 2. 检查代码质量
flake8 backend/

# 3. 手动运行类型检查（可选）
mypy backend/app

# 4. 提交
git add .
git commit -m "feat: your message"
```

### 推送前

```powershell
# 运行测试（hooks 会自动做）
cd backend
pytest

# 推送
git push
```

## 🔧 如果还有问题

### 完全重置

```powershell
# 1. 删除所有缓存
Remove-Item -Recurse -Force $env:USERPROFILE\.cache\pre-commit

# 2. 卸载 hooks
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

### 跳过特定 Hook

如果某个 hook 有问题，可以临时跳过：

```powershell
# 跳过 flake8
$env:SKIP = "flake8"
git commit -m "feat: your message"

# 清除环境变量
Remove-Item Env:\SKIP
```

### 完全跳过 Hooks

紧急情况下：

```powershell
git commit --no-verify -m "emergency fix"
```

## 📊 性能对比

| Hook | 之前（含 mypy） | 现在（无 mypy） |
|------|----------------|----------------|
| Pre-commit | ~30-60 秒 | ~5-10 秒 |
| 首次运行 | ~5 分钟 | ~2 分钟 |

## 📚 相关文档

- **完整指南**: `backend/GIT_HOOKS.md`
- **提交规范**: `backend/COMMIT_CONVENTION.md`
- **手动安装**: `backend/MANUAL_INSTALL.md`
- **Python 版本修复**: `FIX_PYTHON_VERSION.md`

## ✨ 总结

- ✅ Hooks 已简化，移除了有问题的 mypy
- ✅ 仍然保留了所有重要的检查（格式化、linting、安全）
- ✅ 可以手动运行 mypy 进行类型检查
- ✅ 性能更快，依赖问题更少

---

**现在运行 `.\fix-hooks.ps1` 即可完成修复！**
