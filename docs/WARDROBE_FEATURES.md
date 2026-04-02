# 衣橱：整套拆分与前端提示

## 整套穿搭拆分 `POST /api/v1/wardrobe/split-outfit`

- **用途**：上传一张全身/穿搭图，服务端裁切为多块预览图，可选 `save=true` 写入衣橱。
- **表单字段**：
  - `file`：图片（必填）
  - `save`：是否入库（`true`/`false`）
  - `selected_indexes`：要保存的块下标，逗号分隔（如 `0,2`）；仅 `save=true` 时有效。
- **拆分逻辑**（`backend/app/services/outfit_split.py`）：
  - 整图与分块使用 **CLIP**（不可用则 **MobileNet `ImageRecognizer`**）估计品类。
  - **全身照**且更像裙装一体时，输出 **连衣裙/裙子 + 鞋**，并扫描左右窄条尝试识别 **包**，避免把连衣裙硬拆成「上衣 + 裤子」。
  - 否则使用 **上装 / 下装 / 鞋** 三条横带，并对中段做裙装与裤装的二次区分。
  - 入库品类均落在 `VALID_CATEGORIES`（含 `连衣裙`、`包` 等）。
- **CLIP**：`backend/app/ml/clip_recognizer.py` 中已增加 **`连衣裙`** 与 **`裙子`** 区分的候选与 prompt。

详见 [API_EXAMPLES.md](../backend/API_EXAMPLES.md) 中「整套穿搭拆分」示例。

## 删除衣物后的 SnackBar（撤销）

- **文件**：`mobile/lib/core/utils/app_snackbar.dart` 的 `showAppSnackBar`。
- **Flutter 3.41+**：带 `SnackBarAction` 时，`SnackBar` 默认 **`persist: true`**，会**忽略** `duration`，直到用户点击操作。
- **本项目**：统一传入 **`persist: false`**，在 **`kAppSnackBarDuration`（5 秒）** 到时自动关闭；用户仍可在 5 秒内点击「撤销」。

## 衣橱页拆分 UI

- **文件**：`mobile/lib/features/wardrobe/screens/wardrobe_screen.dart`。
- 拆分结果列表使用 **`PlatformImage` + `resolveGarmentImageUrl`** 显示每块缩略图，品类文案来自后端返回的 `category`。
