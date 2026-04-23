# Bugfix Requirements Document

## Introduction

虚拟试衣功能的"真实贴身"（replace模式）无法使用。用户在选择"真实贴身"效果模式时，系统返回错误提示上游服务不可用，即使百炼（DashScope）已正确配置（`DASHSCOPE_TRYON_ENABLED=true` 且 `DASHSCOPE_API_KEY` 已设置）。

该问题导致用户无法使用照片级真实感的虚拟试衣功能，影响用户体验。错误信息提示"替换试衣上游不可用或未成功（已禁止不稳定的本机 diffusion 兜底）"，但实际上百炼服务已配置且应该可用。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 用户选择 mode="replace" 且百炼服务已正确配置（`DASHSCOPE_TRYON_ENABLED=true` 且 `DASHSCOPE_API_KEY` 已设置）THEN 系统返回 HTTP 503 错误："替换试衣上游不可用或未成功（已禁止不稳定的本机 diffusion 兜底）"

1.2 WHEN 百炼 API 调用返回错误状态（status != "success" 或 result_image 为 None）THEN 系统直接判定为上游不可用，不提供详细的错误诊断信息

1.3 WHEN 百炼 API 调用失败且远程 VTON 未配置 THEN 系统提示配置远程 VTON，但未明确说明百炼失败的具体原因（如 API key 无效、额度不足、模型权限问题、网络错误等）

1.4 WHEN 百炼 API 返回错误 THEN 错误响应中的 `replace_debug.bailian` 字段可能为空或缺少关键诊断信息，导致用户无法定位问题根因

### Expected Behavior (Correct)

2.1 WHEN 用户选择 mode="replace" 且百炼服务已正确配置且 API 调用成功 THEN 系统 SHALL 返回成功的试衣结果图

2.2 WHEN 百炼 API 调用返回错误状态 THEN 系统 SHALL 在错误响应的 `replace_debug.bailian` 字段中包含详细的诊断信息（包括 API 返回的 status、message、reason、HTTP 状态码等）

2.3 WHEN 百炼 API 调用失败 THEN 系统 SHALL 在 action_hint 中明确说明百炼失败的具体原因（如"百炼 API key 无效"、"百炼额度不足"、"百炼模型权限不足"、"百炼网络超时"等），而不是泛泛提示"请检查 key/额度/模型权限/网络"

2.4 WHEN 百炼 API 调用因网络或超时失败 THEN 系统 SHALL 捕获异常并在 `replace_debug.bailian` 中记录异常类型和消息，帮助用户诊断网络或配置问题

2.5 WHEN 百炼 API 调用成功但返回的图片为 None THEN 系统 SHALL 在错误响应中明确说明"百炼返回成功但缺少结果图"，并记录在 `replace_debug.bailian` 中

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 用户选择 mode="strict" 或 mode="balanced" THEN 系统 SHALL CONTINUE TO 使用方案A（pipeline A）进行试衣，不受 replace 模式修复的影响

3.2 WHEN 百炼服务未配置（`DASHSCOPE_TRYON_ENABLED=false` 或 `DASHSCOPE_API_KEY` 未设置）THEN 系统 SHALL CONTINUE TO 尝试远程 VTON 或本地 diffusion（如果允许），行为与修复前一致

3.3 WHEN 百炼 API 调用失败且远程 VTON 配置可用 THEN 系统 SHALL CONTINUE TO 自动降级到远程 VTON，保持现有的降级逻辑

3.4 WHEN 百炼 API 调用失败且远程 VTON 也失败且 `TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true` THEN 系统 SHALL CONTINUE TO 降级到本地 diffusion，保持现有的兜底逻辑

3.5 WHEN 用户调用 `/tryon/validate-input` 且 mode="replace" THEN 系统 SHALL CONTINUE TO 跳过方案A门禁检查，返回 pass 状态

3.6 WHEN 百炼 API 调用成功返回结果图 THEN 系统 SHALL CONTINUE TO 保存结果图到存储服务并返回 result_image_url，行为与修复前一致
