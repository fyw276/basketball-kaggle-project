# 虚拟试衣技术蓝图（方案 A + 方案 B + 扩展模式）

最后更新：2026-05-10
适用范围：下装（裤子/裙装）优先，目标是"保留本人身份，只替换服饰"。

## 0. 实施现状（截至 2026-05-10）

已落地（方案 A MVP + 扩展模式 + 客户端接入 + CatVTON 端到端验证）：

**基础管线（方案 A）**
- 后端 v2 API：`POST /api/v2/tryon/validate-input`、`POST /api/v2/tryon/garment`、`POST /api/v2/tryon/preprocess`、`GET /api/v2/tryon/capabilities`、`GET /api/v2/tryon/model-status`
- 输入门障模块：`backend/app/services/tryon_v2/input_gate.py`（包含可解释失败码与分数）
- 流水线模块：`backend/app/services/tryon_v2/pipeline_a.py`（门障 -> 身份保护试衣 -> 统一结果）
- 质量评估模块：`backend/app/services/tryon_v2/qc.py`（identity/boundary/occlusion + aggregate）
- Warp 引擎：`backend/app/services/tryon_v2/warp_engine.py`（分段仿射 + TPS，几何贴合保留身份）

**扩展模式（全部 7 种模式均已支持）**
- `strict` 模式：严格保真模式，几何贴图 + 严格QC校验，最保守/身份保持最强
- `balanced` 模式（对应 Flutter `stable`）：中等严格度，几何贴图 + 宽松QC
- `replace` 模式：融合 Warp / 百炼 / 远程 VTON / CatVTON / Diffusion 多引擎 AI 生成式合成
- `realistic` 模式：CatVTON 深度学习 + 边缘感知 + 光照匹配 + Poisson 融合
- `realistic_v2` 模式：CatVTON v2 增强版
- `professional` 模式：多步管线（分割 + 姿态 + 消除 + 贴合 + 光照 + 验证）
- `hybrid` 模式：Warp 保真（100%衣服图案/颜色）+ CatVTON 光影增强，饱和度感知 alpha 混合
- CatVTON 本地引擎：subprocess 调用 `vton_inference_service/catvton_runner.py`，MediaPipe PoseLandmarker
- 后处理流水线：边缘融合、颜色匹配、细节增强，去噪、接缝消除

**集成与客户端**
- 移动端接入：预检面板、失败码可视化、action_hint 展示、**2 种模式选择**（professional=细节保真 / hybrid=混合模式），默认 hybrid，v2 不可用自动回退 v1。`apiValue` 映射到 `/garment` 端点接受的 `detail_fidelity|stable_fast`；`validateApiValue` 映射到 `/validate-input` 端点接受的 `professional|hybrid`
- Flutter API 客户端：`virtualTryonV2Garment` 支持 `debug_mode` 参数（`off`/`preprocess_only`/`full`）
- CLI 接入：`--v2 --preprocess-only --skip-precheck --mode --garment-category`
- 配置项：`TRYON_BOTTOM_FORCE_FALLBACK`、`TRYON_V2_*` 阈值/开关、`CATVTON_*` 引擎参数

**CatVTON 端到端验证（2026-05-10 实测）**
- CatVTON subprocess 引擎验证完成：推理耗时 **~15 秒**（steps=20, guidance=1.5, VAE slicing 启用）
- 完整管线测试通过（`tryon_20260510_080729_175_1c80df`）：
  - 人物图：906x1382 RGB，上装（cloth_type=upper）
  - 衣服图：768x768，rembg 分割 + 33 个姿态关键点
  - CatVTON 推理：`inference_time_s=14.99`，`status=success`
  - 后处理：`repaint=true`，优化：`vae_slicing` + `flash_attention_fallback`
  - 输出：`09_result_raw.jpg`（CatVTON 原始）+ `10_result_final.jpg`（后处理结果）

**2026-05-10 修复**
- 修复 `validate-input` 422 错误：`TryOnV2ValidateResponse` 新增 `recognized_tryon_category: str`、`recognized_raw_category: str`、`recognized_confidence: float` 独立字段，`thresholds` 保持 `dict[str, float]` 纯数值类型
- 修复 `/garment` mode 枚举不一致：新增 `_MODE_FALLBACK` 映射，旧值自动转换（professional→detail_fidelity, hybrid/mixed→blend, fast/replace→stable_fast）
- 修复 Flutter 端 `apiValue` 映射：`professional` → `detail_fidelity`，`hybrid` → `stable_fast`
- 启动警告：CatVTON + CUDA 环境下禁止使用 `uvicorn --reload`，避免 CUDA context 销毁与显存碎片

**验证状态**
- `tests/test_tryon_v2_api.py` 与 `tests/test_tryon_guards.py` 已稳定通过
- `tests/test_tryon_v2_qc.py` 已覆盖方案 A 质量评分通过/失败分支
- `tests/test_tryon_v2_warp_engine.py` 已覆盖 Warp 引擎 identity 保护测试
- 预检失败码与错误 envelope 字段已在客户端解析并展示
- **CatVTON 端到端管线验证通过（2026-05-10 实测）**

**尚未落地**
- 方案 B（2.5D 深度遮挡增强）仍处于蓝图阶段

## 1. 背景与目标

当前生成式链路容易出现"换人、换脸、换场景"。本蓝图将主链路切换为可控几何贴合：人体结构识别 + 服饰分段贴图 + 遮挡融合。

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

- 显著降低"换人图"概率
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

实际路由：
- POST /api/v2/tryon/garment（主无线）
- POST /api/v2/tryon/pants（已废弃，向后兼容）
- POST /api/v2/tryon/validate-input
- POST /api/v2/tryon/preprocess（预处理：去背景白底 + 品类识别）
- POST /api/v2/tryon/preprocess-batch（批量预处理）
- GET /api/v2/tryon/capabilities
- GET /api/v2/tryon/model-status

## 6. 配置项设计（Settings）

实际配置项：
- TRYON_V2_ENABLED=true|false
- TRYON_V2_STRICT_IDENTITY=true|false
- TRYON_V2_MIN_FULL_BODY_SCORE
- TRYON_V2_MIN_LEG_VISIBILITY_SCORE
- TRYON_V2_QC_THRESHOLD
- TRYON_V2_TIMEOUT_MS
- TRYON_V2_AUTO_PREPROCESS=true|false
- CATVTON_ENABLED/CATVTON_PATH/CATVTON_WIDTH/CATVTON_HEIGHT/CATVTON_STEPS/CATVTON_GUIDANCE/CATVTON_REPAINT/CATVTON_TIMEOUT_SECONDS
- CATVTON_DEBUG_DIR=/path/to/debug/output（白盒调试输出目录）

## 7. 接口字段设计

### 7.1 请求：POST /api/v2/tryon/garment（multipart/form-data）

必填：
- garment_file
- person_file

可选：
- garment_image_url（已预处理的标准图 URL）
- garment_category=auto|top|bottom|skirt|outfit
- garment_file_2（第二件衣服，用于套装）
- garment_image_url_2
- garment_category_2=bottom|skirt
- prompt
- mode=detail_fidelity|blend|stable_fast（也接受旧值：strict→detail_fidelity, balanced→stable_fast, hybrid→blend, professional→detail_fidelity, replace→stable_fast，由后端 mode fallback 自动转换）
- model_gender=male|female|neutral
- debug_mode=off|preprocess_only|full

### 7.2 成功响应

- status=success
- result_image_url
- preview_white_url（白底预览图 URL，letterbox 保持比例）
- pipeline=A
- qc_scores
  - full_body_score
  - leg_visibility_score
  - identity_preserve_score
  - boundary_artifact_score
  - occlusion_validity_score
- metadata
  - latency_ms
  - engine（引擎标识：catvton, pants_warp_v2_pose, top_warp_v2_pose 等）
  - debug_session_dir（debug_mode != off 时返回）

### 7.3 失败响应

保持统一 envelope，并包含：
- error_code
- message
- retryable
- action_hint

## 8. 失败码设计

- TRYON_V2_PERSON_NOT_FULL_BODY
- TRYON_V2_PERSON_LEG_NOT_VISIBLE
- TRYON_V2_PERSON_NOT_FRONT_VIEW
- TRYON_V2_GARMENT_NOT_FRONT_VIEW
- TRYON_V2_GARMENT_TOO_SMALL
- TRYON_V2_GARMENT_MULTI_OBJECT
- TRYON_V2_GARMENT_CONTAINS_MODEL
- TRYON_V2_UNSUPPORTED_CATEGORY
- TRYON_V2_OCCLUSION_TOO_COMPLEX
- TRYON_V2_QC_NOT_PASSED
- TRYON_V2_INTERNAL_WARP_FAILED
- TRYON_V2_TIMEOUT
- TRYON_V2_DISABLED
- QUOTA_TRYON_EXCEEDED

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
