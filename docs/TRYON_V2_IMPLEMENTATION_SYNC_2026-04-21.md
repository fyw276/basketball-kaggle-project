# Try-On V2 文档同步说明（2026-04-21，**已由后续工作大幅扩展**）

> **2026-04-29 及 2026-05-02 更新**：本文件的同步范围（方案 A MVP）已被后续工作大幅扩展。详见新的同步说明或直接查看当前实现：
> - 完整 v2 模式说明：[`docs/TRYON_TECH_BLUEPRINT_AB.md`](TRYON_TECH_BLUEPRINT_AB.md) 的"实施现状"章节
> - 当前 try-on v2 API：[`backend/app/api/tryon_v2.py`](../backend/app/api/tryon_v2.py)
> - v2 引擎模块：[`backend/app/services/tryon_v2/`](<../backend/app/services/tryon_v2/>)

## 目标

本次同步用于完成三件事：
- 文档化已完成的方案 A 实施内容。
- 修复历史文档中不完整或过时信息。
- 确保配置、API、客户端行为、测试入口在文档中保持一致。

## 已同步内容

1. 主 README
- 新增并完善 v2 章节：接口、配置、CLI 示例。
- 明确移动端 `ApiClient` 虽默认 `baseUrl=/api/v1`，但 v2 方法会自动切到 `/api/v2`。

2. 后端环境样例
- 在 `backend/.env.example` 补齐 v2 配置：
  - `TRYON_BOTTOM_FORCE_FALLBACK`
  - `TRYON_V2_ENABLED`
  - `TRYON_V2_STRICT_IDENTITY`
  - `TRYON_V2_MIN_FULL_BODY_SCORE`
  - `TRYON_V2_MIN_LEG_VISIBILITY_SCORE`
  - `TRYON_V2_MIN_FRONT_POSE_SCORE`
  - `TRYON_V2_MIN_GARMENT_FRONT_SCORE`
  - `TRYON_V2_QC_THRESHOLD`
  - `TRYON_V2_TIMEOUT_MS`

3. 蓝图文档
- 在 `docs/TRYON_TECH_BLUEPRINT_AB.md` 增加“实施现状（截至 2026-04-21）”章节。
- 标记方案 A 已落地范围、验证状态、以及方案 B 仍属后续范围。

4. 移动端 README
- 更新更新时间。
- 将试衣能力描述升级为 v1+v2 双链路并说明“预检 -> 生成”。
- 增加 baseUrl 自动升级到 v2 的行为说明。

## 代码一致性修复（与文档同步）

在 `mobile/lib/core/services/api_client.dart` 中补充 v2 基址解析：
- 新增 `_resolveV2BaseUrl()`。
- `tryonV2ValidateInput()` 与 `virtualTryonV2Pants()` 改为调用 v2 基址。

这项修复避免了默认 `baseUrl=/api/v1` 时 v2 请求误打到 v1 路径的问题。

## 建议验收命令

```bash
# 后端 v2 + 守卫回归
cd backend
../.venv/Scripts/python.exe -m pytest tests/test_tryon_v2_api.py tests/test_tryon_guards.py -q

# 预提交检查
pre-commit run --all-files

# 预推送钩子（含 flutter 与 pytest-check）
pre-commit run --hook-stage pre-push --all-files
```

## 备注

本次同步仅覆盖“方案 A 已实施部分”的文档一致性，不改变方案 B 的蓝图目标。
