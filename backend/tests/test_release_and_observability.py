"""Release ledger and dependency observability endpoints."""

import json
import os
import tempfile

from tests.api_json import unwrap_json


def test_release_endpoint(test_client):
    r = test_client.get("/release")
    assert r.status_code == 200
    data = unwrap_json(r)
    assert "ledger" in data
    assert "env_snapshot" in data
    assert "frontend_index_sha256" in data["ledger"]
    assert "backend_git_commit" in data["ledger"]


def test_release_manifest_file_overrides(test_client, monkeypatch):
    manifest = {
        "frontend_index_sha256": "abc123",
        "backend_git_commit": "deadbeef",
        "deploy_time_utc": "2026-04-13T00:00:00Z",
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        monkeypatch.setenv("RELEASE_MANIFEST_PATH", path)
        from app.core.config import Settings
        from app.core.release_info import build_release_ledger

        s = Settings()

        led = build_release_ledger(s)
        assert led["manifest_loaded"] is True
        assert led["frontend_index_sha256"] == "abc123"
        assert led["backend_git_commit"] == "deadbeef"
    finally:
        os.remove(path)


def test_dependency_observability_requires_auth(test_client):
    r = test_client.get("/api/v1/analytics/dependency-observability")
    assert r.status_code in (401, 403)


def test_dependency_observability_authenticated(test_client, auth_headers):
    from app.observability import dependency_metrics as dm

    dm.reset_metrics_for_tests()
    dm.record_dependency_outcome("weather", "success")
    dm.record_dependency_outcome("weather", "timeout")
    r = test_client.get(
        "/api/v1/analytics/dependency-observability",
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = unwrap_json(r)
    assert "domains" in data
    assert "external_enhance" in data["domains"]
    w = data["domains"]["weather"]
    assert w["counts"]["success"] == 1
    assert w["counts"]["timeout"] == 1
    assert w["total"] == 2
    dm.reset_metrics_for_tests()


def test_ops_board_disabled_by_default(test_client):
    r = test_client.get("/ops/dependency-board")
    assert r.status_code == 404


def test_external_enhance_metrics_degraded_when_unavailable():
    from app.observability import dependency_metrics as dm
    from app.services.external_enhance_client import (
        call_external_enhance,
        set_external_enhance_available,
    )

    dm.reset_metrics_for_tests()
    set_external_enhance_available(False, "probe_unhealthy")
    try:
        call_external_enhance({"top": "a", "bottom": "b"}, timeout_ms=1000)
    except RuntimeError:
        pass
    snap = dm.snapshot_rates()
    assert snap["domains"]["external_enhance"]["counts"]["degraded"] == 1
    assert snap["domains"]["external_enhance"]["total"] == 1
    dm.reset_metrics_for_tests()
    set_external_enhance_available(True, "ok")
