# Git Hooks 设置总结

## 完成的工作

### 1. 更新和优化 Pre-commit 配置

**文件：** `backend/.pre-commit-config.yaml`

**改进：**
- ✅ 更新所有 hooks 到最新版本
  - pre-commit-hooks: v4.5.0 → v5.0.0
  - black: 23.11.0 → 24.10.0
  - isort: 5.12.0 → 5.13.2
  - flake8: 6.1.0 → 7.1.1
  - mypy: v1.7.1 → v1.14.1
- ✅ 添加密钥检测（detect-secrets）
- ✅ 添加 commit-msg hook（conventional-pre-commit）
- ✅ 添加 pre-push hook（pytest）
- ✅ 配置 stages 以优化性能
- ✅ 添加 CI 配置
- ✅ 更新 Python 版本目标为 3.11（兼容 3.14）

### 2. 更新项目配置

**文件：** `backend/pyproject.toml`

**改进：**
- ✅ 修复文件格式错误
- ✅ 更新 Python 版本目标：3.9 → 3.11
- ✅ 保持所有工具配置一致

**文件：** `backend/requirements-dev.txt`

**改进：**
- ✅ 更新所有开发依赖到最新版本
- ✅ 添加 detect-secrets==1.5.0
- ✅ 更新 pre-commit==4.0.1

### 3. 创建安装脚本

**文件：** `backend/setup-hooks.sh` (Linux/Mac)

**功能：**
- ✅ 自动检查环境
- ✅ 安装 pre-commit 和 detect-secrets
- ✅ 安装所有 Git hooks
- ✅ 初始化密钥检测基线
- ✅ 验证安装
- ✅ 显示使用说明

**文件：** `backend/setup-hooks.bat` (Windows)

**功能：**
- ✅ 与 shell 脚本相同的功能
- ✅ 中文界面
- ✅ Windows 兼容

### 4. 创建文档

**文件：** `backend/GIT_HOOKS.md`

**内容：**
- ✅ 完整的安装指南
- ✅ 所有 hooks 的详细说明
- ✅ 使用示例
- ✅ 故障排除
- ✅ 最佳实践
- ✅ CI/CD 集成说明

**文件：** `backend/COMMIT_CONVENTION.md`

**内容：**
- ✅ Conventional Commits 规范
- ✅ 类型和范围说明
- ✅ 示例和反例
- ✅ 快速参考表

**文件：** `backend/.secrets.baseline`

**功能：**
- ✅ 密钥检测基线配置
- ✅ 预配置所有检测器

### 5. 更新项目文档

**文件：** `README.md`

**改进：**
- ✅ 添加 Git hooks 设置说明
- ✅ 更新安装步骤
- ✅ 添加快速安装命令

**文件：** `CONTRIBUTING.md`

**改进：**
- ✅ 添加 Git hooks 安装说明
- ✅ 更新开发环境设置
- ✅ 添加跳过 hooks 的说明

**文件：** `.gitignore`

**改进：**
- ✅ 添加 pre-commit 缓存忽略

## 配置的 Hooks

### Pre-commit Hook（提交前）

**运行时机：** `git commit`

**检查项目：**
1. 文件格式检查
   - 移除行尾空格
   - 确保文件以换行符结尾
   - 检查 YAML/JSON/TOML 格式
   - 检查大文件（>1MB）
   - 检查合并冲突
   - 检查混合行尾

2. 安全检查
   - 检测密钥和敏感信息（detect-secrets）

3. Python 代码质量
   - Black 格式化（自动修复）
   - isort 导入排序（自动修复）
   - flake8 代码检查
   - mypy 类型检查

**性能：** < 10 秒（通常）

### Commit-msg Hook（提交消息）

**运行时机：** `git commit`

**检查项目：**
- 验证提交消息格式（Conventional Commits）
- 强制使用类型前缀（feat, fix, docs, etc.）
- 要求提供范围（scope）

**示例：**
```bash
✓ feat(api): add user authentication
✓ fix(db): resolve connection leak
✗ update code
✗ fix bug
```

### Pre-push Hook（推送前）

**运行时机：** `git push`

**检查项目：**
- 运行所有测试（pytest）
- 在第一个失败时停止（-x）

**性能：** 取决于测试数量

## 使用方法

### 安装 Hooks

**一键安装（推荐）：**

```bash
cd backend

# Windows
setup-hooks.bat

# Linux/Mac
chmod +x setup-hooks.sh
./setup-hooks.sh
```

**手动安装：**

```bash
pip install pre-commit==4.0.1 detect-secrets==1.5.0
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push
detect-secrets scan > backend/.secrets.baseline
```

### 正常工作流

```bash
# 1. 修改代码
vim app/main.py

# 2. 暂存更改
git add app/main.py

# 3. 提交（hooks 自动运行）
git commit -m "feat(api): add health check endpoint"

# 4. 推送（运行测试）
git push origin main
```

### 手动运行

```bash
# 运行所有 hooks
pre-commit run --all-files

# 运行特定 hook
pre-commit run black --all-files
pre-commit run pytest-check --all-files

# 只检查暂存的文件
pre-commit run
```

### 跳过 Hooks（紧急情况）

```bash
# 跳过 pre-commit 和 commit-msg
git commit --no-verify -m "emergency fix"

# 跳过 pre-push
git push --no-verify
```

## 最佳实践

1. **始终安装 hooks** - 所有开发者都应该安装 hooks
2. **不要跳过 hooks** - 除非紧急情况
3. **修复后提交** - 不要提交未通过检查的代码
4. **使用规范的提交消息** - 遵循 Conventional Commits
5. **定期更新** - 运行 `pre-commit autoupdate`

## 性能优化

1. **缓存** - Pre-commit 自动缓存工具和依赖
2. **只检查更改的文件** - 默认只检查暂存的文件
3. **并行运行** - 某些 hooks 可以并行运行
4. **CI 跳过** - 在 CI 环境中自动跳过某些 hooks

## CI/CD 集成

Hooks 配置为在 CI 环境中自动跳过，避免重复运行。

**GitHub Actions 示例：**

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install -r backend/requirements-dev.txt
      - name: Run pre-commit
        run: |
          cd backend
          pre-commit run --all-files
      - name: Run tests
        run: |
          cd backend
          pytest
```

## 故障排除

### Hook 运行失败

```bash
# 查看详细错误
pre-commit run --all-files --verbose

# 清理缓存并重试
pre-commit clean
pre-commit run --all-files
```

### 格式化冲突

```bash
# 先运行 isort
isort .

# 再运行 Black
black .

# 提交
git add .
git commit -m "style: format code"
```

### 密钥检测误报

```bash
# 更新基线
detect-secrets scan --baseline backend/.secrets.baseline

# 或在代码中添加注释
password = "fake-password"  # pragma: allowlist secret
```

## 文件清单

### 配置文件
- ✅ `backend/.pre-commit-config.yaml` - Pre-commit 配置
- ✅ `backend/pyproject.toml` - 工具配置
- ✅ `backend/.secrets.baseline` - 密钥检测基线
- ✅ `.gitignore` - Git 忽略规则

### 脚本
- ✅ `backend/setup-hooks.sh` - Linux/Mac 安装脚本
- ✅ `backend/setup-hooks.bat` - Windows 安装脚本

### 文档
- ✅ `backend/GIT_HOOKS.md` - 完整的 Git Hooks 指南
- ✅ `backend/COMMIT_CONVENTION.md` - 提交消息规范
- ✅ `backend/HOOKS_SETUP_SUMMARY.md` - 本文档
- ✅ `README.md` - 项目主文档（已更新）
- ✅ `CONTRIBUTING.md` - 贡献指南（已更新）

## 下一步

1. **安装 hooks**：运行 `setup-hooks.bat` 或 `setup-hooks.sh`
2. **验证安装**：运行 `pre-commit run --all-files`
3. **测试提交**：尝试提交一些代码
4. **阅读文档**：查看 `GIT_HOOKS.md` 了解详细信息

## 参考资源

- [pre-commit 官方文档](https://pre-commit.com/)
- [Conventional Commits 规范](https://www.conventionalcommits.org/)
- [Black 代码风格](https://black.readthedocs.io/)
- [detect-secrets 文档](https://github.com/Yelp/detect-secrets)

---

**创建日期：** 2026-03-21
**最后更新：** 2026-03-21
**版本：** 1.0.0
