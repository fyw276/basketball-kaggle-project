# 2026-04-10 交付说明：智能穿搭 API 与前端体验闭环

## 变更目标

- 统一 API 响应结构，降低前后端联调成本。
- 强化智能穿搭推荐解释能力，输出稳定 JSON 结构。
- 打通首页到智能穿搭的体验闭环（天气、今日推荐、详情回跳、一键生成）。

## 后端变更

### 1. 响应 Envelope 统一

- 成功：`{ success: true, data, error: null, message: "ok" }`
- 失败：`{ success: false, data: null, error: { ... }, message }`

涉及：
- `backend/app/core/api_response.py`
- `backend/app/core/error_handlers.py`
- `backend/app/main.py`（`ApiEnvelopeMiddleware`）

### 2. 智能穿搭契约升级

- `POST /api/v1/smart-outfit/generate` 新增 `address` 请求字段。
- 响应新增 `address` 对象。
- 每套 `outfit` 新增 `ai_recommendation`：
  - `outfit`（string）
  - `style`（string）
  - `score`（0-100 number）
  - `reasons`（长度 3 的字符串数组）

涉及：
- `backend/app/api/smart_outfit.py`
- `backend/app/services/smart_outfit_generator.py`

### 3. AI 解释层策略

- 启用条件：`AI_RECOMMENDER_ENABLED=true` 且配置可用。
- 强制 JSON 解析：仅接受 `outfit/style/score/reasons`。
- 失败处理：解析失败/超时/未配置时 fallback，结构保持一致。
- 业务约束：空衣橱返回 400，不再给虚拟推荐。

配置：
- `AI_RECOMMENDER_ENABLED`
- `AI_RECOMMENDER_API_BASE_URL`
- `AI_RECOMMENDER_API_KEY`
- `AI_RECOMMENDER_MODEL`
- `AI_RECOMMENDER_TIMEOUT_MS`

### 4. 天气地址解析增强

- 增加高德逆地理（可选）并与 Open-Meteo / Nominatim 合并。
- 增加 `geocode_source` 与 `geocode_error` 便于排查。

涉及：
- `backend/app/services/weather_service.py`
- `backend/.env.example`（`AMAP_WEB_KEY`）

## Flutter 前端变更

### 1. 首页体验

- 新增城市/天气/温度卡片。
- 新增今日推荐卡：评分、风格、理由、缩略图。
- 新增骨架屏（呼吸动画）加载态。
- 支持按天失效推荐缓存。
- 查看详情支持“回到上次浏览搭配”。

涉及：
- `mobile/lib/features/home/screens/app_home_screen.dart`

### 2. 智能穿搭页体验

- 新增“一键生成穿搭”。
- 结果卡新增页码指示器与“当前”高亮。
- 记录并缓存当前浏览索引 `recommendation_index`。

涉及：
- `mobile/lib/features/analysis/screens/smart_outfit_screen.dart`

### 3. 图片失败占位

- `PlatformImage` 支持统一失败占位（含文案）。
- 若业务传入 `placeholder`，优先使用业务占位。

涉及：
- `mobile/lib/core/widgets/platform_image.dart`

## 文档同步

已同步：
- `backend/API_EXAMPLES.md`
- `backend/API_SPECIFICATION.md`
- `backend/API_CONTRACT_v1.0.md`
- `backend/README.md`
- `README.md`
- `mobile/README.md`
- `PROJECT_STATUS.md`

## 测试与门禁

执行项（与 hooks 对齐）：
- `pre-commit run --all-files`
- `flutter test --no-pub`（`mobile`）
- `python -m pytest tests_lite -v --tb=short -x`（`backend`）

说明：如某测试已过时，会先修正测试契约或删除无价值旧测，再保证门禁通过。
