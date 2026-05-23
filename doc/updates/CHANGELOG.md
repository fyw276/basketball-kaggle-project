# 更新日志

## 2026-05-24
### 新增
- Agent chat SSE 端点：`POST /api/v1/agent/chat-stream`，支持多轮工具调用、执行步骤流和最终回答流。
- Agent 技能 API：`/api/v1/agent/skills` 支持列表、创建、从工具调用序列 capture、execute-preview。
- 混合记忆检索：关键词 Jaccard + embedding cosine，embedding 不可用时自动回退关键词。
- Prometheus 指标：`GET /metrics` 输出 dependency、try-on v2、agent run/tool/failure 指标。
- Flutter Agent 页面、chunk-safe SSE parser、衣橱图片选择器。
- Try-on v2 fidelity guard、mask target-ratio 扩展工具、CatVTON 后端调试阶段落盘。

### 修复与同步
- 修正文档中的虚拟试衣 v2 模式数量，当前为 7 种：`strict`、`balanced`、`replace`、`realistic`、`realistic_v2`、`professional`、`hybrid`。
- 同步 README、backend README、mobile README、PROJECT_STATUS、DELIVERY_STATUS 与文档索引。
- 记录 `ENABLE_RATE_LIMIT=true` 默认行为和 `RATE_LIMIT_TRYON_PER_MINUTE` 试衣独立限流。

## 2026-05-13
### 修复
- **文档：虚拟试衣 v2 模式数量**：修正 README、VTON_INTEGRATION.md、SERVICE_MODULES_GUIDE.md、TRYON_TECH_BLUEPRINT_AB.md 中的模式数量从 6 种到 7 种（新增 `realistic_v2`）
- **文档：replace 模式引擎优先级**：修正所有相关文档中的引擎优先级描述，默认 `warp,bailian,remote,catvton,diffusion`（warp 优先运行以保证衣服像素保真）；`TRYON_V2_REPLACE_SKIP_WARP=true` 可跳过 warp
- **后端：相似度分析**：修复 `SimilarityDecision` 属性访问错误（`.group` 非 `.category`），添加 logger 导入，添加 `image_url` 空值时的路径推导兜底
- **后端：tryon v2 质量**：修复 `cv2` 导入作用域防止 `UnboundLocalError`，改进衣物预处理（形态学 CLOSE+DILATE、小 mask 自动扩展_bbox），修复后处理人脸保护 cascade，修复 Windows 中文用户名下 cascade 路径
- **Flutter：相似度界面**：修复图片 URL 构建逻辑（去除 `/api/v1` 前缀后拼接相对上传路径）

### 验证
- `pytest tests_lite tests/test_release_and_observability.py` — **87 passed**
- `flutter test --no-pub` — **11 passed**
### 新增
- Flutter 虚拟试衣界面新增 2 种模式：严格保真（strict）和混合模式（hybrid）
- Flutter API 客户端 `virtualTryonV2Garment` 新增 `debug_mode` 参数（`off`/`preprocess_only`/`full`）
- Flutter 默认试衣模式改为 hybrid（最佳：Warp保真 + CatVTON光影增强）
- 后端 v2 API 新增 `/api/v2/tryon/preprocess` 和 `/api/v2/tryon/preprocess-batch` 端点
- Try-On v2 文档（TRYON_TECH_BLUEPRINT_AB.md）更新至 2026-05-10 版本

### 验证
- CatVTON 端到端管线验证完成：推理耗时 ~15秒（steps=20, guidance=1.5）
- 完整管线测试通过：人物图 906x1382 + 衣服图 768x768，mask 生成、姿态检测、CatVTON 推理、后处理全部成功

### 修复
- 文档过时信息（API 端点、支持的模式列表、CatVTON 验证状态）
- **validate-input 422 崩溃**：`TryOnV2ValidateResponse.thresholds` 类型从 `dict[str, float]` 改为 `dict[str, float]` + 独立 `str` 字段（`recognized_tryon_category`、`recognized_raw_category`、`recognized_confidence`），不再混入字符串到数值字典
- **/garment mode 400 错误**：新增 `_MODE_FALLBACK` 映射字典，旧值自动转换（professional→detail_fidelity, hybrid/mixed→blend, fast/replace→stable_fast）
- **Flutter mode 枚举不一致**：`apiValue` 改为输出 `/garment` 端点接受的 `detail_fidelity|stable_fast`，新增 `validateApiValue` 输出 `/validate-input` 端点接受的 `professional|hybrid`
- **启动命令**：setup.md 补充禁止 `--reload` 的说明（CatVTON + CUDA 环境下热重载导致 CUDA context 销毁）

## 2026-05-09
### 新增
- 初始化 doc 文档体系
- 添加 .cursorrules 项目规则
- 创建 arch/ 和 architecture/ 双目录结构
