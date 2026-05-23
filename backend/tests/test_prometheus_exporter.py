"""Tests for Prometheus metrics exporter."""

from app.observability.dependency_metrics import record_dependency_outcome, reset_metrics_for_tests
from app.observability.prometheus_exporter import render_prometheus_metrics
from app.observability.tryon_v2_metrics import (
    record_tryon_v2_failure,
    record_tryon_v2_success,
    reset_tryon_v2_metrics_for_tests,
)


class TestPrometheusExporter:
    def setup_method(self):
        reset_metrics_for_tests()
        reset_tryon_v2_metrics_for_tests()

    def teardown_method(self):
        reset_metrics_for_tests()
        reset_tryon_v2_metrics_for_tests()

    def test_output_contains_help_and_type(self):
        output = render_prometheus_metrics()
        assert "# HELP clothing_dependency_outcomes" in output
        assert "# TYPE clothing_dependency_outcomes counter" in output

    def test_dependency_metrics_appear(self):
        record_dependency_outcome("ai", "success")
        record_dependency_outcome("ai", "success")
        record_dependency_outcome("weather", "failure")
        output = render_prometheus_metrics()
        assert 'clothing_dependency_outcomes{domain="ai",outcome="success"} 2' in output
        assert 'clothing_dependency_outcomes{domain="weather",outcome="failure"} 1' in output

    def test_tryon_v2_metrics_appear(self):
        record_tryon_v2_success(150)
        record_tryon_v2_success(200)
        record_tryon_v2_failure("TIMEOUT", 300)
        output = render_prometheus_metrics()
        assert 'clothing_tryon_v2_outcomes{result="success"} 2' in output
        assert 'clothing_tryon_v2_outcomes{result="failure"} 1' in output
        assert "clothing_tryon_v2_latency_p50_ms" in output
        assert 'clothing_tryon_v2_failure_codes{code="TIMEOUT"} 1' in output

    def test_empty_metrics_still_valid(self):
        output = render_prometheus_metrics()
        assert "clothing_dependency_outcomes" in output
        assert "clothing_tryon_v2_outcomes" in output
        assert output.endswith("\n")
