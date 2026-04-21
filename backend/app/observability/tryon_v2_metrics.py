"""In-process observability metrics for try-on v2 pipeline A."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List

_lock = Lock()
_success_count = 0
_failure_count = 0
_failure_codes: Dict[str, int] = {}
_latencies_ms: List[int] = []
_MAX_LAT_SAMPLES = 5000


def reset_tryon_v2_metrics_for_tests() -> None:
    global _success_count, _failure_count
    with _lock:
        _success_count = 0
        _failure_count = 0
        _failure_codes.clear()
        _latencies_ms.clear()


def _append_latency(latency_ms: int) -> None:
    v = max(0, int(latency_ms))
    _latencies_ms.append(v)
    if len(_latencies_ms) > _MAX_LAT_SAMPLES:
        # Keep latest samples; avoids unbounded memory in long-running workers.
        del _latencies_ms[: len(_latencies_ms) - _MAX_LAT_SAMPLES]


def record_tryon_v2_success(latency_ms: int) -> None:
    global _success_count
    with _lock:
        _success_count += 1
        _append_latency(latency_ms)


def record_tryon_v2_failure(error_code: str | None, latency_ms: int) -> None:
    global _failure_count
    code = (error_code or "UNKNOWN").strip() or "UNKNOWN"
    with _lock:
        _failure_count += 1
        _failure_codes[code] = _failure_codes.get(code, 0) + 1
        _append_latency(latency_ms)


def _percentile(sorted_values: List[int], p: float) -> int | None:
    if not sorted_values:
        return None
    if p <= 0:
        return int(sorted_values[0])
    if p >= 1:
        return int(sorted_values[-1])
    idx = int(round((len(sorted_values) - 1) * p))
    return int(sorted_values[idx])


def snapshot_tryon_v2_metrics() -> Dict[str, Any]:
    with _lock:
        success = int(_success_count)
        failure = int(_failure_count)
        total = success + failure
        failure_codes = dict(_failure_codes)
        lats = list(_latencies_ms)

    rates: Dict[str, Any] = {
        "success_rate": round(success / total, 6) if total else None,
        "failure_rate": round(failure / total, 6) if total else None,
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
        "pipeline": "A",
        "counts": {
            "success": success,
            "failure": failure,
            "total": total,
        },
        **rates,
        "failure_code_distribution": failure_codes,
        "latency_ms": latency_block,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
