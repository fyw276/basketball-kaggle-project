# 模块迁移蓝图（StyleGuruAI + Smart-VTON 可复用能力）

## 1. 目标与边界

1. 保持现有 FastAPI + Flutter 主链路不变。
2. 采用“可插拔增强”策略，不替换已有可用功能。
3. 优先复用可验证的工程模式：两阶段推荐、LLM 严格 JSON、会员配额、支付验签、试衣容错。

## 2. 与现有代码的映射（先改已有文件）

1. 推荐主链路增强
- 读取并扩展 [backend/app/services/outfit_recommender_3d.py](backend/app/services/outfit_recommender_3d.py)
- 读取并扩展 [backend/app/services/smart_outfit_generator.py](backend/app/services/smart_outfit_generator.py)
- 读取并扩展 [backend/app/api/smart_outfit.py](backend/app/api/smart_outfit.py)

2. 试衣容错增强
- 读取并扩展 [backend/app/services/virtual_tryon.py](backend/app/services/virtual_tryon.py)
- 读取并扩展 [backend/app/api/tryon.py](backend/app/api/tryon.py)

3. 移动端接入层增强
- 读取并扩展 [mobile/lib/core/services/api_client.dart](mobile/lib/core/services/api_client.dart)
- 读取并扩展 [mobile/lib/features/analysis/screens/smart_outfit_screen.dart](mobile/lib/features/analysis/screens/smart_outfit_screen.dart)
- 读取并扩展 [mobile/lib/features/analysis/screens/virtual_tryon_screen.dart](mobile/lib/features/analysis/screens/virtual_tryon_screen.dart)

4. 回归与门禁
- 在 [backend/tests_lite](backend/tests_lite) 下新增 lite 测试（接口契约、降级分支、配额逻辑）

## 3. 新增模块（目录级）

1. 在 [backend/app/services](backend/app/services) 下新增：
- recommendation_rerank service（两阶段推荐）
- llm_style_explainer service（严格 JSON 输出）
- feature_quota service（会员/配额）
- payment gateway service（下单与验签）

2. 在 [backend/app/api](backend/app/api) 下新增：
- payment router
- subscription router
- usage router

3. 在 [mobile/lib/features/profile](mobile/lib/features/profile) 下新增：
- membership 状态页或入口组件（显示剩余额度、升级入口）

## 4. 关键能力设计

### 4.1 两阶段推荐（可直接落地）

1. Stage A：结构化预筛
- 条件：颜色、版型、场景、预算、性别表达。
- 目标：把候选集缩小到 20-100 条。

2. Stage B：语义重排
- 构造 profile text（体型/肤色/风格/场景/预算）。
- 对候选单品文本做 embedding。
- 余弦相似度排序，输出 top K。

3. 回退策略
- 候选空集时返回规则引擎默认组合，不抛 500。

### 4.2 LLM 严格 JSON（可插拔）

1. 输入
- 用户画像、天气摘要、衣橱摘要、候选组合。

2. 输出（固定 schema）
- outfit
- style
- score
- reasons[]
- warnings[]

3. 容错
- 解析失败时使用本地规则解释文本。
- 保证 API 响应字段始终齐全。

### 4.3 会员配额与支付

1. 配额模型
- free：每日/每月次数限制。
- pro：更高限额或不限。

2. 计费钩子
- 智能穿搭生成
- 虚拟试衣生成
- 高级分析（可选）

3. 支付验签
- 创建订单接口。
- 服务端验签接口（常量时间比较）。
- 验签成功后写 subscription 与有效期。

### 4.4 试衣容错增强

1. 外部推理失败分类
- quota
- cold start
- timeout
- upstream 5xx

2. 策略
- 限次重试。
- 明确错误码 + 用户友好文案。
- 回退到现有轻量合成链路。

## 5. API 草案（最小新增）

1. POST /api/v1/subscription/order
- 入参：tier
- 出参：order_id, amount, currency

2. POST /api/v1/subscription/verify
- 入参：order_id, payment_id, signature
- 出参：plan, valid_until

3. GET /api/v1/subscription/status
- 出参：plan, quota, usage

4. POST /api/v1/usage/consume
- 入参：action
- 出参：remaining, requires_upgrade

## 6. 接入顺序（按风险从低到高）

1. 第 1 批（低风险，1-2 天）
- 两阶段推荐服务 + 智能穿搭链路接入
- LLM 严格 JSON 解释器（失败自动回退本地解释）

2. 第 2 批（中风险，2-3 天）
- 试衣容错、超时与重试、统一错误码
- Flutter 提示与状态处理

3. 第 3 批（中高风险，3-5 天）
- 会员配额 + 支付闭环 + 订阅状态页

## 7. 最小改动上线方案（推荐）

1. 不改现有主接口字段，只新增可选字段。
2. 不替换已有推荐服务，只在服务层后置重排。
3. 不删除现有试衣逻辑，只在外部失败时回退本地链路。
4. 支付与会员先灰度到 10%-20% 用户。

## 8. 测试与验收

1. backend lite 测试新增
- recommendation rerank contract
- llm json fallback
- usage consume idempotency
- payment verify（成功/失败签名）

2. 端到端人工验收
- 登录 -> 衣橱 -> 智能穿搭 -> 试衣 -> 会员升级 -> 再次生成

3. 门禁
- pre-commit 全量
- pytest tests_lite
- flutter test --no-pub

## 9. 风险与规避

1. 大模型输出漂移
- 规避：强 schema + fallback。

2. 外部试衣服务不稳定
- 规避：分级错误码 + 重试 + 本地回退。

3. 支付争议
- 规避：服务端验签与账单日志留存。

## 10. 一句话实施策略

先把“推荐质量 + 解释稳定性”做稳，再上“配额与支付商业化”，全程保持现有功能可用与接口兼容。
