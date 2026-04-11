# Hybrid Inference Fast Track

## 目标

在不牺牲稳定性的前提下，尽快把准确性拉升到可验证、可回滚、可放量的状态。

本方案采用双通道：

1. 本地模型主通道（默认）
2. 外部增强通道（仅在低置信度或异常时触发）

## 现有基础（已对齐当前代码）

1. 现有主推理入口：`backend/app/services/outfit_style_predict.py`
2. 当前 `/predict` 返回：`score`、`recommendations`、`explanation`
3. 配置入口：`backend/app/core/config.py`（可扩展新增开关和阈值）

## 一、决策层伪代码（可直接落到服务层）

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time


@dataclass
class HybridSettings:
    hybrid_enabled: bool = True
    external_enabled: bool = True
    low_conf_threshold: float = 0.62
    high_conf_threshold: float = 0.78
    margin_threshold: float = 0.08
    local_timeout_ms: int = 1200
    external_timeout_ms: int = 1800
    external_weight: float = 0.35
    local_weight: float = 0.65


def infer_with_hybrid(body: Dict[str, Any], cfg: HybridSettings) -> Dict[str, Any]:
    started = time.time()

    # 1) 本地主推理
    local = run_local_inference(body, timeout_ms=cfg.local_timeout_ms)
    # local 约定: {"label": str, "confidence": float, "top_k": List[dict], "version": str}

    # 2) 直出条件（高置信）
    if (not cfg.hybrid_enabled) or (local["confidence"] >= cfg.high_conf_threshold):
        return format_response(
            final_label=local["label"],
            final_confidence=local["confidence"],
            top_k=local["top_k"],
            source="local",
            fallback_reason=None,
            local_version=local.get("version", "unknown"),
            external_version=None,
            latency_ms=int((time.time() - started) * 1000),
        )

    # 3) 触发条件（低置信/小间隔/异常）
    trigger_low_conf = local["confidence"] < cfg.low_conf_threshold
    trigger_small_margin = top2_margin(local["top_k"]) < cfg.margin_threshold
    trigger_fallback = trigger_low_conf or trigger_small_margin

    if (not cfg.external_enabled) or (not trigger_fallback):
        return format_response(
            final_label=local["label"],
            final_confidence=local["confidence"],
            top_k=local["top_k"],
            source="local",
            fallback_reason=None,
            local_version=local.get("version", "unknown"),
            external_version=None,
            latency_ms=int((time.time() - started) * 1000),
        )

    # 4) 外部增强推理
    try:
        ext = run_external_inference(body, timeout_ms=cfg.external_timeout_ms)
        # ext 约定: {"label": str, "confidence": float, "top_k": List[dict], "version": str}

        fused = fuse_predictions(
            local_top_k=local["top_k"],
            external_top_k=ext["top_k"],
            local_weight=cfg.local_weight,
            external_weight=cfg.external_weight,
        )

        return format_response(
            final_label=fused[0]["label"],
            final_confidence=fused[0]["score"],
            top_k=fused,
            source="hybrid",
            fallback_reason=("low_confidence" if trigger_low_conf else "small_margin"),
            local_version=local.get("version", "unknown"),
            external_version=ext.get("version", "unknown"),
            latency_ms=int((time.time() - started) * 1000),
        )
    except Exception:
        # 5) 降级回本地，保证可用性
        return format_response(
            final_label=local["label"],
            final_confidence=local["confidence"],
            top_k=local["top_k"],
            source="local",
            fallback_reason="external_failed",
            local_version=local.get("version", "unknown"),
            external_version=None,
            latency_ms=int((time.time() - started) * 1000),
        )


def top2_margin(top_k: List[Dict[str, Any]]) -> float:
    if len(top_k) < 2:
        return 1.0
    return float(top_k[0]["score"]) - float(top_k[1]["score"])
```

## 二、配置项清单（建议直接加到 Settings）

建议在 `backend/app/core/config.py` 增加以下配置：

1. `HYBRID_INFERENCE_ENABLED: bool = True`
2. `EXTERNAL_ENHANCE_ENABLED: bool = True`
3. `LOW_CONF_THRESHOLD: float = 0.62`
4. `HIGH_CONF_THRESHOLD: float = 0.78`
5. `MARGIN_THRESHOLD: float = 0.08`
6. `LOCAL_INFER_TIMEOUT_MS: int = 1200`
7. `EXTERNAL_INFER_TIMEOUT_MS: int = 1800`
8. `LOCAL_WEIGHT: float = 0.65`
9. `EXTERNAL_WEIGHT: float = 0.35`
10. `EXTERNAL_API_BASE_URL: str = ""`
11. `EXTERNAL_API_KEY: str = ""`
12. `EXTERNAL_API_PATH: str = "/infer"`
13. `CIRCUIT_BREAKER_FAIL_THRESHOLD: int = 5`
14. `CIRCUIT_BREAKER_RESET_SECONDS: int = 300`

`.env` 示例：

```env
HYBRID_INFERENCE_ENABLED=True
EXTERNAL_ENHANCE_ENABLED=True
LOW_CONF_THRESHOLD=0.62
HIGH_CONF_THRESHOLD=0.78
MARGIN_THRESHOLD=0.08
LOCAL_INFER_TIMEOUT_MS=1200
EXTERNAL_INFER_TIMEOUT_MS=1800
LOCAL_WEIGHT=0.65
EXTERNAL_WEIGHT=0.35
EXTERNAL_API_BASE_URL=https://your-enhance-api.example.com
EXTERNAL_API_KEY=replace_me
EXTERNAL_API_PATH=/infer
CIRCUIT_BREAKER_FAIL_THRESHOLD=5
CIRCUIT_BREAKER_RESET_SECONDS=300
```

## 三、返回结构扩展（前端兼容优先）

在不破坏现有字段前提下，建议追加：

1. `source`: `local | hybrid | external`
2. `fallback_reason`: `low_confidence | small_margin | external_failed | null`
3. `model_version_local`
4. `model_version_external`
5. `latency_ms`

这样 Flutter 和 Web 不需要大改，只需可选展示增强信息。

## 三点五、外部增强接口最小契约（已在代码中兼容）

外部增强服务至少返回 `score`（推荐分）即可，支持以下三种响应形状：

1. 直接对象：`{"score": 7.8, "explanation": "...", "model_version": "v1"}`
2. 标准包裹：`{"success": true, "data": {"score": 7.8, ...}}`
3. result 包裹：`{"result": {"score": 7.8, ...}}`

分值尺度自动兼容：

1. `0~1` 会自动换算为 `0~10`
2. `0~10` 直接使用
3. `0~100` 会自动换算为 `0~10`

这意味着你可以先本地启动第三方项目，再通过网关/轻量适配层把响应整理成上面任一格式即可接入。

## 三点六、与外部开源项目的落地方式（不改主链路）

针对社区项目（如 `fashion-recommender` / `myntra-ai-virtual-tryon`）建议采用：

1. 保持本地模型为主通道（默认）
2. 将第三方服务作为增强通道（只在低置信度触发）
3. 若外部服务异常，自动降级回本地（现有逻辑已支持）

推荐配置示例：

```env
HYBRID_INFERENCE_ENABLED=True
EXTERNAL_ENHANCE_ENABLED=True
EXTERNAL_API_BASE_URL=http://127.0.0.1:9001
EXTERNAL_API_PATH=/infer
EXTERNAL_HEALTHCHECK_ENABLED=True
EXTERNAL_API_HEALTH_PATH=/health
```

## 四、30天速交付任务单（按周执行）

### Week 1（必须完成）

1. 新增 Hybrid 配置项并接入 Settings。
2. 在服务层实现决策函数（先不改现有输出字段，内部日志先通）。
3. 增加外部增强调用客户端（超时、一次重试、异常降级）。
4. 增加结构化日志字段：`source`、`fallback_reason`、`latency_ms`、`model_version`。

验收标准：

1. 本地正常请求保持原有成功率。
2. 人工构造低置信样例时，能够触发外部增强路径。
3. 外部超时时可自动降级回本地。

### Week 2（准确性验证）

1. 建立固定评估集（建议 200 到 500 条）。
2. 跑对比：本地单通道 vs 双通道（不同阈值组合）。
3. 输出指标：Top1、Top3、Macro F1、延迟 P95、回退率。

验收标准：

1. Top1 提升 >= 2%，或 Top3 提升 >= 3%。
2. P95 延迟增幅 <= 25%。

### Week 3（小流量灰度）

1. 按用户或请求哈希做 10% 灰度。
2. 监控每日错误率、回退率、外部失败率。
3. 若异常，开关一键回退到本地单通道。

验收标准：

1. 灰度期间错误率不高于基线。
2. 无阻断性事故。

### Week 4（放量与固化）

1. 放量到 30% 至 50%。
2. 通过门槛后全量。
3. 固化运行手册：阈值调整、熔断恢复、回滚流程。

验收标准：

1. 双通道成为默认策略。
2. 有明确回滚开关和操作说明。

## 五、今日最小可交付（Day 1）

若你今天只做最少改动，按下面顺序：

1. 加配置项：`HYBRID_INFERENCE_ENABLED`、`EXTERNAL_ENHANCE_ENABLED`、`LOW_CONF_THRESHOLD`。
2. 在预测服务里新增 `source` 与 `fallback_reason` 字段（默认 `local` 与 `null`）。
3. 仅实现低置信触发外部增强一条路径。
4. 把外部失败统一降级到本地并记录日志。

做到这一步，就已经具备可灰度、可观察、可回滚的基础能力。

## 六、风险与边界

1. 外部增强接口不稳定时，必须保证降级不影响主链路。
2. 不要在首轮引入复杂多模型投票，先跑通单一增强模型。
3. 阈值先保守，避免回退率过高导致成本和延迟失控。

## 七、建议责任分工

1. 后端：决策层、外部客户端、配置、日志。
2. 算法：评估集、阈值标定、误判分析。
3. 前端：可选展示 `source` 与置信度说明。
4. QA：回退链路、超时链路、一致性回归。
