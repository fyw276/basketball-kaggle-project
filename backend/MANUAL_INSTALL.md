# Git Hooks 手动安装指南

如果自动安装脚本遇到问题，请按照以下步骤手动安装。

## 前提条件

1. 确保在项目根目录（有 `.git` 文件夹）
2. 确保 Python 已安装（3.11+）
3. 建议激活虚拟环境

## 安装步骤

### 步骤 1: 进入项目根目录

```powershell
cd D:\Users\omen\OneDrive\桌面\clothing-assistant
```

### 步骤 2: 激活虚拟环境（推荐）

```powershell
.\backend\venv\Scripts\Activate.ps1
```

如果遇到执行策略错误：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\backend\venv\Scripts\Activate.ps1
```

### 步骤 3: 安装 pre-commit 和 detect-secrets

```powershell
pip install pre-commit==4.0.1 detect-secrets==1.5.0
```

### 步骤 4: 安装 Git hooks

```powershell
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push
```

你应该看到类似的输出：

```
pre-commit installed at .git\hooks\pre-commit
pre-commit installed at .git\hooks\commit-msg
pre-commit installed at .git\hooks\pre-push
```

### 步骤 5: 初始化密钥检测基线

```powershell
# 确保在项目根目录
detect-secrets scan > .secrets.baseline
```

或者使用与 pre-commit 参数一致的命令：

```powershell
detect-secrets scan --baseline .secrets.baseline
```

**注意：** 配置文件中引用的是根目录 `.secrets.baseline`。

### 步骤 6: 验证安装

```powershell
pre-commit run --all-files
```

第一次运行会下载和安装所有工具，可能需要几分钟。

## 验证 Hooks 是否安装成功

检查 `.git\hooks` 目录：

```powershell
ls .git\hooks
```

你应该看到以下文件（没有 `.sample` 后缀）：

- `pre-commit`
- `commit-msg`
- `pre-push`

## 测试 Hooks

### 测试 Pre-commit Hook

```powershell
# 创建一个测试文件
echo "# Test" > test.txt

# 暂存文件
git add test.txt

# 提交（hooks 会自动运行）
git commit -m "test: verify hooks"
```

### 测试 Commit-msg Hook

尝试使用错误的提交消息格式：

```powershell
git commit -m "update code"
```

应该会被拒绝，并显示错误消息。

正确的格式：

```powershell
git commit -m "feat: add new feature"
```

## 常见问题

### Q: pre-commit 命令找不到

**解决方案：** 确保虚拟环境已激活，或者使用完整路径：

```powershell
.\backend\venv\Scripts\pre-commit.exe install --hook-type pre-commit
```

### Q: detect-secrets 命令找不到

**解决方案：** 确保已安装：

```powershell
pip install detect-secrets==1.5.0
```

### Q: Hooks 没有运行

**解决方案：** 检查 `.git\hooks` 目录中的文件是否存在且没有 `.sample` 后缀。

### Q: 权限错误

**解决方案：** 以管理员身份运行 PowerShell。

## 手动运行 Hooks

如果想在不提交的情况下测试 hooks：

```powershell
# 运行所有 hooks
pre-commit run --all-files

# 运行特定 hook
pre-commit run black --all-files
pre-commit run flake8 --all-files
pre-commit run mypy --all-files
```

## 卸载 Hooks

如果需要卸载：

```powershell
pre-commit uninstall --hook-type pre-commit
pre-commit uninstall --hook-type commit-msg
pre-commit uninstall --hook-type pre-push
```

## 跳过 Hooks

在紧急情况下可以跳过 hooks：

```powershell
# 跳过 pre-commit 和 commit-msg
git commit --no-verify -m "emergency fix"

# 跳过 pre-push
git push --no-verify
```

## 更新 Hooks

更新到最新版本：

```powershell
pre-commit autoupdate
pre-commit install --hook-type pre-commit --overwrite
pre-commit install --hook-type commit-msg --overwrite
pre-commit install --hook-type pre-push --overwrite
```

## 完整的安装命令（复制粘贴）

如果你想一次性运行所有命令，复制以下内容到 PowerShell：

```powershell
# 进入项目根目录
cd D:\Users\omen\OneDrive\桌面\clothing-assistant

# 激活虚拟环境（可选）
.\backend\venv\Scripts\Activate.ps1

# 安装工具
pip install pre-commit==4.0.1 detect-secrets==1.5.0

# 安装 hooks
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

# 初始化密钥检测
detect-secrets scan > .secrets.baseline

# 验证安装
pre-commit run --all-files
```

## 获取帮助

如果仍有问题：

1. 查看 [GIT_HOOKS.md](GIT_HOOKS.md) 的"故障排除"部分
2. 查看 [QUICK_INSTALL.md](QUICK_INSTALL.md)
3. 在项目 Issues 中提问

---

**提示：** 手动安装后，hooks 会在每次 `git commit` 和 `git push` 时自动运行。
