"""
CatVTON client for backend — calls CatVTON-enabled VTON inference service.

This module integrates CatVTON into the backend's try-on v2 pipeline by calling
the VTON inference service (vton_inference_service/main.py) which supports CatVTON.

Usage in tryon_v2 API:
    from app.services.tryon_v2.catvton_client import call_catvton_vton
    result = await call_catvton_vton(garment_bytes, person_bytes, garment_category)
"""

from __future__ import annotations

import io
from typing import Any, Dict, Optional

import httpx
from PIL import Image

from app.core.config import settings


def _catvton_url_configured() -> bool:
    return bool(getattr(settings, "VTON_INFERENCE_URL", "") or "")


def _catvton_category_hint(garment_category: Optional[str]) -> str:
    """Map garment category string to CatVTON type."""
    s = (garment_category or "").strip().lower()
    if any(k in s for k in ("裙", "连衣裙", "dress")):
        return "overall"
    if any(k in s for k in ("下装", "裤", "裤装", "bottom", "短裤")):
        return "lower"
    if any(k in s for k in ("上装", "上衣", "外套", "top", "t恤", "毛衣")):
        return "upper"
    return "upper"


async def call_catvton_vton(
    *,
    garment_bytes: bytes,
    person_bytes: bytes,
    garment_category: Optional[str] = None,
    num_inference_steps: int = 50,
    guidance_scale: float = 2.5,
    seed: int = -1,
) -> Optional[Dict[str, Any]]:
    """
    Call CatVTON via the VTON inference service.

    Args:
        garment_bytes: JPEG bytes of the garment product image.
        person_bytes: JPEG bytes of the person full-body image.
        garment_category: Garment category string (e.g. "top", "上装", "bottom").
        num_inference_steps: Diffusion steps (default 50).
        guidance_scale: CFG strength (default 2.5).
        seed: Random seed (-1 = random).

    Returns:
        Dict with keys: result_image (PIL Image), status, message, metadata
        Returns None if VTON_INFERENCE_URL is not configured.
    """
    if not _catvton_url_configured():
        return None

    base = (getattr(settings, "VTON_INFERENCE_URL", "") or "").strip()
    timeout_s = float(getattr(settings, "VTON_INFERENCE_TIMEOUT_SECONDS", 600) or 600)
    api_key = (getattr(settings, "VTON_INFERENCE_API_KEY", "") or "").strip()

    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    catvton_type = _catvton_category_hint(garment_category)

    files = {
        "garment_file": ("garment.jpg", garment_bytes, "image/jpeg"),
        "person_file": ("person.jpg", person_bytes, "image/jpeg"),
    }
    data: Dict[str, Any] = {
        "model_gender": "neutral",
        "garment_category": garment_category or "",
        "prompt": "",
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
        "seed": seed,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(base, files=files, data=data, headers=headers)

        if resp.status_code >= 400:
            return {
                "result_image": None,
                "status": "error",
                "message": f"VTON service HTTP {resp.status_code}",
                "metadata": {"reason": "http_error", "status_code": resp.status_code},
            }

        ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ct in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            engine = resp.headers.get("X-VTON-Engine", "catvton")
            return {
                "result_image": img,
                "status": "success",
                "message": "CatVTON 试衣完成",
                "metadata": {
                    "model": "catvton",
                    "engine": engine,
                    "category": catvton_type,
                    "content_type": ct,
                },
            }

        return {
            "result_image": None,
            "status": "error",
            "message": "VTON service returned unexpected content type",
            "metadata": {"reason": "unexpected_content_type", "ct": ct},
        }

    except httpx.TimeoutException:
        return {
            "result_image": None,
            "status": "error",
            "message": "VTON 服务超时",
            "metadata": {"reason": "timeout", "timeout_s": timeout_s},
        }
    except Exception as e:
        return {
            "result_image": None,
            "status": "error",
            "message": f"VTON 服务调用失败: {e}",
            "metadata": {"reason": "exception", "error": str(e)},
        }
