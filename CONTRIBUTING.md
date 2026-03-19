# 贡献指南

感谢你对智能穿搭助手项目的关注！我们欢迎任何形式的贡献。

## 如何贡献

### 报告问题

如果你发现了 bug 或有功能建议，请：

1. 在 [Issues](https://github.com/your-username/smart-outfit-assistant/issues) 页面搜索是否已有相关问题
2. 如果没有，创建新的 Issue，并提供：
   - 清晰的标题
   - 详细的描述
   - 复现步骤（如果是 bug）
   - 预期行为和实际行为
   - 环境信息（操作系统、Python 版本等）

### 提交代码

1. **Fork 仓库**
   ```bash
   # 在 GitHub 上点击 Fork 按钮
   ```

2. **克隆你的 Fork**
   ```bash
   git clone https://github.com/your-username/smart-outfit-assistant.git
   cd smart-outfit-assistant
   ```

3. **创建特性分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **进行开发**
   - 遵循项目的代码风格
   - 添加必要的测试
   - 更新相关文档

5. **运行测试**
   ```bash
   pytest tests/
   ```

6. **提交更改**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

7. **推送到你的 Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

8. **创建 Pull Request**
   - 在 GitHub 上打开你的 Fork
   - 点击 "New Pull Request"
   - 填写 PR 描述，说明你的更改

## 代码规范

### Python 代码风格

- 遵循 PEP 8 规范
- 使用 Black 格式化代码
- 使用 isort 排序导入
- 使用 pylint 进行代码检查

```bash
# 格式化代码
black .
isort .

# 检查代码
pylint app/
```

### 提交信息规范

使用语义化提交信息：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具相关

示例：
```
feat: add similarity analysis API endpoint
fix: resolve image upload validation issue
docs: update README with installation steps
```

## 测试要求

所有新功能和 bug 修复都应包含测试：

- **单元测试**: 测试单个函数/类
- **集成测试**: 测试多个组件协同工作
- **属性测试**: 使用 Hypothesis 验证通用属性

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/unit/test_similarity.py

# 查看覆盖率
pytest --cov=app --cov-report=html
```

## 文档要求

- 为新功能添加文档字符串
- 更新 README.md（如果需要）
- 更新 API 文档（如果添加了新接口）

## 开发环境设置

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装开发依赖
pip install -r requirements-dev.txt

# 安装 pre-commit hooks
pre-commit install
```

## 问题和讨论

如有任何问题，欢迎：

- 在 Issues 中提问
- 在 Discussions 中讨论
- 发送邮件至项目维护者

## 行为准则

请遵守我们的行为准则，保持友好和尊重的交流环境。

感谢你的贡献！🎉
