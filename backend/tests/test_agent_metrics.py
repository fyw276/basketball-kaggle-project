"""Tests for agent metrics recording, snapshot, Prometheus export, and AgentRun persistence."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.agent_run import AgentRun
from app.observability.agent_metrics import (
    record_agent_failure,
    record_agent_run,
    record_tool_call,
    reset_agent_metrics_for_tests,
    snapshot_agent_metrics,
)
from app.observability.prometheus_exporter import render_prometheus_metrics


@pytest.fixture(autouse=True)
def _clean_metrics():
    """Reset global counters before each test."""
    reset_agent_metrics_for_tests()
    yield
    reset_agent_metrics_for_tests()


# ── Record + Snapshot ─────────────────────────────────────────────────────────


class TestRecordAgentRun:
    def test_record_success(self):
        record_agent_run(
            "success", latency_ms=500, total_rounds=2, total_tool_calls=3, total_tokens=1000
        )
        snap = snapshot_agent_metrics()
        assert snap["runs"]["outcomes"]["success"] == 1
        assert snap["runs"]["total"] == 1

    def test_record_failure(self):
        record_agent_run("failure", latency_ms=200)
        snap = snapshot_agent_metrics()
        assert snap["runs"]["outcomes"]["failure"] == 1

    def test_record_timeout(self):
        record_agent_run("timeout", latency_ms=30000)
        snap = snapshot_agent_metrics()
        assert snap["runs"]["outcomes"]["timeout"] == 1

    def test_invalid_outcome_falls_back_to_failure(self):
        record_agent_run("bogus", latency_ms=100)
        snap = snapshot_agent_metrics()
        assert snap["runs"]["outcomes"]["failure"] == 1
        assert snap["runs"]["total"] == 1

    def test_multiple_runs_accumulate(self):
        record_agent_run("success", 100)
        record_agent_run("success", 200)
        record_agent_run("failure", 300)
        snap = snapshot_agent_metrics()
        assert snap["runs"]["outcomes"]["success"] == 2
        assert snap["runs"]["outcomes"]["failure"] == 1
        assert snap["runs"]["total"] == 3


class TestRecordToolCall:
    def test_single_tool_call(self):
        record_tool_call("get_weather", "success", 150)
        snap = snapshot_agent_metrics()
        assert snap["tool_calls"]["total"] == 1
        by_tool = snap["tool_calls"]["by_tool"]
        assert "get_weather" in by_tool
        assert by_tool["get_weather"]["success"] == 1
        assert by_tool["get_weather"]["failure"] == 0

    def test_tool_call_failure(self):
        record_tool_call("list_wardrobe", "failure", 50)
        snap = snapshot_agent_metrics()
        assert snap["tool_calls"]["by_tool"]["list_wardrobe"]["failure"] == 1

    def test_multiple_tools(self):
        record_tool_call("get_weather", "success", 100)
        record_tool_call("get_weather", "success", 120)
        record_tool_call("list_wardrobe", "failure", 80)
        snap = snapshot_agent_metrics()
        assert snap["tool_calls"]["total"] == 3
        assert snap["tool_calls"]["by_tool"]["get_weather"]["success"] == 2
        assert snap["tool_calls"]["by_tool"]["list_wardrobe"]["failure"] == 1

    def test_invalid_outcome_falls_back_to_failure(self):
        record_tool_call("mood_recommend", "timeout", 200)
        snap = snapshot_agent_metrics()
        assert snap["tool_calls"]["by_tool"]["mood_recommend"]["failure"] == 1


class TestRecordAgentFailure:
    def test_single_reason(self):
        record_agent_failure("timeout")
        snap = snapshot_agent_metrics()
        assert snap["failure_reasons"]["timeout"] == 1

    def test_multiple_reasons(self):
        record_agent_failure("llm_error")
        record_agent_failure("llm_error")
        record_agent_failure("token_budget")
        snap = snapshot_agent_metrics()
        assert snap["failure_reasons"]["llm_error"] == 2
        assert snap["failure_reasons"]["token_budget"] == 1

    def test_empty_reason_becomes_unknown(self):
        record_agent_failure("")
        snap = snapshot_agent_metrics()
        assert snap["failure_reasons"]["unknown"] == 1

    def test_none_reason_becomes_unknown(self):
        record_agent_failure(None)
        snap = snapshot_agent_metrics()
        assert snap["failure_reasons"]["unknown"] == 1


# ── Snapshot structure ─────────────────────────────────────────────────────────


class TestSnapshotStructure:
    def test_empty_snapshot_has_all_keys(self):
        snap = snapshot_agent_metrics()
        assert "runs" in snap
        assert "tool_calls" in snap
        assert "tool_latency_ms" in snap
        assert "failure_reasons" in snap
        assert "generated_at_utc" in snap

    def test_run_rates_when_empty(self):
        snap = snapshot_agent_metrics()
        assert snap["runs"]["success_rate"] is None
        assert snap["runs"]["failure_rate"] is None
        assert snap["runs"]["timeout_rate"] is None

    def test_run_rates_when_populated(self):
        record_agent_run("success", 100)
        record_agent_run("failure", 100)
        snap = snapshot_agent_metrics()
        assert snap["runs"]["success_rate"] == 0.5
        assert snap["runs"]["failure_rate"] == 0.5

    def test_latency_percentiles_when_empty(self):
        snap = snapshot_agent_metrics()
        lat = snap["tool_latency_ms"]
        assert lat["count"] == 0
        assert lat["p50"] is None
        assert lat["p95"] is None
        assert lat["p99"] is None

    def test_latency_percentiles_when_populated(self):
        for i in range(100):
            record_tool_call("test_tool", "success", i * 10)
        snap = snapshot_agent_metrics()
        lat = snap["tool_latency_ms"]
        assert lat["count"] == 100
        assert lat["min"] == 0
        assert lat["max"] == 990
        assert lat["p50"] is not None
        assert lat["p95"] is not None
        assert lat["p99"] is not None
        assert lat["p50"] <= lat["p95"] <= lat["p99"]


# ── Prometheus export ──────────────────────────────────────────────────────────


class TestPrometheusExport:
    def test_agent_runs_total_in_export(self):
        record_agent_run("success", 100)
        record_agent_run("failure", 200)
        output = render_prometheus_metrics()
        assert "agent_runs_total" in output
        assert 'outcome="success"' in output
        assert 'outcome="failure"' in output

    def test_agent_tool_calls_total_in_export(self):
        record_tool_call("get_weather", "success", 100)
        output = render_prometheus_metrics()
        assert "agent_tool_calls_total" in output

    def test_agent_tool_calls_by_tool_in_export(self):
        record_tool_call("get_weather", "success", 100)
        record_tool_call("list_wardrobe", "failure", 50)
        output = render_prometheus_metrics()
        assert "agent_tool_calls_by_tool" in output
        assert 'tool="get_weather"' in output
        assert 'tool="list_wardrobe"' in output

    def test_agent_failures_total_in_export(self):
        record_agent_failure("timeout")
        record_agent_failure("llm_error")
        output = render_prometheus_metrics()
        assert "agent_failures_total" in output
        assert 'reason="timeout"' in output
        assert 'reason="llm_error"' in output

    def test_agent_tool_latency_in_export(self):
        for i in range(10):
            record_tool_call("test_tool", "success", 100 + i)
        output = render_prometheus_metrics()
        assert "agent_tool_latency_ms" in output
        assert 'quantile="p50"' in output


# ── AgentRun DB persistence ────────────────────────────────────────────────────


class TestAgentRunPersistence:
    @pytest.fixture
    def db(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(bind=engine)
        session = factory()
        yield session
        session.close()

    def test_create_agent_run(self, db):
        run = AgentRun(
            run_id="abc123",
            user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            message="今天穿什么",
            outcome="success",
            total_rounds=2,
            total_tool_calls=3,
            total_tokens=1500,
            latency_ms=800,
            tool_calls_log=[
                {"tool_name": "get_weather", "outcome": "success", "latency_ms": 100},
                {"tool_name": "list_wardrobe", "outcome": "success", "latency_ms": 200},
            ],
        )
        db.add(run)
        db.commit()

        saved = db.query(AgentRun).filter_by(run_id="abc123").first()
        assert saved is not None
        assert saved.outcome == "success"
        assert saved.total_rounds == 2
        assert saved.total_tool_calls == 3
        assert saved.total_tokens == 1500
        assert saved.latency_ms == 800
        assert len(saved.tool_calls_log) == 2

    def test_agent_run_with_failure_reason(self, db):
        run = AgentRun(
            run_id="def456",
            user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            message="推荐穿搭",
            outcome="failure",
            failure_reason="llm_error",
        )
        db.add(run)
        db.commit()

        saved = db.query(AgentRun).filter_by(run_id="def456").first()
        assert saved.failure_reason == "llm_error"

    def test_agent_run_with_skill_id(self, db):
        run = AgentRun(
            run_id="ghi789",
            user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            message="查天气",
            outcome="success",
            skill_id="11111111-1111-1111-1111-111111111111",
        )
        db.add(run)
        db.commit()

        saved = db.query(AgentRun).filter_by(run_id="ghi789").first()
        assert saved.skill_id == "11111111-1111-1111-1111-111111111111"

    def test_agent_run_nullable_fields(self, db):
        run = AgentRun(
            run_id="min001",
            user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            message="hi",
            outcome="success",
        )
        db.add(run)
        db.commit()

        saved = db.query(AgentRun).filter_by(run_id="min001").first()
        assert saved.total_rounds == 0
        assert saved.total_tool_calls == 0
        assert saved.total_tokens == 0
        assert saved.latency_ms == 0
        assert saved.failure_reason is None
        assert saved.tool_calls_log is None
        assert saved.skill_id is None
