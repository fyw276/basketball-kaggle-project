"""
Optional remote VTON (photo-realistic 2D try-on) inference.

When settings.VTON_INFERENCE_URL is set, POST /tryon/garment forwards to this URL
instead of running local virtual_tryon (SD inpainting + fallback).

Contract: see docs/VTON_INTEGRATION.md
"""

from __future__ import annotations

import base64
import io
from typing import Any, Dict, Optional

import httpx
from PIL import Image

from app.core.config import settings
from app.core.logging import setup_logging

logger = setup_logging()


def _remote_url_configured() -> bool:
    url = (getattr(settings, "VTON_INFERENCE_URL", None) or "").strip()
    return bool(url)


async def call_remote_vton(
    *,
    garment_bytes: bytes,
    person_bytes: bytes,
    prompt: str,
    model_gender: str,
    garment_category: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Returns same shape as VirtualTryOnService.tryon_garment:
      result_image (PIL or None), status, message, metadata

    Returns None if remote URL is not configured (caller uses local pipeline).
    Raises on HTTP/parse errors so tryon route can map to 502/503.
    """
    if not _remote_url_configured():
        return None

    base = (getattr(settings, "VTON_INFERENCE_URL", "") or "").strip()
    timeout_s = float(getattr(settings, "VTON_INFERENCE_TIMEOUT_SECONDS", 2400) or 2400)
    api_key = (getattr(settings, "VTON_INFERENCE_API_KEY", "") or "").strip()

    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }
    data = {
        "model_gender": model_gender,
        "garment_category": (garment_category or "").strip(),
        "prompt": (prompt or "").strip(),
    }

    logger.info("VTON remote inference: POST %s (timeout=%ss)", base, timeout_s)

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(base, files=files, data=data, headers=headers)

    ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()

    if resp.status_code >= 400:
        text = resp.text[:2000] if resp.text else ""
        raise RuntimeError(f"VTON remote HTTP {resp.status_code}: {text}")

    if ct in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        return {
            "result_image": img,
            "status": "success",
            "message": "远程 VTON 试衣完成",
            "metadata": {"model": "remote_vton", "content_type": ct},
        }

    # JSON body
    try:
        payload = resp.json()
    except Exception as e:
        raise RuntimeError(f"VTON remote: expected image or JSON, got {ct}: {e}") from e

    status = str(payload.get("status") or "error").lower()
    message = str(payload.get("message") or "remote VTON").strip()
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if not isinstance(meta, dict):
        meta = {}

    b64 = payload.get("result_image_base64") or payload.get("image_base64")
    if status == "error" or not b64:
        return {
            "result_image": None,
            "status": "error",
            "message": message or "远程试衣失败",
            "metadata": {**meta, "reason": "remote_error"},
        }

    try:
        raw = base64.b64decode(str(b64))
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise RuntimeError(f"VTON remote: invalid base64 image: {e}") from e

    out_status = status if status in ("success", "fallback") else "success"
    return {
        "result_image": img,
        "status": out_status,
        "message": message,
        "metadata": {**meta, "model": meta.get("model", "remote_vton")},
    }
