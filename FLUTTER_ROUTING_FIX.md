# Flutter 路由问题修复

## 问题描述

用户注册和登录 API 调用成功，但登录后页面没有跳转到主页，仍然停留在登录页面。

## 根本原因

`main.dart` 中的 `GoRouter` 在 `Consumer<AuthProvider>` 内部创建，导致每次 `AuthProvider` 状态改变时，整个路由器都会被重新创建，丢失路由状态。

## 修复方案

### 1. 修改 `mobile/lib/main.dart`

将 `MyApp` 从 `StatelessWidget` 改为 `StatefulWidget`，在 `initState` 中创建 `GoRouter` 并使用 `refreshListenable` 监听认证状态变化。

**关键改动**：
```dart
class _MyAppState extends State<MyApp> {
  late final AuthProvider _authProvider;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _authProvider = AuthProvider(ApiClient());

    _router = GoRouter(
      initialLocation: '/login',
      refreshListenable: _authProvider,  // 监听认证状态变化
      redirect: (context, state) {
        // 路由守卫逻辑
      },
      routes: [
        // 路由配置
      ],
    );
  }
}
```

### 2. 添加调试日志

在 `auth_provider.dart` 和 `login_screen.dart` 中添加 `print` 语句，帮助追踪登录流程。

## 测试步骤

### 1. 重启 Flutter Web

```bash
# 停止当前运行的 Flutter Web
# 按 Ctrl+C 或关闭终端

# 重新启动
cd mobile
flutter run -d chrome
```

### 2. 测试登录流程

1. 打开 Flutter Web（例如 `http://localhost:61742`）
2. 点击"立即注册"
3. 填写注册信息：
   - 用户名: `test_user_001`
   - 邮箱: `test001@example.com`
   - 密码: `Test123!@#`
4. 注册成功后应显示提示并返回登录页
5. 使用用户名 / 邮箱 / 手机号 + 密码手动登录并跳转到主页

### 3. 查看浏览器控制台

打开浏览器开发者工具（F12），查看 Console 标签，应该看到类似输出：

```
📝 表单验证通过，开始登录...
🔐 开始登录: test_user_001
✅ 登录成功: eyJhbGciOiJIUzI1NiIs...
✅ 认证状态已更新: true
🔄 登录结果: true
✅ 登录成功，准备跳转到 /home
✅ 已调用 context.go('/home')
```

## 预期行为

### 注册流程
1. 用户填写注册表单
2. 点击"注册"按钮
3. API 调用成功
4. 显示注册成功提示并切回登录页
5. 用户手动登录后跳转到主页

### 登录流程
1. 用户填写登录表单
2. 点击"登录"按钮
3. API 调用成功
4. `AuthProvider.isAuthenticated` 设置为 `true`
5. `GoRouter` 检测到认证状态变化
6. 路由守卫重定向到 `/home`
7. 显示主页

## 技术细节

### GoRouter 的 refreshListenable

`refreshListenable` 参数允许 `GoRouter` 监听 `ChangeNotifier`（如 `AuthProvider`）的变化。当 `notifyListeners()` 被调用时，路由器会重新评估路由守卫（`redirect` 函数）。

```dart
_router = GoRouter(
  refreshListenable: _authProvider,  // 监听认证状态
  redirect: (context, state) {
    // 每次 _authProvider.notifyListeners() 被调用时执行
    final isAuthenticated = _authProvider.isAuthenticated;
    // ... 路由逻辑
  },
);
```

### 为什么之前的实现有问题？

```dart
// ❌ 错误的实现
Consumer<AuthProvider>(
  builder: (context, authProvider, _) {
    final router = GoRouter(...);  // 每次状态变化都重新创建
    return MaterialApp.router(routerConfig: router);
  },
)
```

每次 `AuthProvider` 调用 `notifyListeners()` 时，`Consumer` 的 `builder` 会重新执行，创建一个全新的 `GoRouter` 实例，导致：
- 路由历史丢失
- 当前页面状态丢失
- 导航不工作

### 正确的实现

```dart
// ✅ 正确的实现
class _MyAppState extends State<MyApp> {
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _router = GoRouter(...);  // 只创建一次
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(routerConfig: _router);
  }
}
```

`GoRouter` 只在 `initState` 中创建一次，使用 `refreshListenable` 监听状态变化。

## 常见问题

### Q1: 登录后仍然停留在登录页面？

检查：
1. 浏览器控制台是否显示调试日志
2. 是否看到 "✅ 认证状态已更新: true"
3. 是否看到 "✅ 已调用 context.go('/home')"

如果看到这些日志但仍未跳转，可能是路由守卫问题。

### Q2: 看不到调试日志？

确保：
1. Flutter Web 已重启（旧代码可能仍在运行）
2. 浏览器开发者工具已打开
3. Console 标签已选中
4. 没有过滤掉日志

### Q3: 注册后为什么没有自动登录？

检查 `auth_provider.dart` 中的 `register` 方法：
```dart
Future<bool> register(...) async {
  // ...
  // 注册成功后返回 true，由 UI 切回登录页
  return true;
}
```

这是当前产品预期流程：注册成功后先回到登录页，再由用户登录进入系统。

## 验证修复

### 成功标志

1. ✅ 注册成功后回到登录页
2. ✅ 使用刚注册账号可在登录页正常登录
3. ✅ 登录后立即跳转到主页
4. ✅ 主页显示功能卡片
5. ✅ URL 从 `/login` 变为 `/home`

### 失败标志

1. ❌ 登录后停留在登录页面
2. ❌ URL 没有变化
3. ❌ 控制台显示错误
4. ❌ 页面空白或加载中

## 下一步

修复完成后，可以测试：
1. 登出功能（如果已实现）
2. 路由守卫（未登录时访问 `/home` 应重定向到 `/login`）
3. 其他页面导航（用户画像、衣橱管理等）

## 相关文件

- `mobile/lib/main.dart` - 应用入口和路由配置
- `mobile/lib/core/providers/auth_provider.dart` - 认证状态管理
- `mobile/lib/features/auth/screens/auth_screen.dart` - 登录/注册界面
