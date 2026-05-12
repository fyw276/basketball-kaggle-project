# Flutter Try-On v2 完整模式支持

**创建日期**：2026-05-10
**状态**：已完成

## 目的

在 Flutter 前端补全 Try-On v2 所有 6 种模式（strict/stable/replace/realistic/professional/hybrid）的 UI 接入，并添加 `debug_mode` 参数到 API 客户端。

## 实现方式

### 1. Flutter UI — 效果模式选择器（`virtual_tryon_screen.dart`）

新增 2 种模式：

| 模式 | API value（/garment） | API value（/validate-input） | 说明 |
|-------|----------------------|------------------------------|------|
| `professional` | `detail_fidelity` | `professional` | 细节保真：CatVTON 深度学习 + 颜色保真增强 |
| `hybrid` | `stable_fast` | `hybrid` | 混合模式：Warp 像素保真（100%衣服颜色/图案）+ CatVTON 光影增强 |

> **2026-05-10 修复**：Flutter 端 `apiValue` 映射到 `/garment` 端点实际接受的 `detail_fidelity|blend|stable_fast`，新增 `validateApiValue` 用于 `/validate-input` 端点（该端点接受 `professional|hybrid`）。

默认值：**`hybrid`**，因为 hybrid 兼顾衣服图案保真和自然贴合效果，是最佳推荐。

### 2. Flutter API 客户端（`api_client.dart`）

在 `virtualTryonV2Garment` 方法中新增参数：

```dart
/// 白盒调试模式: off=关闭（默认）; preprocess_only=仅前处理，极快返回；
/// full=完整管线并保存所有中间产物。
String debugMode = 'off',
```

`debug_mode` 会以 Form 字段形式传递给后端 `POST /api/v2/tryon/garment`。

### 3. Flutter UI — 混合模式提示卡

当用户选择 hybrid 模式时，显示说明卡片：
- 说明原理：Warp 保真 + CatVTON 光影增强
- 说明效果：100% 保留衣服原始图案/颜色 + AI 光影/褶皱叠加

## 关键代码

### `virtual_tryon_screen.dart` 模式枚举

```dart
enum _TryOnQualityMode {
  professional, // 'detail_fidelity'（/garment）/ 'professional'（/validate-input）
  hybrid,       // 'stable_fast'（/garment）/ 'hybrid'（/validate-input，默认）
}

extension _TryOnQualityModeApi on _TryOnQualityMode {
  /// 传给 /garment 端点的 mode 值
  String get apiValue => ...;       // detail_fidelity / stable_fast

  /// 传给 /validate-input 端点的 mode 值
  String get validateApiValue => ...; // professional / hybrid
}
```

### `api_client.dart` 新增参数

```dart
Future<Map<String, dynamic>> virtualTryonV2Garment({
  ...
  String debugMode = 'off',  // 新增
  Duration timeout = const Duration(seconds: 2400),
}) async {
  ...
  if (debugMode.trim().isNotEmpty && debugMode != 'off') {
    request.fields['debug_mode'] = debugMode.trim();
  }
}
```

## 遇到的问题

1. **Flutter `_TryOnQualityMode` 默认值**：之前默认 `professional`，改为 `hybrid` 更合适，因为 professional 依赖 CatVTON 全流程（慢），hybrid 也用 CatVTON 但先走 Warp 保真，效果更稳定
2. **文档格式问题**：`docs/TRYON_TECH_BLUEPRINT_AB.md` 中的反引号内含特殊字符导致 StrReplace 无法匹配，改用 Write 工具重写整个文件

## 注意事项

- `strict_identity` 参数在后端有默认值（`TRYON_V2_STRICT_IDENTITY`），Flutter 客户端目前未暴露此参数，因为后端已有全局开关
- `realistic_v2` 模式后端支持但 Flutter UI 未暴露，因为与 realistic 差别不大
- debug_mode 设为 `preprocess_only` 时只返回 mask 生成结果（极快），适合调 mask；设为 `full` 时返回完整管线 + 所有中间产物（耗时最长）
