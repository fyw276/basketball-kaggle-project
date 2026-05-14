# Bugfix Requirements Document

## Introduction

当用户上传带有明显图案和颜色的衣服图（如卡通图案、彩色星星、印花、刺绣等）进行虚拟试衣时，最终生成的结果图中原始衣服的图案和颜色完全丢失，变成了纯色或灰色衣服。这个问题影响所有使用 `mode="detail_fidelity"` 或 `mode="blend"` 的虚拟试衣请求。

根本原因是 `backend/app/api/tryon_v2.py` 中的 `original_garment_image` 在 `_maybe_auto_preprocess` 函数调用之前保存，导致颜色保真函数 `catvton_color_fidelity_spatial` 使用的是带有背景的原始图片，而不是经过背景去除和标准化处理后的白底图片。这导致：
- 背景干扰了图案识别和颜色提取
- 图案检测分数偏低（pattern_score < 0.7）
- Warp 变形区域计算错误

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户上传带有明显图案（如卡通图案、印花、刺绣）的衣服图进行虚拟试衣 THEN 最终生成的结果图中原始衣服的图案完全丢失

1.2 WHEN 用户上传带有多种颜色（如彩色星星、渐变色、多色印花）的衣服图进行虚拟试衣 THEN 最终生成的结果图中原始衣服的颜色完全丢失，变成纯色或灰色

1.3 WHEN 颜色保真函数 `catvton_color_fidelity_spatial` 使用 `original_garment_image`（在 `_maybe_auto_preprocess` 之前保存的带背景原始图）THEN 图案检测分数偏低（pattern_score < 0.7），导致图案和颜色无法正确注入到最终结果

1.4 WHEN 颜色保真函数使用带有黑色或其他背景的原始图进行 warp 变形计算 THEN 变形区域计算错误，导致图案位置和尺寸不正确

### Expected Behavior (Correct)

2.1 WHEN 用户上传带有明显图案（如卡通图案、印花、刺绣）的衣服图进行虚拟试衣 THEN 最终生成的结果图 SHALL 完整保留原始衣服的图案形状、位置和清晰度

2.2 WHEN 用户上传带有多种颜色（如彩色星星、渐变色、多色印花）的衣服图进行虚拟试衣 THEN 最终生成的结果图 SHALL 完整保留原始衣服的所有颜色、色调和饱和度

2.3 WHEN 颜色保真函数 `catvton_color_fidelity_spatial` 使用 `original_garment_image` THEN 该变量 SHALL 包含经过 `_maybe_auto_preprocess` 处理后的白底标准化图片（768x768），以确保图案检测分数 >= 0.7

2.4 WHEN 颜色保真函数使用 `original_garment_image` 进行 warp 变形计算 THEN 变形区域计算 SHALL 基于正确的白底图片尺寸和内容，确保图案位置和尺寸准确

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 用户上传纯色衣服（无图案）进行虚拟试衣 THEN 系统 SHALL CONTINUE TO 正确保留衣服的纯色颜色

3.2 WHEN 用户上传衣服图进行虚拟试衣且 `mode` 不是 `"detail_fidelity"` 或 `"blend"` THEN 系统 SHALL CONTINUE TO 按照原有逻辑处理，不受此修复影响

3.3 WHEN `_maybe_auto_preprocess` 函数对衣服图进行背景去除和标准化处理 THEN 该函数 SHALL CONTINUE TO 返回 768x768 的白底标准化图片

3.4 WHEN 颜色保真函数 `catvton_color_fidelity_spatial` 应用 realism pass（褶皱和阴影效果）THEN 该功能 SHALL CONTINUE TO 正常工作

3.5 WHEN 系统生成 `preview_white` 预览图 THEN 该功能 SHALL CONTINUE TO 在 `_maybe_auto_preprocess` 之前使用原始 `garment_image` 生成预览

3.6 WHEN 用户上传第二件衣服图（`garment_image_2`）进行虚拟试衣 THEN 系统 SHALL CONTINUE TO 正确处理第二件衣服的图案和颜色保真
