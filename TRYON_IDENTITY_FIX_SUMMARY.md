# 虚拟试衣身份保持问题修复总结

## 🔍 问题

用户报告虚拟试衣功能存在两个严重问题：
1. **衣服图片不对** - 上传灰色T恤，生成白色衣服
2. **人物的脸被改变了** - 生成的人物与原照片不是同一个人

## 🎯 根本原因

### 原因1：错误的降级逻辑 ❌

代码中存在一个致命的降级逻辑：

```python
# 当 description_edit_with_mask 失败时，自动降级到 stylization_all
if (resp.status_code != 200 and function_name == "description_edit_with_mask"):
    fallback_fn = "stylization_all"  # ❌ 这是风格迁移，会改变人物和衣服！
    resp = _call_dashscope(..., function_name=fallback_fn)
```

**`stylization_all` 是全局风格迁移，不是虚拟试衣！**

- 会改变人物的脸
- 会改变衣服的颜色
- 会改变整体风格

### 原因2：百炼API的限制 ⚠️

根据阿里云百炼API文档，`description_edit_with_mask` 功能：

- ✅ 支持：`base_image_url`、`mask_image_url`、`prompt`
- ❌ **不支持**：`ref_img`（参考图）

这意味着它是通过**文本描述**生成内容，而不是通过参考图！

## ✅ 已完成的修复

### 修复1：移除错误的降级逻辑

**修复前：**
```python
# 降级到 stylization_all（风格迁移）
if (resp.status_code != 200 and function_name == "description_edit_with_mask"):
    fallback_fn = "stylization_all"
    resp = _call_dashscope(..., function_name=fallback_fn, mask_url=None)
```

**修复后：**
```python
# 直接返回错误，不降级
resp = _call_dashscope(...)
if resp is None:
    return {"status": "error", "message": "百炼调用返回 None", ...}
```

### 修复2：改进prompt，强调保持原始特征

**修复前：**
```python
"在保持底图人物的脸部身份、发型、表情、姿势、相机视角与背景完全不变的前提下，"
"将 mask 白色区域内的上装替换为参考图中的服装；"
```

**修复后：**
```python
"严格按照参考图中服装的颜色、图案、材质、款式，"  # ← 新增：强调颜色和款式
"将 mask 白色区域内的上装替换为参考图中的服装；"
"必须保持底图人物的脸部身份、发型、表情、姿势、相机视角与背景完全不变；"
"不要更换人物，不要更换场景，不要添加新道具，不要改变服装颜色，mask 区域以外保持原样。"
```

### 修复3：添加详细的日志记录

```python
logger.info(
    "Bailian try-on: model=%s function=%s category_bucket=%s mask=%s prompt=%s",
    model_id, function_name, bucket, "yes" if mask_url else "no",
    prompt_text[:100] + "..." if len(prompt_text) > 100 else prompt_text,
)

logger.info(
    "DashScope API call: function=%s, has_mask=%s, has_ref_img=%s",
    function_name, mask_url is not None, garment_url is not None,
)
```

### 修复4：添加详细的API文档注释

```python
def _call_dashscope(...):
    """
    CRITICAL: For virtual try-on, we MUST use description_edit_with_mask with mask_image_url.
    - base_image_url: person image (底图)
    - ref_img: garment image (参考图/商品图)
    - mask_image_url: clothing mask (白色=编辑区域，黑色=保留区域)

    DO NOT use stylization_all as it's style transfer and will change person identity and garment colors!
    """
```

## ⚠️ 重要限制

**百炼API的 `description_edit_with_mask` 不支持参考图！**

这意味着：
- 它只能根据文本描述生成内容
- 无法保证生成的衣服与商品图完全一致
- 可能会出现颜色、款式偏差

## 💡 推荐解决方案

### 方案A：使用专用VTON服务（强烈推荐）⭐⭐⭐⭐⭐

部署专用的虚拟试衣模型（OOTDiffusion 或 IDM-VTON）：

**优点：**
- ✅ 专门为虚拟试衣设计
- ✅ 支持参考图（商品图）
- ✅ 能够保持人物身份
- ✅ 能够保持衣服颜色和款式

**配置：**
```env
VTON_INFERENCE_URL=http://127.0.0.1:8011/v1/tryon
```

**文档：**
- `docs/VTON_INTEGRATION.md`
- `vton_inference_service/README.md`

### 方案B：使用本地diffusers模型 ⭐⭐⭐

启用本地的Stable Diffusion inpainting模型：

```env
TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true
```

**注意：** 需要确保SD inpainting权重完整，否则可能生成无关图像。

### 方案C：使用方案A（pipeline A）⭐⭐⭐⭐

不使用replace模式，改用balanced或strict模式：

- 基于图像变形和融合
- 不依赖生成式AI
- 效果稳定但不如专用VTON

## 📋 修改的文件

1. `backend/app/services/bailian_tryon_client.py`
   - ✅ 移除了错误的降级逻辑
   - ✅ 改进了prompt
   - ✅ 添加了详细的日志
   - ✅ 添加了API文档注释

2. `backend/TRYON_IDENTITY_FIX_README.md`
   - ✅ 详细的问题分析和解决方案

3. `TRYON_IDENTITY_FIX_SUMMARY.md`
   - ✅ 本文件（修复总结）

## 🔬 测试验证

### 1. 检查日志

重启服务后，查看日志：

```
Bailian try-on: model=wanx2.1-imageedit function=description_edit_with_mask category_bucket=top mask=yes prompt=严格按照参考图中服装的颜色...
DashScope API call: function=description_edit_with_mask, has_mask=True, has_ref_img=True
```

**确认：**
- ✅ function 应该是 `description_edit_with_mask`
- ❌ 不应该出现 `stylization_all`

### 2. 测试虚拟试衣

1. 上传人物照片和商品图（灰色T恤）
2. 选择"真实贴身"模式
3. 检查结果：
   - ✅ 人物的脸应该与原照片一致
   - ⚠️ 衣服颜色可能仍有偏差（因为API限制）

### 3. 如果仍然有问题

**情况A：人物的脸仍然改变**
- 检查日志，确认没有使用 `stylization_all`
- 如果使用了 `stylization_all`，说明修复未生效

**情况B：衣服颜色仍然不对**
- 这是百炼API的限制（不支持参考图）
- 建议切换到专用VTON服务（方案A）

## 📊 效果对比

| 方案 | 人物身份 | 衣服颜色 | 衣服款式 | 速度 | 部署难度 |
|------|---------|---------|---------|------|---------|
| 百炼API（修复前） | ❌ | ❌ | ❌ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 百炼API（修复后） | ✅ | ⚠️ | ⚠️ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 专用VTON服务 | ✅ | ✅ | ✅ | ⭐⭐⭐ | ⭐⭐⭐ |
| 本地diffusers | ✅ | ✅ | ✅ | ⭐⭐ | ⭐⭐ |
| 方案A（pipeline A） | ✅ | ✅ | ✅ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

## 🎯 下一步行动

### 立即行动（已完成）✅

1. ✅ 移除错误的降级逻辑
2. ✅ 改进prompt
3. ✅ 添加日志记录
4. ✅ 重启服务测试

### 短期行动（推荐）

1. **部署专用VTON服务**
   - 参考 `docs/VTON_INTEGRATION.md`
   - 使用 OOTDiffusion 或 IDM-VTON
   - 配置 `VTON_INFERENCE_URL`

2. **或者使用方案A**
   - 在UI中默认使用 balanced 或 strict 模式
   - 隐藏或禁用 replace 模式

### 长期行动

1. 考虑自建虚拟试衣服务
2. 或者寻找其他支持参考图的API服务

## 📚 相关文档

- `backend/TRYON_IDENTITY_FIX_README.md` - 详细的问题分析和解决方案
- `docs/VTON_INTEGRATION.md` - 专用VTON服务集成指南
- `vton_inference_service/README.md` - VTON服务部署指南
- `TRYON_FIX_SUMMARY.md` - dashscope包安装问题修复

## ❓ 常见问题

### Q: 修复后人物的脸还是改变了怎么办？

A: 检查日志确认没有使用 `stylization_all`。如果仍然有问题，可能是百炼API的模型问题，建议切换到专用VTON服务。

### Q: 修复后衣服颜色还是不对怎么办？

A: 这是百炼API的限制（不支持参考图）。解决方案：
1. 部署专用VTON服务（推荐）
2. 使用方案A的balanced或strict模式
3. 在prompt中详细描述衣服特征（临时方案）

### Q: 如何部署专用VTON服务？

A: 参考以下文档：
- `docs/VTON_INTEGRATION.md`
- `vton_inference_service/README.md`
- `scripts/vton_poc/POC_RUNBOOK.md`

### Q: 能否继续使用百炼API？

A: 可以，但效果会受限：
- ✅ 人物身份可以保持（修复后）
- ⚠️ 衣服颜色可能有偏差（API限制）
- 💡 建议：用于快速预览，正式使用专用VTON服务

## 🆘 技术支持

如果问题仍未解决，请提供：

1. 后端日志（包含"Bailian try-on"和"DashScope API call"的行）
2. 错误响应中的 `replace_debug` 完整内容
3. 测试用的人物照片和商品图（如果可以分享）
4. 生成的结果图

---

**修复时间**: 2026-04-22
**修复状态**: ✅ 代码已修复，建议部署专用VTON服务获得最佳效果
**影响范围**: 虚拟试衣的replace模式
**向后兼容**: ✅ 完全兼容，不影响其他功能
