"""Low-risk helper functions extracted from the large try-on v2 API module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import settings


_MODE_FALLBACK = {
    "detail": "detail_fidelity",
    "mixed": "hybrid",
    "fast": "stable_fast",
    "professional": "detail_fidelity",
    "realistic": "detail_fidelity",
    "realistic_v2": "detail_fidelity",
    "replace": "stable_fast",
    "strict": "detail_fidelity",
    "balanced": "hybrid",
}


def _normalize_tryon_mode(mode: str | None) -> str:
    """Map legacy/public mode aliases to the canonical v2 modes."""
    value = (mode or "").strip()
    return _MODE_FALLBACK.get(value, value)


def _make_tryon_error_detail(
    error_code: str,
    message: str,
    action_hint: str | None = None,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    """Return a structured HTTP error payload used across API endpoints."""
    return {
        "message": message,
        "error_code": error_code,
        "retryable": bool(retryable),
        "action_hint": action_hint,
    }


def _load_uploads_url(url: str | None, upload_dir: str | None = None) -> Image.Image | None:
    """Load a local /uploads/... image from the configured storage root."""
    u = (url or "").strip()
    if not u:
        return None

    low = u.lower()
    if "/uploads/" not in low:
        return None

    idx = low.find("/uploads/")
    tail = u[idx + len("/uploads/") :].lstrip("/").replace("\\", "/")
    if not tail:
        return None

    base_dir = (upload_dir or getattr(settings, "UPLOAD_DIR", "") or "").strip()
    if not base_dir:
        return None

    candidates: list[Path] = []
    root = Path(base_dir)
    candidates.append(root)
    candidates.append(root / "uploads")
    if root.name != "uploads":
        candidates.append(root.parent / "uploads")

    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        full = normalized / tail
        if full.is_file():
            try:
                return Image.open(full).convert("RGB")
            except Exception:
                return None

    return None
