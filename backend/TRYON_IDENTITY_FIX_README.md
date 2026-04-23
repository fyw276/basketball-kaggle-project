# 虚拟试衣身份保持问题修复指南

## 问题描述

虚拟试衣功能存在以下问题：
1. **衣服图片不对** - 生成的衣服颜色与上传的商品图不一致（例如：上传灰色T恤，生成白色衣服）
2. **人物的脸被改变了** - 生成的人物与原始照片不是同一个人

## 根本原因分析

### 问题1：错误的降级逻辑

代码中存在一个错误的降级逻辑：

```python
# 若 description_edit_with_mask 失败，自动降级到 stylization_all
if (resp is not None and resp.status_code != 200
    and function_name == "description_edit_with_mask"):
    fallback_fn = "stylization_all"  # ❌ 错误！
    resp = _call_dashscope(..., function_name=fallback_fn, mask_url=None)
```

**`stylization_all` 是风格迁移功能，不是虚拟试衣！**

- `stylization_all`: 全局风格迁移，会改变整个图像的风格，包括人物的脸和衣服颜色
- `description_edit_with_mask`: 局部修补，只修改mask区域，保持人物身份不变

当 `description_edit_with_mask` 失败时，降级到 `stylization_all` 会导致：
- 人物身份改变
- 衣服颜色改变
- 整体风格改变

### 问题2：百炼API的限制

根据阿里云百炼API文档，`description_edit_with_mask` 功能：

- ✅ 支持：`base_image_url`（底图）、`mask_image_url`（mask图）、`prompt`（文本描述）
- ❌ **不支持**：`ref_img`（参考图）

这意味着 `description_edit_with_mask` 是通过**文本描述**来生成内容，而不是通过参考图！

**当前代码的问题：**
```python
kwargs: Dict[str, Any] = dict(
    model=model_id,
    prompt=prompt_text,
    api_key=api_key,
    base_image_url=person_url,      # ✅ 人物图
    ref_img=garment_url,             # ❌ 不支持！
    images=[person_url, garment_url],# ❌ 不支持！
    function="description_edit_with_mask",
    mask_image_url=mask_url,         # ✅ mask图
)
```

`description_edit_with_mask` 会忽略 `ref_img` 参数，只根据 `prompt` 文本描述来生成内容。

## 已完成的修复

### 修复1：移除错误的降级逻辑 ✅

```python
# ── DashScope API 调用 ──
resp = _call_dashscope(
    model_id=model_id,
    function_name=function_name,
    prompt_text=prompt_text,
    api_key=api_key,
    person_url=person_url,
    garment_url=garment_url,
    mask_url=mask_url,
)

# 如果失败，直接返回错误，不要降级到 stylization_all
if resp is None:
    return {
        "result_image": None,
        "status": "error",
        "message": "百炼调用返回 None",
        ...
    }
```

### 修复2：改进prompt，强调保持原始颜色 ✅

```python
def _build_prompt(bucket: str, user_prompt: str) -> str:
    hints = {
        "top": (
            "严格按照参考图中服装的颜色、图案、材质、款式，"
            "将 mask 白色区域内的上装替换为参考图中的服装；"
            "必须保持底图人物的脸部身份、发型、表情、姿势、相机视角与背景完全不变；"
            "不要更换人物，不要更换场景，不要添加新道具，不要改变服装颜色，mask 区域以外保持原样。"
        ),
        ...
    }
```

### 修复3：添加详细的日志记录 ✅

```python
logger.info(
    "Bailian try-on: model=%s function=%s category_bucket=%s mask=%s prompt=%s",
    model_id,
    function_name,
    bucket,
    "yes" if mask_url else "no",
    prompt_text[:100] + "..." if len(prompt_text) > 100 else prompt_text,
)

logger.info(
    "DashScope API call: function=%s, has_mask=%s, has_ref_img=%s",
    function_name,
    mask_url is not None,
    garment_url is not None,
)
```

## 根本解决方案

由于百炼API的 `description_edit_with_mask` 不支持参考图，我们有以下几个选择：

### 方案A：使用专用VTON服务（推荐）

部署专用的虚拟试衣模型（如 OOTDiffusion 或 IDM-VTON）：

1. 这些模型专门为虚拟试衣设计
2. 支持参考图（商品图）
3. 能够保持人物身份和衣服颜色

**配置方法：**
```env
VTON_INFERENCE_URL=http://127.0.0.1:8011/v1/tryon
```

详见：`docs/VTON_INTEGRATION.md`

### 方案B：改进prompt描述（临时方案）

如果必须使用百炼API，需要在prompt中详细描述衣服的特征：

```python
# 从商品图中提取特征（颜色、款式等）
garment_description = extract_garment_features(garment_image)
# 例如："灰色圆领短袖T恤，简约设计，纯色无图案"

prompt = f"将mask区域的衣服替换为：{garment_description}"
```

但这种方案的效果不如专用VTON模型。

### 方案C：使用本地diffusers模型

启用本地的Stable Diffusion inpainting模型：

```env
TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true
```

但需要确保SD inpainting权重完整，否则可能生成无关图像。

## 推荐配置

### 生产环境（推荐）

```env
# 禁用百炼（因为不支持参考图）
DASHSCOPE_TRYON_ENABLED=false

# 使用专用VTON服务
VTON_INFERENCE_URL=http://your-vton-service:8011/v1/tryon

# 或者使用本地diffusers（需要GPU）
TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true
```

### 开发/测试环境

```env
# 使用方案A（pipeline A）的稳定模式
# 不使用replace模式，直接使用balanced或strict模式
```

## 测试验证

### 1. 检查日志

重启服务后，查看日志中的以下信息：

```
Bailian try-on: model=wanx2.1-imageedit function=description_edit_with_mask category_bucket=top mask=yes prompt=严格按照参考图中服装的颜色...
DashScope API call: function=description_edit_with_mask, has_mask=True, has_ref_img=True
```

### 2. 测试虚拟试衣

1. 上传人物照片和商品图
2. 选择"真实贴身"模式
3. 检查结果：
   - ✅ 人物的脸应该与原照片一致
   - ✅ 衣服颜色应该与商品图一致
   - ✅ 衣服款式应该与商品图一致

### 3. 如果仍然有问题

查看错误响应中的 `replace_debug` 字段：

```json
{
  "replace_debug": {
    "bailian": {
      "configured": true,
      "status": "error",
      "message": "...",
      "function": "description_edit_with_mask"
    }
  }
}
```

## 常见问题

### Q: 为什么百炼API不支持参考图？

A: `description_edit_with_mask` 是通用的图像编辑功能，设计用于根据文本描述进行局部修补，而不是专门的虚拟试衣功能。虚拟试衣需要专用的模型（如OOTDiffusion）。

### Q: 如何部署专用VTON服务？

A: 参考 `docs/VTON_INTEGRATION.md` 和 `vton_inference_service/README.md`。

### Q: 能否继续使用百炼API？

A: 可以，但效果会受限。建议：
1. 使用方案A（pipeline A）的balanced或strict模式
2. 或者部署专用VTON服务

### Q: 修复后还是有问题怎么办？

A:
1. 检查日志确认没有降级到 `stylization_all`
2. 确认使用的是 `description_edit_with_mask` 而不是 `stylization_all`
3. 考虑切换到专用VTON服务

## 技术细节

### 百炼API的function对比

| Function | 用途 | 支持参考图 | 保持身份 | 适合虚拟试衣 |
|----------|------|-----------|---------|-------------|
| `stylization_all` | 全局风格迁移 | ✅ | ❌ | ❌ |
| `description_edit` | 指令式编辑 | ❌ | ⚠️ | ❌ |
| `description_edit_with_mask` | 局部修补 | ❌ | ✅ | ⚠️ |

### 专用VTON模型对比

| 模型 | 效果 | 速度 | 部署难度 |
|------|------|------|---------|
| OOTDiffusion | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| IDM-VTON | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 百炼API | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

## 总结

1. ✅ **已修复**：移除了错误的降级到 `stylization_all` 的逻辑
2. ✅ **已改进**：增强了prompt，强调保持原始颜色和身份
3. ✅ **已添加**：详细的日志记录，便于调试
4. ⚠️ **限制**：百炼API的 `description_edit_with_mask` 不支持参考图
5. 💡 **推荐**：使用专用VTON服务（OOTDiffusion或IDM-VTON）获得最佳效果

---

**修复时间**: 2026-04-22
**状态**: ✅ 代码已修复，建议部署专用VTON服务
