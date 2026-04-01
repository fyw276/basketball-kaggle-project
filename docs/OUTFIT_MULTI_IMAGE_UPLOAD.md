# 搭配推荐：多图上传

## 行为说明

- **端点**: `POST /api/v1/analysis/outfits`
- **单图（兼容）**: multipart 字段名 `file`，与旧版客户端一致。
- **多图**: 字段名 `files`，同一请求内可重复出现多次（每张图一个 part），最多 **5** 张。
- **服务端处理**:
  - 对每张图分别做 CLIP（失败则 MobileNet）识别；
  - **特征向量**：按维度对齐后（较短向量右侧补零）再对多张图取 **算术平均**；
  - **风格标签 / 适用场景**：合并并去重；
  - **品类**：以 **第一张** 图为主（与预览、主色提取一致）；
  - **预览与落库**：使用 **第一张** 图的像素作为展示与保存目标图。

## Flutter 客户端

- `ApiClient.recommendOutfits`：`imageFile` 单图，或 `imageFiles` 多图。
- 单图仍发 `file`；多图每张 part 使用字段名 `files`（与 FastAPI `List[UploadFile]` 一致）。
- 穿搭推荐页：`ImagePickerSection` 最多 5 张、可多选，调用 `recommendOutfitsFromXFiles`。

## 相关代码

- 后端：`backend/app/api/analysis.py`（`MAX_OUTFIT_UPLOAD_IMAGES`、`recommend_outfits`、`_merge_clip_like_results`）
- 前端：`mobile/lib/core/services/api_client.dart`、`mobile/lib/features/analysis/screens/outfit_recommend_screen.dart`
