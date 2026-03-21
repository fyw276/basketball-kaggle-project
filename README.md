# 智能穿搭助手 (Smart Outfit Assistant)

基于多模态推荐与轻量化推理的智能穿搭助手系统，帮助用户解决重复购买、搭配不确定性和适合度判断三大核心痛点。

## 项目简介

智能穿搭助手是一个多端协同的智能穿搭决策系统，通过轻量级图像识别技术和多维度推荐算法，为用户提供：

- 🔍 **相似度分析与重复预警** - 避免重复购买相似服饰
- 👔 **智能搭配推荐** - 基于个人衣橱生成搭配方案
- ⭐ **适合度评分** - 评估服饰是否适合用户的肤色、身材和风格

## 核心功能

### 1. 重复购买预警
- 使用 MobileNetV2 提取服饰特征向量
- 基于余弦相似度计算与衣橱中服饰的相似度
- 自动标记高相似度服饰并提供购买建议

### 2. 搭配推荐
- 基于品类搭配规则生成搭配方案
- 应用颜色和谐理论（同色系/邻近色/互补色）
- 考虑风格一致性和用户偏好

### 3. 适合度评分
- 颜色适合度：基于肤色与服饰颜色的匹配度
- 版型适合度：基于体型和不希望强化的身体部位
- 风格适合度：基于用户风格偏好
- 综合评分并提供改进建议

## 技术架构

### 后端服务
- **框架**: FastAPI (Python 3.9+)
- **数据库**: PostgreSQL + Redis
- **AI 模型**: MobileNetV2 (轻量级 CNN)
- **图像处理**: TensorFlow Lite / PyTorch

### 移动端
- **框架**: Flutter 3.x
- **平台**: iOS + Android
- **状态管理**: Riverpod
- **HTTP 客户端**: Dio

### CLI 工具
- **框架**: Python Click
- **终端美化**: Rich

### MCP 服务
- **协议**: Model Context Protocol
- **集成**: 支持 ChatGPT、Claude 等 AI 智能体调用

## 项目结构

```
clothing-assistant/
├── .kiro/
│   └── specs/
│       └── smart-outfit-assistant/
│           ├── requirements.md      # 需求文档
│           ├── design.md           # 技术设计文档
│           ├── tasks.md            # 实现计划
│           └── .config.kiro        # 配置文件
├── backend/                        # FastAPI 后端服务（待实现）
├── mobile/                         # Flutter 移动端（待实现）
├── cli/                           # CLI 工具（待实现）
├── mcp/                           # MCP 服务（待实现）
├── models/                        # AI 模型文件（待实现）
└── README.md
```

## 开发计划

本项目采用规格驱动开发（Spec-Driven Development）方法，完整的开发计划请查看：

- 📋 [需求文档](.kiro/specs/smart-outfit-assistant/requirements.md) - 16 个核心需求
- 🎨 [技术设计文档](.kiro/specs/smart-outfit-assistant/design.md) - 详细的架构和算法设计
- ✅ [实现计划](.kiro/specs/smart-outfit-assistant/tasks.md) - 37 个实现任务

## 快速开始

### 环境要求

- Python 3.11+ (推荐 3.14)
- PostgreSQL 14+
- Redis 7+
- Flutter 3.x (移动端开发)
- Git (版本控制)

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/your-username/smart-outfit-assistant.git
cd smart-outfit-assistant

# 后端服务
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 设置 Git hooks（重要！）
# Windows:
setup-hooks.bat

# Linux/Mac:
chmod +x setup-hooks.sh
./setup-hooks.sh

# 配置环境变量
cp .env.example .env

# 启动服务器
python run.py

# 移动端（待实现）
cd mobile
flutter pub get

# CLI 工具（待实现）
cd cli
pip install -e .
```

### Git Hooks 设置

本项目使用 pre-commit 框架管理 Git hooks，确保代码质量：

- **Pre-commit**: 自动格式化、linting、类型检查
- **Commit-msg**: 强制使用规范的提交消息（Conventional Commits）
- **Pre-push**: 运行测试

**快速安装：**
```bash
cd backend
setup-hooks.bat  # Windows
# 或
./setup-hooks.sh  # Linux/Mac
```

详细文档请查看 [Git Hooks 配置指南](backend/GIT_HOOKS.md)。

## 开发状态

🚧 **项目当前处于规格设计阶段**

- ✅ 需求分析完成
- ✅ 技术设计完成
- ✅ 实现计划完成
- ⏳ 代码实现进行中

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

- MobileNetV2 模型来自 TensorFlow
- 感谢所有开源项目的贡献者

---

**注意**: 本项目为毕业设计/课题研究项目，仅供学习和研究使用。
年级：2024级
学号：202452320220
班级：智能科学与技术2班