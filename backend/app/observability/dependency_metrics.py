"""Rolling counters for external-ish dependencies (weather / try-on / AI / hybrid enhance).

Rates are computed over recorded outcomes since process start (or last reset in tests).
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Literal, Mapping

Outcome = Literal["success", "failure", "timeout", "degraded"]
Domain = Literal["weather", "tryon", "ai", "external_enhance"]

_OUTCOMES: tuple[str, ...] = ("success", "failure", "timeout", "degraded")
_lock = Lock()
_counts: Dict[str, Dict[str, int]] = {
    "weather": {k: 0 for k in _OUTCOMES},
    "tryon": {k: 0 for k in _OUTCOMES},
    "ai": {k: 0 for k in _OUTCOMES},
    "external_enhance": {k: 0 for k in _OUTCOMES},
}


def reset_metrics_for_tests() -> None:
    """Clear counters (pytest only)."""
    with _lock:
        for d in _counts.values():
            for k in _OUTCOMES:
                d[k] = 0


def record_dependency_outcome(domain: Domain, outcome: Outcome) -> None:
    if outcome not in _OUTCOMES:
        outcome = "failure"
    with _lock:
        bucket = _counts.setdefault(domain, {k: 0 for k in _OUTCOMES})
        bucket[outcome] = bucket.get(outcome, 0) + 1


def classify_external_exception(exc: BaseException) -> Outcome:
    """Map common client timeouts to ``timeout``; everything else ``failure``."""
    import asyncio

    import httpx

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    timeout_types: tuple[type, ...] = tuple(
        t
        for t in (
            getattr(httpx, "TimeoutException", None),
            getattr(httpx, "ReadTimeout", None),
            getattr(httpx, "ConnectTimeout", None),
            getattr(httpx, "WriteTimeout", None),
            getattr(httpx, "PoolTimeout", None),
        )
        if isinstance(t, type)
    )
    if timeout_types and isinstance(exc, timeout_types):
        return "timeout"
    return "failure"


def record_weather_success_payload(data: Mapping[str, Any]) -> None:
    """HTTP 200 weather body: degraded when geocode/address is fallback-quality."""
    from app.services.weather_service import is_weather_geocode_degraded

    if is_weather_geocode_degraded(dict(data)):
        record_dependency_outcome("weather", "degraded")
    else:
        record_dependency_outcome("weather", "success")


def record_weather_exception(exc: BaseException) -> None:
    record_dependency_outcome("weather", classify_external_exception(exc))


def snapshot_rates() -> Dict[str, Any]:
    with _lock:
        snap = {dom: dict(bucket) for dom, bucket in _counts.items()}
    domains: Dict[str, Any] = {}
    for dom, bucket in snap.items():
        total = sum(int(bucket.get(k, 0)) for k in _OUTCOMES)
        row: Dict[str, Any] = {
            "counts": {k: int(bucket.get(k, 0)) for k in _OUTCOMES},
            "total": total,
        }
        if total:
            for k in _OUTCOMES:
                row[f"{k}_rate"] = round(int(bucket.get(k, 0)) / total, 6)
        else:
            for k in _OUTCOMES:
                row[f"{k}_rate"] = None
        domains[dom] = row
    return {
        "domains": domains,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def render_dependency_board_html(extra_release_block: str = "") -> str:
    """Minimal self-contained page for internal ops (no auth; gate route with env)."""
    snap = snapshot_rates()
    rows = []
    for dom, row in snap["domains"].items():
        c = row["counts"]
        rows.append(
            "<tr>"
            f"<td><b>{html.escape(dom)}</b></td>"
            f"<td>{c['success']}</td>"
            f"<td>{c['failure']}</td>"
            f"<td>{c['timeout']}</td>"
            f"<td>{c['degraded']}</td>"
            f"<td>{row['total']}</td>"
            f"<td>{row.get('failure_rate')}</td>"
            f"<td>{row.get('timeout_rate')}</td>"
            f"<td>{row.get('degraded_rate')}</td>"
            "</tr>"
        )
    body = "\n".join(rows)
    rel = html.escape(extra_release_block or "(enable /release for JSON ledger)")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Dependency observability</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1a1a1a; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 960px; }}
    th, td {{ border: 1px solid #ccc; padding: 8px 10px; text-align: left; }}
    th {{ background: #f4f4f4; }}
    .muted {{ color: #555; font-size: 14px; margin-top: 24px; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>外部依赖观测（进程内累计）</h1>
  <p>成功 / 失败 / 超时 / 降级 计数与占比（自进程启动）。对接 Prometheus 时可由 sidecar 拉取 JSON 再转指标。</p>
  <table>
    <thead>
      <tr>
        <th>域</th><th>success</th><th>failure</th><th>timeout</th><th>degraded</th>
        <th>total</th><th>failure_rate</th><th>timeout_rate</th><th>degraded_rate</th>
      </tr>
    </thead>
    <tbody>
 {body}
    </tbody>
  </table>
  <div class="muted">Release台账摘要：{rel}</div>
</body>
</html>"""
