# 智能穿搭助手 - 快速启动指南

更完整的「本地跑通 + 高德/千问/豆包仅配置接入」清单见 **[docs/LOCAL_FULL_RUN_AND_MINIMAL_API.md](docs/LOCAL_FULL_RUN_AND_MINIMAL_API.md)**。

## 🚀 5 分钟快速开始

### 步骤 1: 启动后端服务

首次克隆请配置环境文件：`cd backend` 后执行 `copy .env.example .env`（macOS/Linux: `cp .env.example .env`），再启动。

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

**验证**: 访问 http://127.0.0.1:8010/health 应该看到 `{"status":"healthy"}`

### 步骤 2: 启动 Flutter Web

```bash
cd mobile
flutter run -d chrome
```

**验证**: 浏览器自动打开，显示登录页面。若直接访问 `http://localhost:<端口>/` 出现白屏，请 **热重载或更新到已包含 `/` → `/auth` 重定向的版本**（见 [docs/AI_OUTFIT_PREDICT_AND_TRYON.md](docs/AI_OUTFIT_PREDICT_AND_TRYON.md)）。

### 步骤 3: 注册账号

1. 点击"立即注册"
2. 填写信息：
   - 用户名: `demo_user`
   - 邮箱: `demo@example.com`
   - 密码: `Demo123!@#`
3. 点击"注册"
4. 注册成功后返回登录页（默认切回登录 Tab）
5. 使用刚注册的账号在登录页登录并进入主页

### 步骤 4: 创建用户画像

1. 点击"用户画像"卡片
2. 填写个人信息：
   - 身高: `175` cm
   - 体型: `梨形` / `倒三角` / `微胖` 等
   - 肤色: `冷白` / `黄皮` / `小麦` / `深色`
   - 风格偏好（多选）: `休闲`、`简约`、`通勤` 等
   - 预算范围: `经济` / `中等` / `高端`
   - 希望修饰部位（可选）: `肩` / `腰` / `臀` / `大腿` 等
3. 点击右上角保存按钮（或保存图标）

### 步骤 5: 添加服饰到衣橱

1. 点击"我的衣橱"卡片
2. 点击右下角"+"按钮
3. 选择服饰图片（准备一些服饰照片）
4. 等待识别完成
5. 重复添加多件服饰

### 步骤 6: 体验智能功能

#### 相似度分析
1. 点击"相似度分析"
2. 上传服饰图片
3. 查看相似服饰列表

#### 智能穿搭（天气 + 可选心情，一次 3 套）
1. 主页进入 **穿搭** → 列表第一项 **「智能穿搭」**（不是「场景穿搭推荐」）
2. 上传 1 张参考衣物图；可选填写情绪；底部 **生成穿搭**
3. 左右滑动查看 3 套结果；**重新生成** 会换一批，条件不变

对接后端路径：`GET/POST http://<后端>/api/v1/smart-outfit/...`（需登录），详见 `backend/API_EXAMPLES.md`。

#### 场景穿搭推荐（多图 + 选场景）
1. 穿搭中心第二项 **「场景穿搭推荐」**
2. 选择场景并上传图片（可多张）
3. 查看推荐的搭配方案

#### 情绪穿搭（心情 → 穿搭方向）
1. 点击"情绪穿搭"
2. 选择当前心情（例如「心情不好 · 想暖一点」）
3. 查看风格/颜色建议与衣橱匹配单品

#### 虚拟试衣（伪 3D 三视角）
1. 点击「虚拟试衣」（需登录）
2. **衣服图请用无模特的白底/平铺商品图**（含模特图会被后端拒绝）；人物正面照必填，侧面/背面可选
3. 点击生成，左右滑动查看正/侧/背三视角（可点进全屏缩放）
   - 未加载扩散模型时，后端使用 **去背景 + 粘贴合成**，不再使用半透明整图叠图

#### AI 穿搭风格分（可选：Vite 演示页）
1. 启动独立 predict API（默认 **8765**）：仓库根目录执行 `.\scripts\run_predict_api.ps1`，或见 [docs/AI_OUTFIT_PREDICT_AND_TRYON.md](docs/AI_OUTFIT_PREDICT_AND_TRYON.md)
2. 另开终端：`cd frontend && npm install && npm run dev`
3. 浏览器打开 Vite 提示的地址，填写表单调用 **`POST /predict`**

#### Flutter 与主后端同端口（仅 predict）
若只运行 `app.main`（例如 `--port 8010`），希望预测接口也走同一进程：

```bash
flutter run -d chrome --dart-define=PREDICT_API_PORT=8010
```

#### 适合度评分
1. 点击"适合度分析"
2. 上传服饰图片
3. 查看三维评分（场景匹配 / 体型适配 / 风格协调）与每个维度的**原因说明**

## 📱 完整功能列表

### ✅ 已实现功能

1. **用户认证**
   - 注册
   - 登录
   - 登出
   - JWT Token 管理

2. **用户画像**
   - 创建画像
   - 编辑画像
   - 基本信息（身高、体重、性别、体型、肤色）
   - 风格偏好（多选）
   - 颜色偏好（多选）

3. **衣橱管理**
   - 添加服饰（图片上传）
   - 查看服饰列表
   - 按品类筛选
   - 删除服饰
   - 自动识别（品类、颜色、风格）

4. **相似度分析**
   - 上传服饰图片
   - 识别服饰信息
   - 查找相似服饰
   - 相似度评分
   - 重复购买预警

5. **搭配推荐**
   - 上传基础服饰
   - 生成搭配方案
   - 多方案推荐（1-5个）
   - 方案评分
   - 推荐理由

6. **适合度评分**
   - 上传服饰图片
   - 总体适合度评分
   - 详细评分（风格、颜色、体型、肤色）
   - 个性化建议

## 🛠️ 技术栈

### 后端
- FastAPI (Python)
- SQLite 数据库
- JWT 认证
- CLIP（transformers + torch）图像理解（弱网/离线可回退轻量方案）
- Redis 缓存（可选）

### 前端
- Flutter Web
- Provider 状态管理
- GoRouter 路由
- `package:http` 网络请求（自定义 `ApiClient`）
- Material Design 3

## 📂 项目结构

```
.
├── backend/                 # 后端服务
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── core/           # 核心配置
│   │   ├── db/             # 数据库
│   │   ├── ml/             # 机器学习模型
│   │   ├── models/         # 数据模型
│   │   ├── schemas/        # API 模式
│   │   └── services/       # 业务逻辑
│   ├── tests/              # 测试
│   └── main.py             # 入口文件
│
├── mobile/                  # Flutter 前端
│   ├── lib/
│   │   ├── core/           # 核心功能
│   │   │   ├── providers/  # 状态管理
│   │   │   └── services/   # API 服务
│   │   ├── features/       # 功能模块
│   │   │   ├── auth/       # 认证
│   │   │   ├── home/       # 主页
│   │   │   ├── profile/    # 用户画像
│   │   │   ├── wardrobe/   # 衣橱管理
│   │   │   └── analysis/   # 分析功能
│   │   └── main.dart       # 入口文件
│   └── pubspec.yaml        # 依赖配置
│
└── docs/                    # 文档
```

## 🔧 配置说明

### 后端配置 (backend/.env)

```env
# 应用配置
APP_NAME="Smart Outfit Assistant"
DEBUG=True

# 数据库
DATABASE_URL=sqlite:///./outfit_assistant.db

# JWT
JWT_SECRET_KEY=dev-secret-key-change-in-production-12345
JWT_EXPIRATION_HOURS=24

# CORS
CORS_ALLOW_ALL_LOCALHOST=True

# 文件上传
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=10485760
```

### 前端配置 (mobile/lib/core/services/api_client.dart)

```dart
static const String baseUrl = 'http://127.0.0.1:8010/api/v1';
```

## 🧪 测试

### 后端测试

```bash
cd backend
pytest tests/ -v
```

**测试覆盖**:
- 289 个测试用例
- 所有 API 端点
- 认证和授权
- 图像识别
- 业务逻辑

### 前端测试

```bash
cd mobile
flutter test
```

## 📊 API 文档

### Swagger UI
访问: http://127.0.0.1:8010/docs

### ReDoc
访问: http://127.0.0.1:8010/redoc

### 主要 API 端点

#### 认证
- `POST /api/v1/auth/register` - 注册
- `POST /api/v1/auth/login` - 登录

#### 用户画像
- `POST /api/v1/profile` - 创建画像
- `GET /api/v1/profile` - 获取画像
- `PUT /api/v1/profile` - 更新画像

#### 衣橱管理
- `POST /api/v1/wardrobe/garments` - 添加服饰
- `GET /api/v1/wardrobe/garments` - 获取服饰列表
- `DELETE /api/v1/wardrobe/garments/{id}` - 删除服饰
- `POST /api/v1/wardrobe/split-outfit` - 整套穿搭图拆分（可选入库；连衣裙/包等见 [docs/WARDROBE_FEATURES.md](docs/WARDROBE_FEATURES.md)）

#### 分析功能
- `POST /api/v1/analysis/similarity` - 相似度分析
- `POST /api/v1/analysis/outfits` - 搭配推荐（单图字段 `file`；多图字段 `files` 可重复，最多 5 张，合并识别后一次推荐；详见 [docs/OUTFIT_MULTI_IMAGE_UPLOAD.md](docs/OUTFIT_MULTI_IMAGE_UPLOAD.md)）
- `POST /api/v1/analysis/suitability` - 适合度评分

## 🐛 故障排查

### 问题 1: 后端无法启动

**检查**:
```bash
# 检查 Python 版本
python --version  # 应该是 3.9+

# 检查依赖
pip list | grep fastapi

# 检查端口占用
netstat -ano | findstr :8010
```

### 问题 2: Flutter Web 无法启动

**检查**:
```bash
# 检查 Flutter 版本
flutter --version

# 检查依赖
flutter pub get

# 清理缓存
flutter clean
flutter pub get
```

### 问题 3: CORS 错误

**解决方案**:
1. 确保后端 `.env` 中 `CORS_ALLOW_ALL_LOCALHOST=True`
2. 重启后端服务
3. 清除浏览器缓存（Ctrl+Shift+R）

### 问题 4: 登录后无法跳转

**解决方案**:
1. 在 Flutter 终端按 `R` 键热重启
2. 检查浏览器控制台是否有错误
3. 确保密码包含特殊字符（如 `Test123!@#`）

## 📝 开发提示

### 热重载

Flutter 支持热重载，修改代码后：
- 按 `r` 键：热重载（保留状态）
- 按 `R` 键：热重启（重置状态）

### 调试

#### 后端调试
```bash
# 查看日志
tail -f backend/logs/app.log

# 使用 Python 调试器
python -m pdb backend/app/main.py
```

#### 前端调试
- 打开浏览器开发者工具（F12）
- 查看 Console 标签的日志
- 查看 Network 标签的网络请求

### 代码格式化

#### 后端
```bash
cd backend
black app/
flake8 app/
```

#### 前端
```bash
cd mobile
flutter format lib/
flutter analyze
```

## 🎯 下一步

### 功能增强
- [ ] 添加服饰详情页
- [ ] 支持编辑服饰信息
- [ ] 添加搜索功能
- [ ] 支持分享搭配方案
- [ ] 添加收藏功能

### UI/UX 优化
- [ ] 添加骨架屏
- [ ] 优化图片加载
- [ ] 添加动画效果
- [ ] 支持深色模式

### 性能优化
- [ ] 实现图片缓存
- [ ] 添加分页加载
- [ ] 优化网络请求

## 📚 相关文档

- `MOBILE_FEATURES_COMPLETE.md` - 功能实现详细说明
- `FLUTTER_ROUTING_FIX.md` - 路由问题修复说明
- `CORS_FIX_SUMMARY.md` - CORS 配置说明
- `backend/API_DOCUMENTATION_COMPLETE.md` - API 完整文档

## 💡 提示

1. **首次使用**: 建议先创建用户画像，这样分析功能会更准确
2. **添加服饰**: 多添加一些服饰到衣橱，搭配推荐效果会更好
3. **图片质量**: 使用清晰的服饰图片，识别准确度会更高
4. **测试数据**: 可以使用测试图片进行功能演示

## 🎉 开始使用

现在您已经了解了所有功能，可以开始使用智能穿搭助手了！

祝您使用愉快！ 👔👗👠
