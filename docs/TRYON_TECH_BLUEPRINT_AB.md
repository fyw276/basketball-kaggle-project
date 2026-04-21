# 虚拟试衣技术蓝图（方案 A + 方案 B）

最后更新：2026-04-21
适用范围：下装（裤子/裙装）优先，目标是“保留本人身份，只替换服饰”。

## 0. 实施现状（截至 2026-04-21）

已落地（方案 A MVP + 客户端接入）：
- 后端 v2 API：`POST /api/v2/tryon/validate-input`、`POST /api/v2/tryon/pants`、`GET /api/v2/tryon/capabilities`。
- 输入门禁模块：`backend/app/services/tryon_v2/input_gate.py`（包含可解释失败码与分数）。
- 流水线模块：`backend/app/services/tryon_v2/pipeline_a.py`（门禁 -> 身份保护试衣 -> 统一结果）。
- 质量评估模块：`backend/app/services/tryon_v2/qc.py`（identity/boundary/occlusion + aggregate）。
- 配置项：`TRYON_BOTTOM_FORCE_FALLBACK` 与 `TRYON_V2_*` 阈值/开关。
- 移动端接入：预检面板、失败码可视化、action_hint 展示、v2 不可用自动回退 v1。
- CLI 接入：`--v2 --precheck-only --skip-precheck --mode --garment-category`。

当前验证状态：
- `tests/test_tryon_v2_api.py` 与 `tests/test_tryon_guards.py` 已稳定通过。
- `tests/test_tryon_v2_qc.py` 已覆盖方案 A 质量评分通过/失败分支。
- 预检失败码与错误 envelope 字段已在客户端解析并展示。

尚未落地：
- 方案 B（2.5D 深度遮挡增强）仍处于蓝图阶段。

## 1. 背景与目标

当前生成式链路容易出现“换人、换脸、换场景”。本蓝图将主链路切换为可控几何贴合：人体结构识别 + 服饰分段贴图 + 遮挡融合。

核心目标：
- 输入人像必须全身正面，腿部完整可见。
- 上传裤子图必须正面清晰，主体完整。
- 输出保持本人和原背景，仅替换为上传裤子。

非目标：
- 首期不做全 3D 数字人布料仿真。
- 生成式模型不作为主输出链路，仅可作为失败后的辅助增强候选。

## 2. 总体架构

推荐分层：
1. 输入门禁层（Input Gate）
2. 人体理解层（Pose + Parsing）
3. 服饰结构化层（Garment Structuring）
4. 几何贴合层（Warp）
5. 遮挡与融合层（Occlusion + Blend）
6. 质量评估层（QC）
7. 结果与可观测层（Result + Metrics）

## 3. 方案 A：2D 可控贴图主链路（优先落地）

### 3.1 适用场景

- 快速上线
- 强身份保持
- 可解释、可回归

### 3.2 模型选型建议

- 人体姿态：RTMPose 或 MoveNet
- 人体解析：SCHP / BiSeNet（拿到上衣、下装、腿、手臂、鞋等掩码）
- 人像分割：MODNet / PP-HumanSeg（边界补强）
- 服饰抠图：U2Net/rembg + 规则后处理
- 变形：分段仿射 + TPS（腰部、左裤腿、右裤腿）

### 3.3 核心算法流程

1. 输入门禁
- full_body_score：是否全身
- leg_visibility_score：腿部可见度
- front_pose_score：正面程度
- garment_front_score：裤子正面完整度

2. 人体结构提取
- 关键点：髋、膝、踝、裆
- 语义掩码：下装目标区域、手臂前景、鞋区等

3. 服饰结构化
- 将裤子分为腰区、左裤腿、右裤腿
- 构建局部控制点

4. 贴合变形
- 按关键点做分块 Warp
- 防止整图缩放导致穿帮

5. 遮挡融合
- 手臂、上衣下摆、包带等前景覆盖裤子
- 边界羽化 + 局部梯度融合（Poisson 可选）

6. 质控
- identity_preserve_score
- boundary_artifact_score
- occlusion_validity_score
- 不达阈值直接失败返回，不输出伪结果

### 3.4 工程收益

- 显著降低“换人图”概率
- 行为可预测，测试可覆盖
- 性能和资源成本可控

## 4. 方案 B：2.5D 混合增强链路（中期升级）

### 4.1 适用场景

在方案 A 稳定后，提升复杂姿态与遮挡真实感。

### 4.2 新增能力

- 单目深度估计（DPT/MiDaS 级）
- 轻量 3D 人体先验（SMPL-lite，仅用于姿态/深度一致性）
- 深度引导遮挡（depth-aware occlusion）

### 4.3 流程差异（相对 A）

- 保留 A 的输入门禁、结构化、分段 Warp。
- 在遮挡阶段引入深度顺序修正。
- 在 QC 增加 depth_consistency_score 与 occlusion_correctness_score。

### 4.4 预期提升

- 腿部弯曲和轻侧身时贴合更自然
- 前后景关系更稳定
- 在不走全 3D 的前提下接近高质量可视效果

## 5. 模块拆分（可直接开工）

建议新增目录：
- backend/app/services/tryon_v2/

建议文件：
- input_gate.py
- pose_parser.py
- garment_struct.py
- warp_engine.py
- occlusion_blend.py
- qc.py
- pipeline_a.py
- pipeline_b.py

API 层：
- backend/app/api/tryon_v2.py

建议路由：
- POST /api/v2/tryon/pants
- POST /api/v2/tryon/validate-input
- GET /api/v2/tryon/capabilities

## 6. 配置项设计（Settings）

建议新增：
- TRYON_V2_ENABLED=true|false
- TRYON_V2_PIPELINE=A|B
- TRYON_V2_STRICT_IDENTITY=true|false
- TRYON_V2_MIN_FULL_BODY_SCORE
- TRYON_V2_MIN_LEG_VISIBILITY
- TRYON_V2_MIN_GARMENT_FRONT_SCORE
- TRYON_V2_QC_THRESHOLD
- TRYON_V2_TIMEOUT_MS

## 7. 接口字段设计

### 7.1 请求：POST /api/v2/tryon/pants（multipart/form-data）

必填：
- person_file
- garment_file
- garment_category=bottom

可选：
- mode=strict|balanced
- debug=true|false

### 7.2 成功响应

- status=success
- result_image_url
- pipeline=A|B
- qc_scores
  - full_body_score
  - leg_visibility_score
  - identity_preserve_score
  - boundary_artifact_score
  - occlusion_correctness_score（B）
- metadata
  - latency_ms
  - model_versions

### 7.3 失败响应

保持统一 envelope，并包含：
- error_code
- message
- retryable
- action_hint

## 8. 失败码设计（建议）

- TRYON_V2_PERSON_NOT_FULL_BODY
- TRYON_V2_PERSON_LEG_NOT_VISIBLE
- TRYON_V2_PERSON_NOT_FRONT_VIEW
- TRYON_V2_GARMENT_NOT_FRONT_VIEW
- TRYON_V2_GARMENT_TOO_SMALL
- TRYON_V2_GARMENT_MULTI_OBJECT
- TRYON_V2_OCCLUSION_TOO_COMPLEX
- TRYON_V2_QC_NOT_PASSED
- TRYON_V2_INTERNAL_WARP_FAILED
- TRYON_V2_TIMEOUT

## 9. 里程碑排期（8 周）

M1（第 1-2 周）：方案 A MVP
- 完成输入门禁 + 姿态/解析 + 基础 Warp
- 打通 API 与前端串联
- 返回标准失败码

M2（第 3-4 周）：方案 A 质量版
- 遮挡融合优化
- QC 阈值体系
- 100+ 样例回归评测

M3（第 5-6 周）：方案 B 原型
- 深度估计接入
- depth-aware occlusion
- A/B 离线评估

M4（第 7-8 周）：方案 B 灰度
- 配置灰度开关
- 指标看板
- 难例闭环优化

## 10. 验收指标（建议）

- 身份一致性通过率 >= 95%
- 下装区域对齐可接受率 >= 90%
- 明显穿帮率 <= 5%
- 失败可解释率 = 100%
- 时延：
  - 方案 A：目标 <= 800ms（视部署资源）
  - 方案 B：目标 <= 1400ms

## 11. 测试与观测建议

测试层级：
1. 单元测试：门禁分数、失败码映射、Warp 几何稳定性
2. 集成测试：输入到输出 URL 与 envelope 字段
3. 视觉回归：固定样例集比对（结构分 + 人脸相似度 + 边界误差）

观测指标：
- tryon_v2_success_rate
- tryon_v2_failure_code_distribution
- tryon_v2_identity_drift_rate
- tryon_v2_latency_p50/p95

## 12. 风险与对策

风险：
- 用户上传图像质量波动大
- 复杂遮挡场景（包、外套下摆、坐姿）
- 不同设备色域/曝光差异

对策：
- 强门禁 + 明确 action_hint
- 低置信直接 fail-fast
- 逐步灰度发布并收敛阈值

## 13. 推荐实施顺序

1. 先上方案 A 主链路并切断下装走生成式主路径
2. 再上方案 B 的深度遮挡增强
3. 保留生成式为可选辅助，不作为默认主结果

---

本蓝图用于工程落地，不仅是模型选型说明。建议作为后续任务拆分、接口评审与里程碑跟踪的统一基线文档。
