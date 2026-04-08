# Flutter 移动端快速开始指南

## 第一步：安装 Flutter

如果还没有安装 Flutter，请访问 [Flutter 官网](https://flutter.dev/docs/get-started/install) 安装。

验证安装：
```bash
flutter doctor
```

## 第二步：安装依赖

```bash
cd mobile
flutter pub get
```

## 第三步：配置后端地址

编辑 `lib/core/services/api_client.dart`，修改第 6 行的 `baseUrl`：

```dart
static const String baseUrl = 'http://10.0.2.2:8010/api/v1';  // Android 模拟器
// 或
static const String baseUrl = 'http://127.0.0.1:8010/api/v1';  // iOS 模拟器
// 或
static const String baseUrl = 'http://192.168.1.100:8010/api/v1';  // 真机（替换为你的 IP）
```

## 第四步：启动后端服务

确保后端服务正在运行：

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

## 第五步：运行应用

```bash
# 列出可用设备
flutter devices

# 运行应用
flutter run
```

## 第六步：测试功能

1. **注册账号**
   - 打开应用
   - 点击"还没有账号？立即注册"
   - 填写用户名、邮箱、密码
   - 点击"注册"

2. **登录**
   - 输入用户名和密码
   - 点击"登录"

3. **浏览功能**
   - 主页显示所有功能模块
   - 点击各个功能卡片进入对应页面

## 常见问题

### 1. 无法连接到后端

**问题**: 应用显示网络错误

**解决方案**:
- 确保后端服务正在运行
- 检查 API 地址配置是否正确
- Android 模拟器使用 `10.0.2.2` 而不是 `localhost`
- 真机需要使用电脑的实际 IP 地址

### 2. 权限错误

**问题**: 无法访问相机或相册

**解决方案**:
- Android: 检查 `AndroidManifest.xml` 中的权限配置
- iOS: 检查 `Info.plist` 中的权限配置
- 在设备设置中手动授予权限

### 3. 依赖安装失败

**问题**: `flutter pub get` 失败

**解决方案**:
```bash
# 清理缓存
flutter clean

# 重新获取依赖
flutter pub get

# 如果还是失败，尝试升级 Flutter
flutter upgrade
```

### 4. 构建失败

**问题**: `flutter run` 失败

**解决方案**:
```bash
# Android
flutter clean
flutter pub get
flutter run

# iOS (需要 Mac)
cd ios
pod install
cd ..
flutter run
```

## 开发提示

### 热重载

在开发过程中，修改代码后按 `r` 进行热重载，按 `R` 进行热重启。

### 调试

```bash
# 查看日志
flutter logs

# 调试模式运行
flutter run --debug

# 性能分析
flutter run --profile
```

### 代码格式化

```bash
# 格式化代码
flutter format lib/

# 分析代码
flutter analyze
```

## 下一步

现在你已经成功运行了移动端应用！接下来可以：

1. 完善各个功能页面的实现
2. 添加图片上传功能
3. 实现相似度分析界面
4. 实现搭配推荐界面
5. 优化 UI/UX

查看 `README.md` 了解更多开发信息。
