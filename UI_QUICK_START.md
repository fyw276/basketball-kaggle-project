# 前端 UI 改进 - 快速使用指南

## 🎨 设计系统已集成

你的前端已经完成了全面的视觉升级！所有新组件和主题都已集成到项目中，可以直接使用。

---

## 📦 新增组件和文件

### 主题系统
```
mobile/lib/core/theme/app_theme.dart
```
定义了所有的颜色、文本样式、组件主题和渐变。

### 自定义组件
```
mobile/lib/core/widgets/
├── gradient_button.dart           # 渐变按钮
├── glass_morphism_card.dart       # 玻璃态卡片
└── modern_feature_card.dart       # 现代功能卡片
```

### 改进的屏幕
```
mobile/lib/features/
├── auth/screens/
│   ├── login_screen.dart          # ✅ 已改进
│   └── register_screen.dart       # ✅ 已改进
├── home/screens/
│   └── home_screen.dart           # ✅ 已改进
└── wardrobe/screens/
    └── wardrobe_screen.dart       # ✅ 已改进
```

---

## 🚀 快速开始

### 1. 在新屏幕中使用主题颜色

```dart
import '../../../core/theme/app_theme.dart';

// 使用预定义的颜色
Container(
  color: AppTheme.primaryColor,
  child: Text(
    '文本',
    style: TextStyle(
      color: AppTheme.textPrimaryColor,
      fontSize: 16,
    ),
  ),
)
```

**可用颜色**：
- `AppTheme.primaryColor` - 主色 (#8B5CF6)
- `AppTheme.secondaryColor` - 副色 (#EC4899)
- `AppTheme.accentColor` - 强调色 (#10B981)
- `AppTheme.errorColor` - 错误红
- `AppTheme.successColor` - 成功绿
- `AppTheme.warningColor` - 警告黄
- `AppTheme.infoColor` - 信息蓝
- `AppTheme.textPrimaryColor` - 主文本
- `AppTheme.textSecondaryColor` - 次级文本
- `AppTheme.backgroundColor` - 页面背景
- `AppTheme.surfaceColor` - 卡片背景
- `AppTheme.borderColor` - 边框色

### 2. 使用渐变按钮

```dart
import '../../../core/widgets/gradient_button.dart';

GradientButton(
  text: '按钮文本',
  gradient: AppTheme.primaryGradient,
  onPressed: () {
    // 处理点击
  },
  isLoading: _isLoading,
)
```

**参数**：
- `text` (String) - 按钮文本
- `gradient` (LinearGradient) - 渐变背景
- `onPressed` (VoidCallback) - 点击回调
- `isLoading` (bool) - 是否loading状态（可选）
- `height` (double) - 按钮高度（默认 54）
- `borderRadius` (double) - 圆角半径（默认 12）

### 3. 使用现代功能卡片

```dart
import '../../../core/widgets/modern_feature_card.dart';

ModernFeatureCard(
  icon: Icons.star,
  title: '功能标题',
  subtitle: '功能描述',
  gradient: LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF8B5CF6), Color(0xFFEC4899)],
  ),
  onTap: () {
    print('卡片被点击');
  },
)
```

**参数**：
- `icon` (IconData) - 卡片图标
- `title` (String) - 标题文本
- `subtitle` (String) - 描述文本
- `gradient` (LinearGradient) - 背景渐变
- `onTap` (VoidCallback) - 点击回调

### 4. 使用玻璃态卡片

```dart
import '../../../core/widgets/glass_morphism_card.dart';

GlassMorphismCard(
  borderRadius: 16,
  blurAmount: 10,
  backgroundColor: Colors.white,
  child: Padding(
    padding: EdgeInsets.all(16),
    child: Text('玻璃态效果'),
  ),
  onTap: () {},
)
```

**参数**：
- `child` (Widget) - 卡片内容
- `borderRadius` (double) - 圆角（默认 16）
- `blurAmount` (double) - 模糊度（默认 10）
- `backgroundColor` (Color) - 背景色（默认白色）
- `bordered` (bool) - 是否有边框（默认 true）

### 5. 使用文本样式

```dart
// 使用主题中预定义的文本样式
Text(
  '大标题',
  style: Theme.of(context).textTheme.displayLarge,
)

Text(
  '正文',
  style: Theme.of(context).textTheme.bodyMedium,
)

Text(
  '标题',
  style: Theme.of(context).textTheme.headlineSmall,
)
```

### 6. 使用渐变背景

```dart
Container(
  decoration: const BoxDecoration(
    gradient: AppTheme.primaryGradient,
  ),
  child: Center(
    child: Text('渐变背景'),
  ),
)
```

**可用渐变**：
- `AppTheme.primaryGradient` - 紫→粉 渐变
- `AppTheme.accentGradient` - 绿渐变

---

## 🎯 颜色组合方案

如果需要自定义渐变，这里是推荐的颜色组合：

### 功能卡片渐变
```dart
// 用户画像
LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
)

// 我的衣橱
LinearGradient(
  colors: [Color(0xFF10B981), Color(0xFF059669)],
)

// 相似度分析
LinearGradient(
  colors: [Color(0xFFF59E0B), Color(0xFFD97706)],
)

// 搭配推荐
LinearGradient(
  colors: [Color(0xFF8B5CF6), Color(0xFFEC4899)],
)

// 适合度评分
LinearGradient(
  colors: [Color(0xFFEC4899), Color(0xFFF472D0)],
)
```

---

## 📝 设计规范

### 间距
遵循 8px 倍数系统：
- xs: 4px
- sm: 8px
- md: 16px
- lg: 24px
- xl: 32px
- 2xl: 48px

### 圆角
- 小元素: 12px
- 标准: 16px
- 大元素: 20px

### 字号
- 大标题: 32px (bold)
- 标题: 20-24px (semibold)
- 正文: 14-16px (regular)
- 标签: 12px (regular)

### 投影
卡片和按钮使用 `boxShadow` 时，建议：
```dart
boxShadow: [
  BoxShadow(
    color: primaryColor.withOpacity(0.25),
    blurRadius: 12,
    offset: const Offset(0, 4),
  ),
]
```

---

## ✨ 最佳实践

### ✅ 推荐做法

1. **总是使用 AppTheme 中的颜色**
   ```dart
   // ✅ 好
   color: AppTheme.primaryColor,

   // ❌ 不好
   color: Colors.blue,
   ```

2. **为按钮使用渐变按钮组件**
   ```dart
   // ✅ 好
   GradientButton(...)

   // ❌ 不好
   ElevatedButton(...)
   ```

3. **应用合适的间距**
   ```dart
   // ✅ 好
   const SizedBox(height: 16),

   // ❌ 不好
   const SizedBox(height: 13),
   ```

4. **使用 const 构造提高性能**
   ```dart
   // ✅ 好
   const Text('文本')
   const SizedBox(height: 16)

   // ❌ 不好
   Text('文本')
   SizedBox(height: 16)
   ```

### ❌ 避免做法

1. **不要混合使用多种颜色系统**
2. **不要创建自定义主题而不使用 AppTheme**
3. **不要使用内联样式，应该从主题继承**
4. **不要创建不圆角的卡片（minimum 12px）**

---

## 🔍 常见问题

### Q: 如何改变全局主题？
A: 所有主题设置都在 `AppTheme` 中。修改 `AppTheme.lightTheme` 的属性会影响整个应用。

### Q: 如何添加暗色主题？
A: 在 `AppTheme` 中添加 `static ThemeData get darkTheme { ... }`，然后在 `main.dart` 中配置 `darkTheme` 参数。

### Q: 我可以为不同的屏幕使用不同的颜色吗？
A: 可以，但建议在 `AppTheme` 中添加新的颜色常量。

### Q: 如何自定义卡片的样式？
A: 修改 `AppTheme` 中的 `cardTheme`，或者在特定组件中覆盖样式。

### Q: 渐变按钮可以禁用吗？
A: 可以，设置 `onPressed: null` 会自动禁用。

---

## 📚 进阶用法

### 创建自定义渐变组合
```dart
const myGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [Color(0xFF...), Color(0xFF...)],
);
```

### 创建自定义卡片
```dart
Card(
  color: AppTheme.surfaceColor,
  elevation: 0,
  shape: RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(16),
    side: const BorderSide(color: AppTheme.borderColor),
  ),
  child: /* ... */,
)
```

### 动画卡片
```dart
ScaleTransition(
  scale: _animation,
  child: ModernFeatureCard(...),
)
```

---

## 🐛 调试提示

如果颜色看起来不对：
1. 检查 `AppTheme` 中的颜色定义是否正确
2. 确保 `main.dart` 应用了正确的主题
3. 清除 Flutter 构建缓存：`flutter clean`

如果布局看起来奇怪：
1. 检查是否正确使用了 `SizedBox` 间距
2. 确保卡片的 `elevation` 为 0（使用边框代替）
3. 验证圆角半径是否为 12px 的倍数

---

## 📖 文档索引

- [DESIGN_GUIDE.md](./DESIGN_GUIDE.md) - 完整的设计系统文档
- [FRONTEND_UI_IMPROVEMENT.md](./FRONTEND_UI_IMPROVEMENT.md) - 详细的改进说明
- [main.dart](./mobile/lib/main.dart) - 应用程序入口
- [app_theme.dart](./mobile/lib/core/theme/app_theme.dart) - 主题系统定义

---

## 💡 提示

- 定期查看 `DESIGN_GUIDE.md` 以了解最新的设计规范
- 在创建新屏幕时参考现有的改进屏幕
- 使用组件库中的组件而不是重新创建
- 保持一致的间距和颜色使用

---

**最后更新**: 2026 年 3 月 25 日

**设计系统版本**: 1.0

**作者**: GitHub Copilot

---
