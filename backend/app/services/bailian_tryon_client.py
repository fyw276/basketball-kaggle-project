"""
Virtual try-on via Alibaba Cloud Model Studio (DashScope) — e.g. wanx2.1-imageedit.

Uses reference image + base image (see DashScope ImageSynthesis docs). Not a dedicated
VTON checkpoint; quality depends on the chosen model and function.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from typing import Any, Dict, Optional

import httpx
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy imports so local dev without dashscope still starts
try:
    from dashscope.aigc.image_synthesis import ImageSynthesis
    from dashscope.common.constants import TaskStatus
except ImportError:  # pragma: no cover
    ImageSynthesis = None  # type: ignore[misc, assignment]
    TaskStatus = None  # type: ignore[misc, assignment]


def _category_bucket(garment_category: Optional[str]) -> str:
    s = (garment_category or "").strip().lower()
    if any(k in s for k in ("裙", "连衣裙", "半裙", "skirt", "dress")):
        return "skirt"
    if any(k in s for k in ("下装", "裤", "裤装", "bottom", "pants", "jeans", "短裤")):
        return "bottom"
    if any(k in s for k in ("上装", "上衣", "外套", "top", "shirt", "coat", "t恤", "毛衣")):
        return "top"
    return "default"


def _resolve_model_id(bucket: str) -> str:
    default = (
        getattr(settings, "DASHSCOPE_TRYON_MODEL", None) or ""
    ).strip() or "wanx2.1-imageedit"
    if bucket == "top":
        v = (getattr(settings, "DASHSCOPE_TRYON_MODEL_TOP", None) or "").strip()
        return v or default
    if bucket == "bottom":
        v = (getattr(settings, "DASHSCOPE_TRYON_MODEL_BOTTOM", None) or "").strip()
        return v or default
    if bucket == "skirt":
        v = (getattr(settings, "DASHSCOPE_TRYON_MODEL_SKIRT", None) or "").strip()
        return v or default
    return default


def _build_prompt(bucket: str, user_prompt: str) -> str:
    hints = {
        "top": "将参考图中的上装真实穿在人物上半身，保持脸部、发型与背景自然协调。",
        "bottom": "将参考图中的下装真实穿在人物下半身，保持上半身与背景自然协调。",
        "skirt": "将参考图中的裙装真实穿在人物身上，保持人物姿态与背景自然协调。",
        "default": "将参考图中的服装真实穿在人物身上，保持人物姿态与背景自然协调。",
    }
    base = hints.get(bucket, hints["default"])
    u = (user_prompt or "").strip()
    if u:
        return f"{base} {u}"
    return base


def _bailian_configured() -> bool:
    if not getattr(settings, "DASHSCOPE_TRYON_ENABLED", False):
        return False
    key = (getattr(settings, "DASHSCOPE_API_KEY", None) or "").strip()
    return bool(key)


def _call_bailian_tryon_sync(
    *,
    garment_bytes: bytes,
    person_bytes: bytes,
    prompt: str,
    garment_category: Optional[str],
) -> Dict[str, Any]:
    if ImageSynthesis is None or TaskStatus is None:
        return {
            "result_image": None,
            "status": "error",
            "message": "dashscope 未安装，请 pip install dashscope",
            "metadata": {"reason": "dashscope_missing"},
        }

    api_key = (settings.DASHSCOPE_API_KEY or "").strip()
    bucket = _category_bucket(garment_category)
    model_id = _resolve_model_id(bucket)
    prompt_text = _build_prompt(bucket, prompt)
    function_name = (
        getattr(settings, "DASHSCOPE_TRYON_FUNCTION", None) or ""
    ).strip() or "stylization_all"

    tmp_g: Optional[str] = None
    tmp_p: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fg:
            fg.write(garment_bytes)
            tmp_g = fg.name
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fp:
            fp.write(person_bytes)
            tmp_p = fp.name

        logger.info(
            "Bailian try-on: model=%s function=%s category_bucket=%s",
            model_id,
            function_name,
            bucket,
        )

        resp = ImageSynthesis.call(
            model=model_id,
            prompt=prompt_text,
            api_key=api_key,
            base_image_url=tmp_p,
            ref_img=tmp_g,
            function=function_name,
        )

        if resp.status_code != 200:
            msg = (resp.message or resp.code or "DashScope error").strip()
            return {
                "result_image": None,
                "status": "error",
                "message": msg or "百炼试衣调用失败",
                "metadata": {
                    "reason": "dashscope_http",
                    "code": getattr(resp, "code", None),
                    "model": model_id,
                },
            }

        out = resp.output
        if out is None:
            return {
                "result_image": None,
                "status": "error",
                "message": "百炼返回空输出",
                "metadata": {"reason": "dashscope_empty_output", "model": model_id},
            }

        task_status = getattr(out, "task_status", None) or (
            out.get("task_status") if isinstance(out, dict) else None
        )
        if task_status != TaskStatus.SUCCEEDED:
            return {
                "result_image": None,
                "status": "error",
                "message": f"百炼任务未成功: {task_status}",
                "metadata": {
                    "reason": "dashscope_task",
                    "task_status": task_status,
                    "model": model_id,
                },
            }

        results = getattr(out, "results", None)
        if results is None and isinstance(out, dict):
            results = out.get("results")
        if not results:
            return {
                "result_image": None,
                "status": "error",
                "message": "百炼未返回图片结果",
                "metadata": {"reason": "dashscope_no_results", "model": model_id},
            }

        first = results[0]
        url = getattr(first, "url", None) or (first.get("url") if isinstance(first, dict) else None)
        if not url:
            return {
                "result_image": None,
                "status": "error",
                "message": "百炼结果缺少图片 URL",
                "metadata": {"reason": "dashscope_no_url", "model": model_id},
            }

        timeout = float(getattr(settings, "DASHSCOPE_TRYON_DOWNLOAD_TIMEOUT_SECONDS", 120) or 120)
        with httpx.Client(timeout=timeout) as client:
            r = client.get(str(url))
            r.raise_for_status()
            raw = r.content

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        return {
            "result_image": img,
            "status": "success",
            "message": "百炼试衣完成",
            "metadata": {
                "model": model_id,
                "function": function_name,
                "category_bucket": bucket,
                "provider": "dashscope_bailian",
            },
        }
    except Exception as e:
        logger.exception("Bailian try-on failed: %s", e)
        return {
            "result_image": None,
            "status": "error",
            "message": str(e) or "百炼试衣异常",
            "metadata": {"reason": "dashscope_exception"},
        }
    finally:
        for path in (tmp_g, tmp_p):
            if path and os.path.isfile(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


async def call_bailian_tryon(
    *,
    garment_bytes: bytes,
    person_bytes: bytes,
    prompt: str,
    garment_category: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Returns None if Bailian try-on is not enabled (caller uses remote/local).
    Otherwise returns the same dict shape as VirtualTryOnService.tryon_garment.
    """
    if not _bailian_configured():
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _call_bailian_tryon_sync(
            garment_bytes=garment_bytes,
            person_bytes=person_bytes,
            prompt=prompt,
            garment_category=garment_category,
        ),
    )
