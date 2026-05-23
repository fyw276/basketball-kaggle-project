"""Prometheus exposition-format exporter for existing in-process metrics.

Zero dependencies — renders the standard text-based exposition format that
Prometheus /metrics scrapers understand natively.  Reads from the existing
dependency_metrics and tryon_v2_metrics snapshots; does NOT duplicate storage.
"""

from __future__ import annotations

from typing import Dict

from app.observability.agent_metrics import snapshot_agent_metrics
from app.observability.dependency_metrics import snapshot_rates
from app.observability.tryon_v2_metrics import snapshot_tryon_v2_metrics


def _gauge(name: str, value: float, help_text: str = "") -> str:
    lines = []
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name} {value}")
    return "\n".join(lines)


def _counter_with_labels(name: str, labels: Dict[str, str], value: int, help_text: str = "") -> str:
    label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
    return f"{name}{{{label_str}}} {value}"


def render_prometheus_metrics() -> str:
    """Render all observability metrics in Prometheus exposition format."""
    sections = []

    # ── dependency_metrics ──
    dep = snapshot_rates()
    dep_help = (
        "# HELP clothing_dependency_outcomes Total outcomes by domain and result\n"
        "# TYPE clothing_dependency_outcomes counter"
    )
    dep_lines = [dep_help]
    for domain, row in dep.get("domains", {}).items():
        counts = row.get("counts", {})
        for outcome in ("success", "failure", "timeout", "degraded"):
            dep_lines.append(
                _counter_with_labels(
                    "clothing_dependency_outcomes",
                    {"domain": domain, "outcome": outcome},
                    counts.get(outcome, 0),
                )
            )
    sections.append("\n".join(dep_lines))

    # ── tryon_v2_metrics ──
    tv2 = snapshot_tryon_v2_metrics()
    tv2_counts = tv2.get("counts", {})
    tv2_help = (
        "# HELP clothing_tryon_v2_outcomes Try-on v2 pipeline outcomes\n"
        "# TYPE clothing_tryon_v2_outcomes counter"
    )
    tv2_lines = [tv2_help]
    tv2_lines.append(
        _counter_with_labels(
            "clothing_tryon_v2_outcomes", {"result": "success"}, tv2_counts.get("success", 0)
        )
    )
    tv2_lines.append(
        _counter_with_labels(
            "clothing_tryon_v2_outcomes", {"result": "failure"}, tv2_counts.get("failure", 0)
        )
    )

    # Latency gauges
    lat = tv2.get("latency_ms", {})
    if lat.get("count", 0) > 0:
        tv2_lines.append("")
        tv2_lines.append(
            _gauge("clothing_tryon_v2_latency_p50_ms", lat.get("p50", 0), "Try-on v2 p50 latency")
        )
        tv2_lines.append(
            _gauge("clothing_tryon_v2_latency_p95_ms", lat.get("p95", 0), "Try-on v2 p95 latency")
        )
        tv2_lines.append(
            _gauge("clothing_tryon_v2_latency_p99_ms", lat.get("p99", 0), "Try-on v2 p99 latency")
        )
        tv2_lines.append(
            _gauge("clothing_tryon_v2_latency_avg_ms", lat.get("avg", 0), "Try-on v2 avg latency")
        )

    # Failure code distribution
    for code, cnt in tv2.get("failure_code_distribution", {}).items():
        tv2_lines.append(
            _counter_with_labels("clothing_tryon_v2_failure_codes", {"code": code}, cnt)
        )
    sections.append("\n".join(tv2_lines))

    # ── agent_metrics ──
    ag = snapshot_agent_metrics()
    ag_lines: list[str] = []

    # Run outcomes
    ag_lines.append("# HELP agent_runs_total Total agent runs by outcome")
    ag_lines.append("# TYPE agent_runs_total counter")
    for outcome in ("success", "failure", "timeout"):
        ag_lines.append(
            _counter_with_labels(
                "agent_runs_total", {"outcome": outcome}, ag["runs"]["outcomes"].get(outcome, 0)
            )
        )

    # Total tool calls
    ag_lines.append("")
    ag_lines.append("# HELP agent_tool_calls_total Total tool calls across all agent runs")
    ag_lines.append("# TYPE agent_tool_calls_total counter")
    ag_lines.append(f'agent_tool_calls_total {ag["tool_calls"]["total"]}')

    # Per-tool outcomes
    ag_lines.append("")
    ag_lines.append("# HELP agent_tool_calls_by_tool Tool calls by tool name and outcome")
    ag_lines.append("# TYPE agent_tool_calls_by_tool counter")
    for tool_name, details in ag["tool_calls"].get("by_tool", {}).items():
        for outcome in ("success", "failure"):
            ag_lines.append(
                _counter_with_labels(
                    "agent_tool_calls_by_tool",
                    {"tool": tool_name, "outcome": outcome},
                    details.get(outcome, 0),
                )
            )

    # Tool latency
    lat = ag.get("tool_latency_ms", {})
    if lat.get("count", 0) > 0:
        ag_lines.append("")
        ag_lines.append("# HELP agent_tool_latency_ms Tool call latency percentiles")
        ag_lines.append("# TYPE agent_tool_latency_ms gauge")
        for q in ("p50", "p95", "p99"):
            v = lat.get(q)
            if v is not None:
                ag_lines.append(f'agent_tool_latency_ms{{quantile="{q}"}} {v}')

    # Failure reasons
    ag_lines.append("")
    ag_lines.append("# HELP agent_failures_total Agent failures by reason")
    ag_lines.append("# TYPE agent_failures_total counter")
    for reason, cnt in ag.get("failure_reasons", {}).items():
        ag_lines.append(_counter_with_labels("agent_failures_total", {"reason": reason}, cnt))

    sections.append("\n".join(ag_lines))

    return "\n\n".join(sections) + "\n"
