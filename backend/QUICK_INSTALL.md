# Git Hooks 快速安装指南

## 🚀 一键安装

### Windows PowerShell（推荐）

```powershell
# 1. 进入 backend 目录
cd backend

# 2. 运行安装脚本
.\setup-hooks.ps1
```

**如果脚本遇到问题，请查看 [手动安装指南](MANUAL_INSTALL.md)**

### Windows CMD

```cmd
# 1. 进入 backend 目录
cd backend

# 2. 运行安装脚本
setup-hooks.bat
```

### Linux/Mac

```bash
# 1. 进入 backend 目录
cd backend

# 2. 添加执行权限
chmod +x setup-hooks.sh

# 3. 运行安装脚本
./setup-hooks.sh
```

## ⚠️ 常见问题

### PowerShell 执行策略错误

如果看到 "无法加载文件，因为在此系统上禁止运行脚本"：

```powershell
# 临时允许运行脚本（推荐）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 然后再次运行
.\setup-hooks.ps1
```

或者：

```powershell
# 绕过执行策略运行
powershell -ExecutionPolicy Bypass -File .\setup-hooks.ps1
```

### 不在 Git 仓库中

确保你在项目的 `backend` 目录下运行脚本：

```powershell
# 检查当前位置
pwd

# 应该显示类似：
# D:\Users\omen\OneDrive\桌面\clothing-assistant\backend

# 如果不在 backend 目录，先进入
cd D:\Users\omen\OneDrive\桌面\clothing-assistant\backend
```

### Python 未安装

确保 Python 已安装并在 PATH 中：

```powershell
# 检查 Python 版本
python --version

# 应该显示：Python 3.11+ 或 3.14
```

### 虚拟环境未激活

建议先激活虚拟环境：

```powershell
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 然后运行安装脚本
.\setup-hooks.ps1
```

## ✅ 验证安装

安装完成后，验证 hooks 是否正常工作：

```powershell
# 手动运行所有 hooks
pre-commit run --all-files

# 应该看到所有检查都通过
```

## 📝 测试提交

尝试提交一些代码：

```powershell
# 1. 修改文件
echo "# Test" >> test.txt

# 2. 暂存文件
git add test.txt

# 3. 提交（hooks 会自动运行）
git commit -m "test: add test file"

# 如果提交消息格式不正确，会被拒绝
# 正确格式：type(scope): description
```

## 🎯 下一步

- 阅读完整文档：[GIT_HOOKS.md](GIT_HOOKS.md)
- 查看提交规范：[COMMIT_CONVENTION.md](COMMIT_CONVENTION.md)
- 开始开发！

## 💡 提示

- 使用 `git commit --no-verify` 可以跳过 hooks（紧急情况）
- 使用 `pre-commit run` 可以手动运行 hooks
- 使用 `pre-commit autoupdate` 可以更新 hooks 版本

---

**需要帮助？** 查看 [GIT_HOOKS.md](GIT_HOOKS.md) 的"故障排除"部分
