from app.observability.tryon_v2_metrics import (
    record_tryon_v2_failure,
    record_tryon_v2_success,
    reset_tryon_v2_metrics_for_tests,
    snapshot_tryon_v2_metrics,
)


def test_tryon_v2_metrics_rates_and_distribution():
    reset_tryon_v2_metrics_for_tests()

    record_tryon_v2_success(120)
    record_tryon_v2_success(140)
    record_tryon_v2_failure("TRYON_V2_QC_NOT_PASSED", 210)
    record_tryon_v2_failure("TRYON_V2_QC_NOT_PASSED", 220)
    record_tryon_v2_failure("TRYON_V2_INTERNAL_WARP_FAILED", 400)

    snap = snapshot_tryon_v2_metrics()

    assert snap["counts"]["total"] == 5
    assert snap["counts"]["success"] == 2
    assert snap["counts"]["failure"] == 3
    assert snap["success_rate"] == 0.4
    assert snap["failure_rate"] == 0.6

    dist = snap["failure_code_distribution"]
    assert dist["TRYON_V2_QC_NOT_PASSED"] == 2
    assert dist["TRYON_V2_INTERNAL_WARP_FAILED"] == 1

    lat = snap["latency_ms"]
    assert lat["count"] == 5
    assert lat["p50"] is not None
    assert lat["p95"] is not None
