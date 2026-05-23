"""In-process observability metrics for the Agent chat loop.

Tracks run outcomes, per-tool call counts/latencies, and failure reasons.
Follows the same thread-safe counter pattern as tryon_v2_metrics.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List

_lock = Lock()

# ── Run-level counters ──
_run_outcomes: Dict[str, int] = {"success": 0, "failure": 0, "timeout": 0}

# ── Tool-level counters ──
_tool_calls_total: int = 0
_tool_outcomes: Dict[str, Dict[str, int]] = {}  # {tool_name: {"success": N, "failure": N}}
_tool_latencies_ms: List[int] = []
_MAX_LAT_SAMPLES = 5000

# ── Failure reasons ──
_failure_reasons: Dict[str, int] = {}  # {"timeout": N, "llm_error": N, ...}


def reset_agent_metrics_for_tests() -> None:
    """Clear all counters (pytest only)."""
    global _tool_calls_total
    with _lock:
        for k in _run_outcomes:
            _run_outcomes[k] = 0
        _tool_calls_total = 0
        _tool_outcomes.clear()
        _tool_latencies_ms.clear()
        _failure_reasons.clear()


def _append_latency(latency_ms: int) -> None:
    v = max(0, int(latency_ms))
    _tool_latencies_ms.append(v)
    if len(_tool_latencies_ms) > _MAX_LAT_SAMPLES:
        del _tool_latencies_ms[: len(_tool_latencies_ms) - _MAX_LAT_SAMPLES]


def record_agent_run(
    outcome: str,
    latency_ms: int,
    total_rounds: int = 0,
    total_tool_calls: int = 0,
    total_tokens: int = 0,
) -> None:
    """Record a completed agent run."""
    if outcome not in _run_outcomes:
        outcome = "failure"
    with _lock:
        _run_outcomes[outcome] = _run_outcomes.get(outcome, 0) + 1


def record_tool_call(tool_name: str, outcome: str, latency_ms: int) -> None:
    """Record a single tool call within an agent run."""
    global _tool_calls_total
    if outcome not in ("success", "failure"):
        outcome = "failure"
    with _lock:
        _tool_calls_total += 1
        bucket = _tool_outcomes.setdefault(tool_name, {"success": 0, "failure": 0})
        bucket[outcome] = bucket.get(outcome, 0) + 1
        _append_latency(max(0, int(latency_ms)))


def record_agent_failure(reason: str) -> None:
    """Record a failure reason (timeout, llm_error, token_budget, tool_limit, empty_response)."""
    reason = (reason or "unknown").strip() or "unknown"
    with _lock:
        _failure_reasons[reason] = _failure_reasons.get(reason, 0) + 1


def _percentile(sorted_values: List[int], p: float) -> int | None:
    if not sorted_values:
        return None
    if p <= 0:
        return int(sorted_values[0])
    if p >= 1:
        return int(sorted_values[-1])
    idx = int(round((len(sorted_values) - 1) * p))
    return int(sorted_values[idx])


def snapshot_agent_metrics() -> Dict[str, Any]:
    """Return a point-in-time snapshot of all agent metrics."""
    with _lock:
        run_outcomes = dict(_run_outcomes)
        tool_total = int(_tool_calls_total)
        tool_outcomes = {k: dict(v) for k, v in _tool_outcomes.items()}
        lats = list(_tool_latencies_ms)
        failure_reasons = dict(_failure_reasons)

    total_runs = sum(run_outcomes.values())
    rates = {}
    for k in ("success", "failure", "timeout"):
        rates[f"{k}_rate"] = round(run_outcomes[k] / total_runs, 6) if total_runs else None

    # Tool-level rates
    tool_details = {}
    for tool_name, bucket in tool_outcomes.items():
        t = sum(bucket.values())
        tool_details[tool_name] = {
            "success": bucket.get("success", 0),
            "failure": bucket.get("failure", 0),
            "total": t,
            "success_rate": round(bucket["success"] / t, 6) if t else None,
        }

    latency_block: Dict[str, Any]
    if lats:
        sl = sorted(lats)
        latency_block = {
            "count": len(sl),
            "min": int(sl[0]),
            "max": int(sl[-1]),
            "avg": round(sum(sl) / len(sl), 3),
            "p50": _percentile(sl, 0.50),
            "p95": _percentile(sl, 0.95),
            "p99": _percentile(sl, 0.99),
        }
    else:
        latency_block = {
            "count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "p50": None,
            "p95": None,
            "p99": None,
        }

    return {
        "runs": {
            "outcomes": run_outcomes,
            "total": total_runs,
            **rates,
        },
        "tool_calls": {
            "total": tool_total,
            "by_tool": tool_details,
        },
        "tool_latency_ms": latency_block,
        "failure_reasons": failure_reasons,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
