# 智能穿搭助手 (Smart Outfit Assistant)

**最后更新**: 2026-04-01
**状态**: ✅ 可用于演示与迭代（后端 FastAPI + Flutter Web/移动端）

## 项目简介

智能穿搭助手是一个多端协同的智能穿搭决策系统，通过图像理解（CLIP）与多维度推荐算法，为用户提供：

- 🔍 **相似度分析与重复预警**：找出相似单品，避免重复购买
- 👔 **智能搭配推荐**：基于衣橱与画像生成场景穿搭方案
- ⭐ **适合度评分**：颜色 / 风格 / 体型友好度建议
- 🧠 **情绪穿搭**：根据心情给出更“治愈/更冷静/更有能量”的配色与风格方向，并匹配衣橱单品
- 🧥 **虚拟试衣（伪 3D 多视角）**：正面 / 侧面 / 背面三视角生成与轮播预览（支持多视角人物照）

## 核心功能

### 1. 重复购买预警
- 优先使用 CLIP 提取服饰特征向量（transformers + torch），弱网/离线可回退轻量方案
- 基于余弦相似度计算与衣橱中服饰的相似度
- 高/中/低三级相似度分级，自动标记重复购买风险

### 2. 搭配推荐
- 基于品类搭配规则生成搭配方案（颜色和谐 + 风格一致）
- 支持场景指定（正式/休闲/约会/运动）
- 考虑用户性别表达指数，智能推荐中性风或跨性别穿搭

### 3. 适合度评分
- 颜色适合度：基于肤色与服饰颜色的匹配度
- 版型适合度：基于体型和不希望强化的身体部位
- 风格适合度：基于用户风格偏好
- 综合评分并提供个性化改进建议

### 4. 情绪穿搭（Mood → Outfit）
- 快捷心情选择（例如「心情不好 · 想暖一点」）
- 后端输出：风格建议、适用场景、配色倾向（权重）、衣橱单品匹配列表

### 5. 虚拟试衣（Try-on）
- 前端自动 3 次请求生成 `front/side/back view`
- 支持人物 3 视角上传：正面必填，侧面/背面可选（未上传则复用正面照）
- 轮播与全屏预览：等比例完整显示（`contain`），支持缩放/拖拽

## 技术架构

### 后端服务
- **框架**: FastAPI（推荐 Python 3.12+）
- **数据库**: PostgreSQL + Redis
- **AI**:
  - CLIP（`transformers` + `torch`）用于类别/风格/场景与相似检索特征
  - 虚拟试衣：diffusers inpainting pipeline（可选，需下载模型；未就绪时 fallback）

### 移动端 (Flutter)
- **框架**: Flutter 3.x + Dart（iOS / Android / Web）
- **状态管理**: Provider
- **HTTP 客户端**: `package:http`（自定义 `ApiClient`）

### 设计系统
- **Material Design 3** 全局统一主题
- **性别表达指数** 动态配色（0.0 柔粉 ↔ 1.0 深蓝）
- **大圆角** 统一样式（BorderRadius 统一为 22px）

### CLI 工具
- **框架**: Python Click
- **终端美化**: Rich

### MCP 服务
- **协议**: Model Context Protocol
- **集成**: 支持 ChatGPT、Claude 等 AI 智能体调用

## 项目结构

```
clothing-assistant/
├── .kiro/specs/smart-outfit-assistant/
│   ├── requirements.md             # 需求文档
│   ├── design.md                  # 技术设计文档
│   ├── tasks.md                   # 实现计划
│   └── .config.kiro               # 配置文件
├── backend/                        # ✅ FastAPI 后端服务（已完成）
│   ├── app/                       # 应用代码
│   │   ├── api/                   # API 路由（22个端点）
│   │   ├── core/                  # 核心配置（含性别表达系统）
│   │   ├── db/                    # 数据库
│   │   ├── ml/                    # 机器学习模型
│   │   ├── models/                # ORM 模型
│   │   ├── schemas/               # Pydantic schemas
│   │   └── services/              # 业务逻辑
│   ├── tests/                     # ✅ 324 个测试（全部通过）
│   └── uploads/                   # 上传的图片
├── mobile/                         # ✅ Flutter 前端（已完成）
│   └── lib/
│       ├── core/                  # 核心服务、主题、性别表达系统
│       └── features/              # 功能模块
│           ├── auth/              # 认证
│           ├── home/              # 主页导航
│           ├── profile/           # 用户画像
│           ├── wardrobe/          # 衣橱管理（左右分栏 + 批量上传）
│           └── analysis/          # 分析功能（结果同屏展示）
├── cli/                           # ⏳ CLI 工具（待实现）
├── mcp/                           # ⏳ MCP 服务（待实现）
└── docs/                          # 📚 项目文档
```

## 开发状态

✅ **核心功能已完成** - 项目可用于演示和测试

本项目采用规格驱动开发（Spec-Driven Development）方法，完整的开发文档请查看：

- 📋 [需求文档](.kiro/specs/smart-outfit-assistant/requirements.md) - 16 个核心需求
- 🎨 [技术设计文档](.kiro/specs/smart-outfit-assistant/design.md) - 详细的架构和算法设计
- ✅ [实现计划](.kiro/specs/smart-outfit-assistant/tasks.md) - 37 个实现任务
- 📊 [项目状态](PROJECT_STATUS.md) - 当前完成度和功能清单

## 快速开始

详细的启动指南请查看 [QUICK_START.md](QUICK_START.md)

### 环境要求

- Python 3.11+ (推荐 3.12)
- PostgreSQL 14+ (开发环境可使用 SQLite)
- Redis 7+ (可选，用于缓存)
- Flutter 3.x (前端开发)

### 快速启动

```bash
# 1. 启动后端服务
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. 启动前端应用（新终端）
cd mobile
flutter run -d chrome

# 3. 访问应用
# 前端: 浏览器自动打开
# API 文档: http://localhost:8000/docs
```

### 模型下载/离线提示（重要）

- CLIP / Try-on 首次运行可能需要从 Hugging Face 下载权重（弱网易超时）。
- 国内网络建议设置镜像：`HF_ENDPOINT=https://hf-mirror.com`
- 可用脚本一次性预下载（用于离线/加速）：

```bash
cd backend
python scripts/prefetch_models.py --clip vit_l14
python scripts/prefetch_models.py --tryon
```

### Git Hooks 设置

本项目使用 **pre-commit 框架**管理 Git hooks，确保跨语言的代码质量和安全检查。

#### 🎯 已实现的 Hooks

| 阶段 | 功能 | 语言 | 说明 |
|------|------|------|------|
| **Pre-commit** | 代码格式化 | Python | Black + isort |
| | 代码格式化 | Dart/Flutter | `dart format` |
| | Linting | Python | flake8 (100字符上限) |
| | Linting | Dart/Flutter | `dart analyze` |
| | 基础检查 | 全局 | trailing whitespace, EOF, merge conflicts, etc. |
| | 大文件检查 | 全局 | 禁止提交 >1MB 文件 |
| | 密钥检测 | 全局 | detect-secrets 防止凭证泄露 |
| **Commit-msg** | 提交规范 | 全局 | Conventional Commits 强制执行 |
| **Pre-push** | 测试 | Python | pytest 完整测试 |
| | 测试 | Flutter | flutter test 单元测试 |

#### ⚡ 快速安装

从项目根目录运行安装脚本：

```powershell
# Windows PowerShell（推荐）:
.\setup-hooks.ps1

# Windows CMD:
setup-hooks.bat

# Linux/Mac:
chmod +x setup-hooks.sh
./setup-hooks.sh
```

或手动安装：

```bash
# 1. 安装依赖
pip install pre-commit==4.0.1 detect-secrets==1.5.0

# 2. 安装 hooks
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

# 3. 验证安装
ls .git/hooks
# 应该看到：pre-commit, commit-msg, pre-push （无 .sample 后缀）
```

#### 📝 提交消息规范

遵循 **Conventional Commits** 格式：

```bash
# 基础格式：type(scope): description
type(scope): description

# 示例：
git commit -m "feat: add wardrobe management feature"
git commit -m "fix(api): resolve authentication timeout bug"
git commit -m "docs: update installation guide"
git commit -m "refactor(ui): simplify color theme system"
```

**允许的提交类型：**
- `feat` - 新功能
- `fix` - bug 修复
- `docs` - 文档更新
- `style` - 代码格式、无逻辑修改
- `refactor` - 代码重构
- `test` - 测试相关
- `chore` - 构建、依赖、工具更新
- `perf` - 性能优化
- `ci` - CI/CD 配置
- `build` - 构建系统
- `revert` - 回滚提交

**Scope（作用域）是可选的：** `(api)`, `(ui)`, `(mobile)`, `(backend)` 等

#### 🔧 常见操作

```bash
# 运行所有 hooks（不提交）
pre-commit run --all-files

# 跳过 hooks 提交（仅在特殊情况下使用）
git commit --no-verify -m "type: message"

# 手动格式化和检查 Dart 代码
cd mobile
dart format lib test
dart analyze lib

# 手动运行 Python 测试
cd backend
python -m pytest -v --tb=short

# 手动运行 Flutter 测试
cd mobile
flutter test
```

#### 📚 详细文档

- [GIT_HOOKS 完整指南](backend/GIT_HOOKS.md)
- [Conventional Commits 规范](backend/COMMIT_CONVENTION.md)
- [Git Hooks 设置说明](SETUP_HOOKS_README.md)

## 功能完成度

✅ **后端服务**: 100% 完成
- 22 个 API 端点全部实现
- 324 个测试全部通过（无失败）
- 性别表达指数系统、图像识别、相似度分析、搭配推荐、适合度评分全部可用

✅ **前端应用**: 100% 完成
- 用户认证、用户画像、衣橱管理全部实现
- **衣橱页** 左右分栏（固定分类边栏 + 虚拟滚动网格，每行4张1:1正方形）
- **批量上传** 支持一次选择多张图片，逐张上传并显示进度
- **分析页** 四种分析结果同屏展示
- 性别表达指数滑块（全局大圆角样式）
- Flutter Web 完全兼容

⏳ **CLI 工具**: 待实现
⏳ **MCP 服务**: 待实现

## 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 测试策略

本项目采用双重测试方法：

- **单元测试**: 使用 pytest 验证具体功能
- **属性测试**: 使用 Hypothesis 验证通用属性
- **集成测试**: 验证多组件协同工作
- **性能测试**: 确保响应时间满足要求

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 联系方式

- 项目主页: https://github.com/your-username/smart-outfit-assistant
- 问题反馈: https://github.com/your-username/smart-outfit-assistant/issues

## 致谢

- CLIP / Diffusers 等模型组件来自开源社区
- 感谢所有开源项目的贡献者

---

**注意**: 本项目为毕业设计/课题研究项目，仅供学习和研究使用。
年级：2024级
学号：202452320220
班级：智能科学与技术2班
