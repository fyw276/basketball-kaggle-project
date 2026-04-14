"""Release artifact ledger: frontend index hash, backend commit, env snapshot (no secrets)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.core.config import Settings


def _read_manifest(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def build_release_ledger(settings: Settings) -> Dict[str, Any]:
    """Merge optional manifest JSON with env-backed Settings (env wins when set)."""
    manifest = _read_manifest((settings.RELEASE_MANIFEST_PATH or "").strip())
    front = (settings.RELEASE_FRONTEND_INDEX_SHA256 or "").strip() or str(
        manifest.get("frontend_index_sha256") or manifest.get("WEB_BUILD_SHA256") or ""
    ).strip()
    commit = (settings.RELEASE_BACKEND_GIT_COMMIT or "").strip() or str(
        manifest.get("backend_git_commit") or manifest.get("SOURCE_GIT_COMMIT") or ""
    ).strip()
    deploy_at = (settings.RELEASE_DEPLOY_TIME_UTC or "").strip() or str(
        manifest.get("deploy_time_utc") or manifest.get("DEPLOY_TIME_UTC") or ""
    ).strip()
    path_loaded = bool((settings.RELEASE_MANIFEST_PATH or "").strip()) and bool(manifest)
    return {
        "frontend_index_sha256": front,
        "backend_git_commit": commit,
        "deploy_time_utc": deploy_at,
        "manifest_path_configured": bool((settings.RELEASE_MANIFEST_PATH or "").strip()),
        "manifest_loaded": path_loaded,
    }


def build_env_snapshot(settings: Settings) -> Dict[str, Any]:
    """Non-secret configuration useful for correlating incidents (rotate keys separately)."""
    db_url = (settings.DATABASE_URL or "").strip()
    db_kind = "sqlite" if db_url.lower().startswith("sqlite") else "other"
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "database_kind": db_kind,
        "hybrid_inference_enabled": settings.HYBRID_INFERENCE_ENABLED,
        "external_enhance_enabled": settings.EXTERNAL_ENHANCE_ENABLED,
        "external_infer_timeout_ms": settings.EXTERNAL_INFER_TIMEOUT_MS,
        "local_infer_timeout_ms": settings.LOCAL_INFER_TIMEOUT_MS,
        "ai_recommender_enabled": settings.AI_RECOMMENDER_ENABLED,
        "ai_recommender_model": settings.AI_RECOMMENDER_MODEL,
        "ai_recommender_timeout_ms": settings.AI_RECOMMENDER_TIMEOUT_MS,
        "amap_web_configured": bool((settings.AMAP_WEB_KEY or "").strip()),
        "amap_weather_enabled": getattr(settings, "AMAP_WEATHER_ENABLED", False),
        "hf_endpoint_configured": bool((settings.HF_ENDPOINT or "").strip()),
        "hf_home_configured": bool((settings.HF_HOME or "").strip()),
        "enable_rate_limit": settings.ENABLE_RATE_LIMIT,
        "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
    }
