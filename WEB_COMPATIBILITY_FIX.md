# Flutter Web 兼容性修复

## 问题原因

Flutter Web 不支持 `dart:io` 的 `File` 类和 `MultipartFile.fromFile()` 方法，因为 Web 平台没有文件系统访问权限。

## 解决方案

使用 `XFile` 的 `readAsBytes()` 方法读取文件字节，然后使用 `MultipartFile.fromBytes()` 上传。

## 已修复的文件

### 1. API Client (`mobile/lib/core/services/api_client.dart`)

**修改内容**:
- 添加 `image_picker` 导入
- 所有图片上传方法改为接受 `XFile` 参数
- 使用 `MultipartFile.fromBytes()` 替代 `MultipartFile.fromFile()`

**新方法**:
- `addGarmentFromXFile(XFile)` - 添加服饰
- `analyzeSimilarityFromXFile(XFile)` - 相似度分析
- `recommendOutfitsFromXFile(XFile)` - 搭配推荐
- `analyzeSuitabilityFromXFile(XFile)` - 适合度评分

### 2. 衣橱管理 (`mobile/lib/features/wardrobe/screens/wardrobe_screen.dart`)

**修改内容**:
- `_addGarment()` 方法直接传递 `XFile` 对象
- 调用 `addGarmentFromXFile()` 而不是 `addGarment()`

### 3. 相似度分析 (`mobile/lib/features/analysis/screens/similarity_screen.dart`)

**修改内容**:
- 移除 `dart:io` 导入
- `_selectedImage` 类型从 `File?` 改为 `XFile?`
- 使用 `Image.memory()` 和 `FutureBuilder` 显示图片
- 调用 `analyzeSimilarityFromXFile()` 而不是 `analyzeSimilarity()`
- 修正数据字段映射以匹配后端 API

### 4. 搭配推荐 (`mobile/lib/features/analysis/screens/outfit_screen.dart`)

**修改内容**:
- 添加 `dart:typed_data` 导入
- `_selectedImage` 类型保持为 `XFile?`
- 使用 `Image.memory()` 和 `FutureBuilder` 显示图片
- 调用 `recommendOutfitsFromXFile()` 而不是 `recommendOutfits()`

### 5. 适合度评分 (`mobile/lib/features/analysis/screens/suitability_screen.dart`)

**修改内容**:
- 移除 `dart:io` 导入，添加 `dart:typed_data`
- `_selectedImage` 类型从 `File?` 改为 `XFile?`
- 使用 `Image.memory()` 和 `FutureBuilder` 显示图片
- 调用 `analyzeSuitabilityFromXFile()` 而不是 `analyzeSuitability()`

## 图片显示方法

### Web 兼容的图片显示

```dart
// ❌ 错误 - 不支持 Web
Image.file(File(path))

// ✅ 正确 - 支持 Web
FutureBuilder<List<int>>(
  future: xFile.readAsBytes(),
  builder: (context, snapshot) {
    if (snapshot.hasData) {
      return Image.memory(snapshot.data!);
    }
    return CircularProgressIndicator();
  },
)
```

## 文件上传方法

### Web 兼容的文件上传

```dart
// ❌ 错误 - 不支持 Web
MultipartFile.fromFile(path)

// ✅ 正确 - 支持 Web
final bytes = await xFile.readAsBytes();
MultipartFile.fromBytes(
  bytes,
  filename: xFile.name,
)
```

## 测试步骤

### 1. 重启 Flutter Web

在 Flutter 终端按 `R` 键（热重启）

### 2. 测试衣橱管理

1. 点击"我的衣橱"
2. 点击右下角"+"按钮
3. 选择图片
4. 验证上传成功

### 3. 测试相似度分析

1. 点击"相似度分析"
2. 选择图片
3. 点击"开始分析"
4. 验证结果显示

## 常见错误

### 错误 1: Unsupported operation: MultipartFile is only supported where dart:io is available

**原因**: 使用了 `MultipartFile.fromFile()`

**解决**: 使用 `MultipartFile.fromBytes()`

### 错误 2: Cannot use 'dart:io' in web

**原因**: 导入了 `dart:io`

**解决**: 移除 `import 'dart:io';`

### 错误 3: The getter 'path' isn't defined for the type 'XFile'

**原因**: `XFile` 在 Web 上没有 `path` 属性

**解决**: 使用 `readAsBytes()` 读取字节

## 完整修复清单

- [x] API Client - 添加 XFile 支持方法
- [x] 衣橱管理 - 使用 XFile 上传
- [x] 相似度分析 - 使用 XFile 和 Image.memory
- [x] 搭配推荐 - 使用 XFile 和 Image.memory
- [x] 适合度评分 - 使用 XFile 和 Image.memory

## 下一步

1. 重启 Flutter Web（在终端按 `R` 键热重启）
2. 测试所有功能：
   - 用户画像创建
   - 衣橱管理（添加/查看/删除服饰）
   - 相似度分析
   - 搭配推荐
   - 适合度评分
3. 如果遇到 API 错误，检查后端服务是否运行
4. 查看浏览器控制台获取详细错误信息

## 参考

- [Flutter Web 文件上传](https://docs.flutter.dev/platform-integration/web/file-handling)
- [image_picker Web 支持](https://pub.dev/packages/image_picker#web)
- 本项目 `ApiClient` 使用 `package:http` 的 `MultipartFile.fromBytes`（见 `mobile/lib/core/services/api_client.dart`），无需 Dio。

## 另见（智能穿搭 / API 与 Web）

- [docs/SMART_OUTFIT_FLUTTER_WEB.md](docs/SMART_OUTFIT_FLUTTER_WEB.md)：智能穿搭、CORS、认证顺序、衣橱图片 URL、`PageView` 鼠标滑动与响应式布局说明。
