# 智能穿搭助手 - Flutter 移动端

更新时间：2026-05-29

这是智能穿搭助手的 Flutter 移动端应用。

## 功能特性

- ✅ 用户注册和登录
- ✅ JWT Token 认证
- ✅ 主页导航
- ✅ 用户画像管理（含性别表达指数）
- ✅ 衣橱管理（批量上传、筛选、编辑）
- ✅ 相似度分析（单品重复购买预警 + Look 拆分匹配）
- ✅ 搭配推荐（支持多图同次请求，合并识别）
- ✅ 智能穿搭（参考图 + 自动天气 + 可选心情；接口：`/api/v1/smart-outfit/*`）
- ✅ 首页天气与今日推荐卡（城市/天气/温度 + AI 评分/风格/理由）
- ✅ 一键生成穿搭（选图 → 补天气 → 生成）
- ✅ 结果回跳定位（首页“查看详情”自动跳转到上次浏览搭配）
- ✅ 适合度分析（场景/体型/风格三维评分 + 每维原因说明）
- ✅ 情绪穿搭（心情 → 配色/风格方向 + 衣橱匹配）
- ✅ 虚拟试衣（v1 + v2 方案 A 双链路，支持“先预检再生成”、Look 候选预填、结果保存到相册/Web 打开）
- ✅ AI Agent 对话（SSE 流式执行步骤 + 工具调用结果 + 最终回答）
- ✅ 分析页衣橱选择器（从已有衣橱单品直接填充分析图片）
- ✅ 体型感知（读取画像，一键生成 3 套体型专属穿搭）

## 技术栈

- **Flutter**: 3.0+
- **状态管理**: Provider
- **网络请求**: `package:http`（自定义 `ApiClient`）
- **路由**: GoRouter
- **本地存储**: SharedPreferences
- **图片选择**: ImagePicker
- **图片保存/打开**: Gal、UrlLauncher、PathProvider

## 项目结构

```
mobile/
├── lib/
│   ├── main.dart                    # 应用入口
│   ├── core/                        # 核心功能
│   │   ├── providers/              # 状态管理
│   │   │   └── auth_provider.dart
│   │   └── services/               # 服务层
│   │       └── api_client.dart
│   └── features/                    # 功能模块
│       ├── auth/                   # 认证
│       │   └── screens/
│       │       └── auth_screen.dart  # 登录/注册（TabBar 切换）
│       ├── home/                   # 主页
│       │   └── screens/
│       │       └── home_screen.dart
│       ├── profile/                # 用户画像
│       ├── wardrobe/               # 衣橱管理
│       ├── agent/                  # Agent 流式对话与执行步骤
│       └── analysis/               # 分析功能
│           └── screens/
│               ├── similarity_analysis_screen.dart
│               ├── outfit_recommend_screen.dart
│               ├── suitability_analysis_screen.dart
│               └── body_shape_insight_screen.dart
└── pubspec.yaml                     # 依赖配置
```

## 快速开始

### 前置要求

- Flutter SDK 3.0 或更高版本
- Dart SDK 3.0 或更高版本
- Android Studio 或 VS Code
- Android 模拟器或 iOS 模拟器

### 安装步骤

1. **安装依赖**

```bash
cd mobile
flutter pub get
```

2. **配置后端 API 地址（可选）**

后端地址由 `ApiBaseResolver` 根据平台自动解析（Web/Android/iOS/桌面），一般无需手改。
如需自定义，请查看：

- `lib/core/services/api_base_resolver.dart`
- `lib/core/services/api_base_resolver_web.dart`
- `lib/core/services/api_base_resolver_io.dart`

常见说明：

- **Flutter Web（本机调试）**：`api_base_resolver_web.dart` 将 API 固定为 **`http://127.0.0.1:<端口>/api/v1`**（默认端口 **8010**，与 `backend/.env` 的 `PORT` 一致），详见 [`docs/SMART_OUTFIT_FLUTTER_WEB.md`](../docs/SMART_OUTFIT_FLUTTER_WEB.md)。
- Android 模拟器：`http://10.0.2.2:8010/api/v1`（端口随 `api_port_config.dart` / `--dart-define=API_PORT`）
- iOS 模拟器：`http://127.0.0.1:8010/api/v1`
- 真机：使用后端所在机器的局域网 IP（同网段）

说明：
- `ApiClient` 的 v2 试衣方法会自动把 `/api/v1` 基址切换到 `/api/v2`，无需单独维护第二套 baseUrl。

3. **运行应用**

```bash
# 运行在 Android 模拟器
flutter run

# 运行在 iOS 模拟器
flutter run -d ios

# 运行在真机
flutter run -d <device-id>
```

## 开发指南

### 添加新功能

1. 在 `lib/features/` 下创建新的功能模块
2. 创建对应的 screens、widgets、providers
3. 在 `main.dart` 中添加路由

### API 调用

所有 API 调用都通过 `ApiClient` 进行：

```dart
final apiClient = ApiClient();

// 登录
final response = await apiClient.login(
  username: 'testuser',
  password: 'password',
);

// 获取衣橱
final garments = await apiClient.getGarments();
```

### 状态管理

使用 Provider 进行状态管理：

```dart
// 读取状态
final authProvider = context.watch<AuthProvider>();

// 调用方法
final authProvider = context.read<AuthProvider>();
await authProvider.login(...);
```

## 测试

```bash
# 运行单元测试
flutter test

# 运行集成测试
flutter test integration_test
```

## 近期关键变更（2026-05-24）

- 新增 Agent 对话页与 `/agent` 路由，消费 `/api/v1/agent/chat-stream` SSE 事件。
- 新增 `SseParser`，正确处理跨 chunk 的 SSE 行边界，智能穿搭流与 Agent 流共用。
- 分析页支持从衣橱选择图片，减少重复上传；v2 试衣调用继续自动从 `/api/v1` 基址切换到 `/api/v2`。
- 虚拟试衣 v2 模式文档同步为 7 种：strict/balanced/replace/realistic/realistic_v2/professional/hybrid。

## 近期关键变更（2026-05-01）

- 虚拟试衣 v2 多引擎多模式正式上线（strict/balanced/replace/realistic/realistic_v2/professional/hybrid），CatVTON 深度学习 + 百炼 + Warp 几何引擎全支持
- CatVTON 后处理修复（尺寸不匹配 → `quick_enhance()` 快速路径）
- 极限 VRAM 优化（8GB 可用）、白盒调试工具、实时日志

## 近期关键变更（2026-04-25）

- **Flutter Web 渲染修复**：修复了登录页标题 `Text` widget 在 Web 上的 `debugSize == size` 断言错误（通过添加 `maxLines: 1` 约束）。

## 近期关键变更（2026-04-10）

- 前后端统一响应包裹：`success/data/error/message`。
- 智能穿搭 `generate` 支持结构化地址 `address`，前端不再拼接地址字符串。
- 每套搭配新增 `ai_recommendation`：`outfit/style/score/reasons[3]`，并在卡片展示。
- 首页今日推荐通过 `SharedPreferences` 缓存并按“自然日”失效，避免旧推荐长期停留。
- `PlatformImage` 新增统一失败占位（文案：图片加载失败）。

## 构建发布版本

### Android

```bash
flutter build apk --release
# 或
flutter build appbundle --release
```

### iOS

```bash
flutter build ios --release
```

## 常见问题

### Q: 无法连接到后端 API

A: 检查以下几点：
1. 后端服务是否正在运行
2. API 地址是否正确配置
3. 网络权限是否已添加（Android: AndroidManifest.xml, iOS: Info.plist）

### Q: 图片选择不工作

A: 确保已添加相应权限：
- Android: `AndroidManifest.xml` 中添加相机和存储权限
- iOS: `Info.plist` 中添加相机和相册权限

### Q: Token 过期怎么办

A: Token 默认有效期 24 小时，过期后需要重新登录。

## 下一步建议

- [ ] 增加更多情绪与场景模板，丰富解释性文案
- [ ] 增加端到端/集成测试覆盖（Web/真机）
- [ ] 训练专用服饰分类模型（替代 FashionCLIP 零样本）

## 许可证

MIT License
