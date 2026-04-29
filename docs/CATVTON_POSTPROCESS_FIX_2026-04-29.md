# CatVTON 后处理修复总结 (2026-04-29)

## 问题描述

CatVTON 虚拟试衣完成后，后处理阶段出现尺寸不匹配错误：
- **CatVTON 输出尺寸**: 768×1024 (固定)
- **原始人物图尺寸**: 1236×1498 (用户上传)
- **后处理尝试**: 将 768×1024 的结果与 1236×1498 的原图混合
- **结果**: 后处理失败，虽然 CatVTON 推理成功，但输出质量不佳

## 根本原因

在 `backend/app/api/tryon_v2.py` 中，后处理函数 `enhance_tryon_result()` 需要原始人物图作为参考来进行边缘融合和色彩匹配。但当输入是 CatVTON 输出时，两者的尺寸不同，导致后处理逻辑出错。

## 修复方案

修改 `backend/app/api/tryon_v2.py` 中的后处理逻辑：

```python
# 检查是否是 CatVTON 输出（尺寸可能是 768x1024 或 512x512 等）
is_catvton_output = (
    result.get("metadata", {}).get("engine") == "catvton"
    or result.get("metadata", {}).get("model") == "catvton_local"
)

# CatVTON 输出尺寸可能与原始图片不同，需要特殊处理
if is_catvton_output and result_img.size != person_image.size:
    # CatVTON 输出：使用快速增强，避免与不同尺寸的原始图片混合
    from app.services.tryon_v2.postprocess import quick_enhance
    result_img = quick_enhance(result_img)
    logger.info(f"Post-processing: CatVTON output ({result_img.size}), using quick_enhance")
else:
    # 正常流程：完整后处理
    result_img = enhance_tryon_result(...)
```

## 修复文件

| 文件 | 修改内容 |
|------|----------|
| `backend/app/api/tryon_v2.py` | 添加 CatVTON 输出检测，使用 `quick_enhance()` 替代 `enhance_tryon_result()` |

## 相关文件

| 文件 | 说明 |
|------|------|
| `backend/app/api/tryon_v2.py` | Try-on v2 API，包含后处理调用 |
| `backend/app/services/tryon_v2/postprocess.py` | 包含 `quick_enhance()` 和 `enhance_tryon_result()` |
| `vton_inference_service/catvton_runner.py` | CatVTON 子进程推理，输出固定 768×1024 |
| `backend/app/services/tryon_v2/catvton_engine_client.py` | CatVTON 引擎客户端 |
| `scripts/diagnose_catvton.py` | CatVTON 诊断工具 |

## CatVTON 性能说明

CatVTON 在 8GB VRAM 环境下的推理时间：
- **每步约 35 秒**
- **默认 50 步** → 总计约 **29 分钟**
- 建议：根据实际需求调整 `CATVTON_STEPS`（可降至 20-30 步以加快速度）

## CatVTON 调试目录

调试输出保存在: `D:\models\catvton_debug\`

中间产物文件说明:
| 文件 | 说明 |
|------|------|
| `01_input_person.jpg` | 输入人物图 |
| `02_input_garment.jpg` | 输入衣物图 |
| `03_mask.png` | 生成的衣服区域遮罩 |
| `04_pose_keypoints.jpg` | OpenPose 骨骼关键点图 |
| `05_mask_overlay.png` | 遮罩叠加人物图（用于验证 mask 质量） |
| `06_person_resized.jpg` | 缩放后人物图 |
| `07_garment_resized.jpg` | 缩放后衣物图 |
| `08_mask_resized.jpg` | 缩放后遮罩 |
| `09_result_raw.jpg` | CatVTON 扩散输出（未重绘） |
| `10_result_final.jpg` | CatVTON 最终结果（已重绘） |

## 验证修复

修复后，日志应显示：
```
Post-processing: CatVTON output (768, 1024), using quick_enhance
Post-processing applied: strength=strong
```

而不是之前的尺寸不匹配错误。
