# Commit Message Convention

本项目使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

## 格式

```
type(scope): subject

[optional body]

[optional footer]
```

## Type（类型）

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(api): add user authentication` |
| `fix` | Bug 修复 | `fix(db): resolve connection leak` |
| `docs` | 文档更新 | `docs: update installation guide` |
| `style` | 代码格式（不影响功能） | `style: format with black` |
| `refactor` | 代码重构 | `refactor(api): simplify error handling` |
| `test` | 测试相关 | `test: add unit tests for similarity` |
| `chore` | 构建/工具相关 | `chore: update dependencies` |
| `perf` | 性能优化 | `perf(ml): optimize feature extraction` |
| `ci` | CI/CD 配置 | `ci: add GitHub Actions workflow` |
| `build` | 构建系统 | `build: configure Docker` |
| `revert` | 回滚提交 | `revert: revert commit abc123` |

## Scope（范围）

可选，表示影响的模块或组件：

- `api` - API 端点
- `db` - 数据库
- `auth` - 认证
- `ml` - 机器学习
- `ui` - 用户界面
- `cli` - 命令行工具
- `mcp` - MCP 服务
- `config` - 配置
- `deps` - 依赖

## Subject（主题）

- 使用祈使句，现在时："add" 而不是 "added" 或 "adds"
- 不要大写首字母
- 不要以句号结尾
- 限制在 50 个字符以内

## Body（正文）

可选，提供更详细的说明：

- 解释"为什么"而不是"是什么"
- 每行限制在 72 个字符以内
- 可以包含多个段落

## Footer（页脚）

可选，用于：

- 引用 Issue：`Closes #123`
- 破坏性变更：`BREAKING CHANGE: ...`

## 示例

### 简单提交

```bash
git commit -m "feat(api): add health check endpoint"
```

### 带范围的提交

```bash
git commit -m "fix(db): resolve connection pool leak"
```

### 带正文的提交

```bash
git commit -m "feat(ml): implement similarity analysis

- Add cosine similarity calculation
- Implement feature vector extraction
- Add caching for performance

Closes #42"
```

### 破坏性变更

```bash
git commit -m "feat(api): change authentication method

BREAKING CHANGE: JWT tokens now require 'Bearer' prefix"
```

## 常见错误

❌ **错误示例：**

```bash
# 太模糊
git commit -m "update code"

# 没有类型
git commit -m "add new feature"

# 大写首字母
git commit -m "feat: Add new feature"

# 以句号结尾
git commit -m "feat: add new feature."

# 使用过去时
git commit -m "feat: added new feature"
```

✅ **正确示例：**

```bash
git commit -m "feat(api): add user registration endpoint"
git commit -m "fix(auth): resolve token expiration issue"
git commit -m "docs: update API documentation"
git commit -m "refactor(db): simplify query logic"
```

## 工具支持

本项目使用 `conventional-pre-commit` hook 自动验证提交消息。

**跳过验证（不推荐）：**
```bash
git commit --no-verify -m "WIP"
```

## 参考资源

- [Conventional Commits 官方规范](https://www.conventionalcommits.org/)
- [Angular Commit Guidelines](https://github.com/angular/angular/blob/main/CONTRIBUTING.md#commit)
- [Semantic Versioning](https://semver.org/)

---

**提示：** 良好的提交消息有助于：
- 自动生成 CHANGELOG
- 确定语义化版本号
- 快速理解项目历史
- 简化代码审查
