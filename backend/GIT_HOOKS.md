# Git Hooks 配置指南

本项目使用 [pre-commit](https://pre-commit.com/) 框架管理 Git hooks，确保代码质量和一致性。

## 快速开始

### 一键安装（推荐）

从**仓库根目录**（存在 `.git` 与 `.pre-commit-config.yaml` 的目录）执行：

**Windows PowerShell:**
```powershell
cd D:\path\to\clothing-assistant
.\setup-hooks.ps1
```

**Windows CMD:**
```cmd
cd D:\path\to\clothing-assistant
setup-hooks.bat
```

**Linux/Mac:**
```bash
cd /path/to/clothing-assistant
chmod +x setup-hooks.sh
./setup-hooks.sh
```

### 手动安装

```bash
# 在仓库根目录
# 1. 安装 pre-commit
pip install pre-commit==4.0.1 detect-secrets==1.5.0

# 2. 安装 hooks
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

# 3. 密钥基线（根目录 .secrets.baseline，与 .pre-commit-config.yaml 中 detect-secrets 一致）
detect-secrets scan > .secrets.baseline

# 4. 验证安装
pre-commit run --all-files
```

## 已配置的 Hooks

### 1. Pre-commit Hook（提交前）

在每次 `git commit` 时自动运行，检查暂存的文件。

**检查项目：**
- ✅ 移除行尾空格
- ✅ 确保文件以换行符结尾
- ✅ 验证 YAML/JSON/TOML 文件格式
- ✅ 检查大文件（>1MB）
- ✅ 检查合并冲突标记
- ✅ 检查 Python debug 语句
- ✅ 检测密钥和敏感信息
- ✅ Black 代码格式化
- ✅ isort 导入排序
- ✅ flake8 代码检查
- ✅ mypy 类型检查

**性能：** 通常 < 10 秒

### 2. Commit-msg Hook（提交消息）

在每次 `git commit` 时验证提交消息格式。

**规范：** 使用 [Conventional Commits](https://www.conventionalcommits.org/)

**格式：**
```
type(scope): description

[optional body]

[optional footer]
```

**允许的类型：**
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式调整（不影响功能）
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建/工具相关
- `perf`: 性能优化
- `ci`: CI/CD 配置
- `build`: 构建系统
- `revert`: 回滚提交

**示例：**
```bash
# 好的提交消息 ✓
git commit -m "feat(api): add user authentication endpoint"
git commit -m "fix(db): resolve connection pool leak"
git commit -m "docs: update installation guide"

# 不好的提交消息 ✗
git commit -m "update code"
git commit -m "fix bug"
git commit -m "WIP"
```

### 3. Pre-push Hook（推送前）

在每次 `git push` 时运行测试。

**检查项目：**
- ✅ 运行所有单元测试
- ✅ 运行集成测试
- ✅ 检查测试覆盖率

**性能：** 取决于测试数量，通常 10-60 秒

## 使用指南

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

### 跳过 Hooks

在紧急情况下可以跳过 hooks（不推荐）：

```bash
# 跳过 pre-commit 和 commit-msg
git commit --no-verify -m "emergency fix"

# 跳过 pre-push
git push --no-verify
```

### 手动运行 Hooks

```bash
# 运行所有 hooks
pre-commit run --all-files

# 运行特定 hook
pre-commit run black --all-files
pre-commit run flake8 --all-files

# 只检查暂存的文件
pre-commit run
```

### 更新 Hooks

```bash
# 更新到最新版本
pre-commit autoupdate

# 清理缓存
pre-commit clean

# 重新安装
pre-commit uninstall
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push
```

## 配置文件

### .pre-commit-config.yaml

主配置文件，定义所有 hooks 和规则。

**位置：** 仓库根目录 `.pre-commit-config.yaml`

**修改后：**
```bash
# 重新安装 hooks
pre-commit install --hook-type pre-commit --overwrite
```

### .secrets.baseline

密钥检测基线文件，记录已知的"假阳性"。

**位置：** 仓库根目录 `.secrets.baseline`（与 pre-commit 配置中的 `--baseline` 一致）

**更新基线：**
```bash
detect-secrets scan --baseline .secrets.baseline
```

### pyproject.toml

工具配置（Black, isort, pytest, mypy, coverage）。

**位置：** `backend/pyproject.toml`

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

如果 Black 和 isort 产生冲突：

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

如果检测到假阳性：

```bash
# 更新基线
detect-secrets scan --baseline .secrets.baseline

# 或在代码中添加注释
password = "fake-password"  # pragma: allowlist secret
```

### mypy 类型错误

```bash
# 忽略特定行
result = some_function()  # type: ignore

# 忽略整个文件
# mypy: ignore-errors

# 或在 pyproject.toml 中配置
```

### 测试失败

Pre-push hook 会在测试失败时阻止推送：

```bash
# 修复测试
pytest tests/

# 或跳过（不推荐）
git push --no-verify
```

## CI/CD 集成

Hooks 在 CI 环境中自动跳过，避免重复运行。

**GitHub Actions 示例：**
```yaml
- name: Run pre-commit
  run: |
    pip install pre-commit
    pre-commit run --all-files
```

**环境变量：**
- `CI=true` - 自动检测 CI 环境
- `SKIP=pytest-check` - 跳过特定 hook

## 性能优化

### 缓存

Pre-commit 自动缓存工具和依赖：

**缓存位置：**
- Linux/Mac: `~/.cache/pre-commit`
- Windows: `%LOCALAPPDATA%\pre-commit`

### 并行运行

某些 hooks 可以并行运行以提高速度：

```yaml
# .pre-commit-config.yaml
repos:
  - repo: ...
    hooks:
      - id: black
        stages: [commit]
        # 并行运行
```

### 只检查更改的文件

默认情况下，hooks 只检查暂存的文件，不会检查整个代码库。

## 最佳实践

1. **频繁提交** - 小的、频繁的提交比大的、罕见的提交更好
2. **有意义的消息** - 使用清晰、描述性的提交消息
3. **修复后提交** - 不要跳过 hooks，修复问题后再提交
4. **保持更新** - 定期运行 `pre-commit autoupdate`
5. **团队一致** - 确保所有团队成员都安装了 hooks

## 参考资源

- [pre-commit 官方文档](https://pre-commit.com/)
- [Conventional Commits 规范](https://www.conventionalcommits.org/)
- [Black 代码风格](https://black.readthedocs.io/)
- [PEP 8 风格指南](https://pep8.org/)
- [detect-secrets 文档](https://github.com/Yelp/detect-secrets)

## 获取帮助

如果遇到问题：

1. 查看本文档的"故障排除"部分
2. 运行 `pre-commit run --all-files --verbose` 查看详细错误
3. 在项目 Issues 中搜索或提问
4. 联系项目维护者

---

**最后更新：** 2026-04-02
