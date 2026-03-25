# 智能穿搭助手 - Flutter 移动端

这是智能穿搭助手的 Flutter 移动端应用。

## 功能特性

- ✅ 用户注册和登录
- ✅ JWT Token 认证
- ✅ 主页导航
- 🚧 用户画像管理
- 🚧 衣橱管理
- 🚧 相似度分析
- 🚧 搭配推荐
- 🚧 适合度评分

## 技术栈

- **Flutter**: 3.0+
- **状态管理**: Provider
- **网络请求**: Dio
- **路由**: GoRouter
- **本地存储**: SharedPreferences
- **图片选择**: ImagePicker

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
│       │       ├── login_screen.dart
│       │       └── register_screen.dart
│       ├── home/                   # 主页
│       │   └── screens/
│       │       └── home_screen.dart
│       ├── profile/                # 用户画像
│       ├── wardrobe/               # 衣橱管理
│       └── analysis/               # 分析功能
│           └── screens/
│               ├── similarity_screen.dart
│               ├── outfit_screen.dart
│               └── suitability_screen.dart
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

2. **配置后端 API 地址**

编辑 `lib/core/services/api_client.dart`，修改 `baseUrl`：

```dart
static const String baseUrl = 'http://YOUR_BACKEND_IP:8000/api/v1';
```

注意：
- Android 模拟器使用 `http://10.0.2.2:8000/api/v1`
- iOS 模拟器使用 `http://localhost:8000/api/v1`
- 真机使用实际 IP 地址

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

## 下一步开发

- [ ] 完善用户画像表单
- [ ] 实现衣橱管理功能
- [ ] 实现图片上传和预览
- [ ] 实现相似度分析界面
- [ ] 实现搭配推荐界面
- [ ] 实现适合度评分界面
- [ ] 添加加载状态和错误处理
- [ ] 优化 UI/UX
- [ ] 添加单元测试和集成测试

## 许可证

MIT License
