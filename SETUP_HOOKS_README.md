# Git Hooks 安装说明

## ✅ 问题已解决

`.pre-commit-config.yaml` 文件现在已经在项目根目录了。

## 🚀 快速安装

### 从项目根目录运行（重要！）

```powershell
# 1. 确保在项目根目录
cd D:\Users\omen\OneDrive\桌面\clothing-assistant

# 2. 运行安装脚本
.\setup-hooks.ps1
```

## 📁 文件位置

- ✅ `.pre-commit-config.yaml` - 项目根目录
- ✅ `backend/.secrets.baseline` - backend 目录
- ✅ `setup-hooks.ps1` - 项目根目录（PowerShell）
- ✅ `setup-hooks.bat` - 项目根目录（CMD）
- ✅ `setup-hooks.sh` - 项目根目录（Linux/Mac）

## 🔧 手动安装（如果脚本失败）

```powershell
# 1. 确保在项目根目录
cd D:\Users\omen\OneDrive\桌面\clothing-assistant

# 2. 激活虚拟环境（可选）
.\backend\venv\Scripts\Activate.ps1

# 3. 安装工具
pip install pre-commit==4.0.1 detect-secrets==1.5.0

# 4. 安装 hooks
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

# 5. 初始化密钥检测
detect-secrets scan > backend\.secrets.baseline

# 6. 验证安装
pre-commit run --all-files
```

## ✅ 验证安装

```powershell
# 检查 hooks 是否已安装
ls .git\hooks

# 应该看到这些文件（没有 .sample 后缀）：
# - pre-commit
# - commit-msg
# - pre-push
```

## 🧪 测试

```powershell
# 测试提交消息验证
git commit --allow-empty -m "test"  # 应该被拒绝
git commit --allow-empty -m "test: verify hooks"  # 应该成功
```

## 📚 详细文档

- **完整指南**: `backend/GIT_HOOKS.md`
- **提交规范**: `backend/COMMIT_CONVENTION.md`
- **手动安装**: `backend/MANUAL_INSTALL.md`

## ⚠️ 常见问题

### Q: 为什么之前失败了？

A: `.pre-commit-config.yaml` 文件之前在 `backend/` 目录，但 pre-commit 需要它在项目根目录。现在已经修复。

### Q: 我应该从哪里运行脚本？

A: 从项目根目录（有 `.git` 文件夹的地方），不是 `backend/` 目录。

### Q: 如何确认我在正确的目录？

```powershell
# 检查当前目录
pwd

# 应该显示：
# D:\Users\omen\OneDrive\桌面\clothing-assistant

# 检查是否有 .git 文件夹
ls .git
```

---

**现在试试运行 `.\setup-hooks.ps1`，应该可以正常工作了！**
