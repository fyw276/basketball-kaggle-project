# GitHub 推送指南

本文档将指导你如何将智能穿搭助手项目推送到 GitHub。

## 前置准备

### 1. 安装 Git

如果你还没有安装 Git，请按照以下步骤安装：

**Windows:**
1. 访问 https://git-scm.com/download/win
2. 下载并安装 Git for Windows
3. 安装时选择默认选项即可

**验证安装:**
```bash
git --version
```

### 2. 配置 Git

首次使用 Git 需要配置用户信息：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱@example.com"
```

### 3. 创建 GitHub 账户

如果还没有 GitHub 账户：
1. 访问 https://github.com
2. 点击 "Sign up" 注册账户
3. 验证邮箱

## 推送步骤

### 步骤 1: 初始化本地 Git 仓库

在项目根目录（clothing-assistant）打开终端，执行：

```bash
# 初始化 Git 仓库
git init

# 查看当前状态
git status
```

### 步骤 2: 添加文件到暂存区

```bash
# 添加所有文件
git add .

# 或者逐个添加
git add README.md
git add .gitignore
git add LICENSE
git add .kiro/
```

### 步骤 3: 提交更改

```bash
git commit -m "Initial commit: Add project specification and documentation"
```

### 步骤 4: 在 GitHub 上创建仓库

1. 登录 GitHub
2. 点击右上角的 "+" 按钮
3. 选择 "New repository"
4. 填写仓库信息：
   - **Repository name**: `smart-outfit-assistant` 或 `clothing-assistant`
   - **Description**: 智能穿搭助手 - 基于多模态推荐与轻量化推理的穿搭决策系统
   - **Public/Private**: 选择公开或私有
   - **不要**勾选 "Initialize this repository with a README"（我们已经有了）
5. 点击 "Create repository"

### 步骤 5: 关联远程仓库

GitHub 会显示推送指令，复制并执行：

```bash
# 添加远程仓库（替换为你的 GitHub 用户名）
git remote add origin https://github.com/你的用户名/smart-outfit-assistant.git

# 验证远程仓库
git remote -v
```

### 步骤 6: 推送到 GitHub

```bash
# 推送到主分支
git branch -M main
git push -u origin main
```

如果遇到认证问题，GitHub 现在推荐使用 Personal Access Token (PAT)：

#### 创建 Personal Access Token

1. 访问 GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. 点击 "Generate new token (classic)"
3. 设置：
   - Note: "Smart Outfit Assistant"
   - Expiration: 选择过期时间
   - 勾选 `repo` 权限
4. 点击 "Generate token"
5. **复制并保存 token**（只显示一次）

#### 使用 Token 推送

```bash
# 第一次推送时会要求输入用户名和密码
# 用户名: 你的 GitHub 用户名
# 密码: 粘贴你的 Personal Access Token
git push -u origin main
```

## 后续更新

完成首次推送后，后续更新流程：

```bash
# 1. 查看更改
git status

# 2. 添加更改
git add .

# 3. 提交更改
git commit -m "描述你的更改"

# 4. 推送到 GitHub
git push
```

## 常用 Git 命令

```bash
# 查看状态
git status

# 查看提交历史
git log

# 查看远程仓库
git remote -v

# 拉取最新代码
git pull

# 创建新分支
git checkout -b feature/new-feature

# 切换分支
git checkout main

# 合并分支
git merge feature/new-feature

# 删除分支
git branch -d feature/new-feature
```

## 项目结构说明

推送后，你的 GitHub 仓库将包含：

```
smart-outfit-assistant/
├── .gitignore              # Git 忽略文件配置
├── .kiro/                  # Kiro 规格文件
│   └── specs/
│       └── smart-outfit-assistant/
│           ├── .config.kiro
│           ├── requirements.md
│           ├── design.md
│           └── tasks.md
├── CONTRIBUTING.md         # 贡献指南
├── GITHUB_SETUP.md        # 本文件
├── LICENSE                # MIT 许可证
└── README.md              # 项目说明
```

## 推荐的下一步

1. **添加 GitHub Actions**
   - 创建 `.github/workflows/` 目录
   - 添加 CI/CD 配置

2. **设置 GitHub Pages**（可选）
   - 用于托管项目文档

3. **启用 Issues 和 Discussions**
   - 在仓库设置中启用

4. **添加 Topics**
   - 在仓库主页点击设置图标
   - 添加相关标签：`python`, `fastapi`, `flutter`, `ai`, `fashion`, `recommendation-system`

5. **创建 Project Board**
   - 用于跟踪开发进度

## 故障排除

### 问题 1: 推送被拒绝

```bash
# 如果远程仓库有更新，先拉取
git pull origin main --rebase
git push
```

### 问题 2: 认证失败

- 确保使用 Personal Access Token 而不是密码
- 检查 token 权限是否包含 `repo`

### 问题 3: 文件太大

```bash
# 如果有大文件，使用 Git LFS
git lfs install
git lfs track "*.h5"
git lfs track "*.pth"
git add .gitattributes
git commit -m "Add Git LFS tracking"
```

## 需要帮助？

- GitHub 文档: https://docs.github.com
- Git 文档: https://git-scm.com/doc
- 项目 Issues: https://github.com/你的用户名/smart-outfit-assistant/issues

---

祝你推送顺利！🚀
