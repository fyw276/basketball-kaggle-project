"""
Virtual try-on via Alibaba Cloud Model Studio (DashScope) — e.g. wanx2.1-imageedit.

Uses reference image + base image with clothing-region mask so the model only
edits the garment area and preserves the person's face/background unchanged.

Key fix vs. the original implementation:
- Previously used `stylization_all` (style transfer) which ignores identity → generates new person
- Now uses `description_edit_with_mask` with a MediaPipe-derived clothing mask so only the
  clothing area is edited, keeping face/pose/background intact
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
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
        "top": (
            "在保持底图人物的脸部身份、发型、表情、姿势、相机视角与背景完全不变的前提下，"
            "将 mask 白色区域内的上装替换为参考图中的服装；"
            "不要更换人物，不要更换场景，不要添加新道具，mask 区域以外保持原样。"
        ),
        "bottom": (
            "在保持底图人物的脸部身份、发型、表情、姿势、相机视角与背景完全不变的前提下，"
            "将 mask 白色区域内的下装替换为参考图中的服装；"
            "不要更换人物，不要更换场景，不要添加新道具，mask 区域以外保持原样。"
        ),
        "skirt": (
            "在保持底图人物的脸部身份、发型、表情、姿势、相机视角与背景完全不变的前提下，"
            "将 mask 白色区域内的裙装替换为参考图中的服装；"
            "不要更换人物，不要更换场景，不要添加新道具，mask 区域以外保持原样。"
        ),
        "default": (
            "在保持底图人物的脸部身份、发型、表情、姿势、相机视角与背景完全不变的前提下，"
            "将 mask 白色区域内的服装替换为参考图中的服装；"
            "不要更换人物，不要更换场景，不要添加新道具，mask 区域以外保持原样。"
        ),
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

    # 优先使用 description_edit_with_mask（基于 mask 的局部编辑，保留人物身份）
    # 若配置强制覆盖，则使用配置值
    configured_fn = (getattr(settings, "DASHSCOPE_TRYON_FUNCTION", None) or "").strip()
    # description_edit_with_mask 支持 mask，保持人物身份；stylization_all 是风格迁移（会生成新人）
    function_name = configured_fn if configured_fn else "description_edit_with_mask"

    try:

        def _jpeg_data_url(b: bytes) -> str:
            b64 = base64.b64encode(b).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"

        person_url = _jpeg_data_url(person_bytes)
        garment_url = _jpeg_data_url(garment_bytes)

        # ── 生成衣服区域 mask ────────────────────────────────────────────────
        # 用 MediaPipe 骨架关键点（或 fallback 比例估算）生成白色=编辑区域的 mask。
        # 这样 DashScope 只会修改衣服区域，不会改变脸部/背景，从根本上解决"生成新人"问题。
        mask_url: Optional[str] = None
        try:
            from app.services.tryon_v2.pose_utils import detect_pose_keypoints, make_clothing_mask

            person_img = Image.open(io.BytesIO(person_bytes)).convert("RGB")
            kpts = detect_pose_keypoints(person_img)
            # 对 outfit 同时覆盖上装+下装区域
            mask_cat = bucket if bucket in {"top", "bottom", "skirt"} else "outfit"
            mask_img = make_clothing_mask(person_img, kpts, mask_cat)

            # 把 mask 转为 JPEG base64 data URL
            mask_buf = io.BytesIO()
            mask_img.convert("RGB").save(mask_buf, format="JPEG", quality=90)
            mask_url = _jpeg_data_url(mask_buf.getvalue())
            logger.info(
                "Bailian try-on: generated clothing mask via %s (kpts=%s)",
                "MediaPipe" if kpts else "fallback",
                "yes" if kpts else "no",
            )
        except Exception as mask_err:
            logger.warning("Clothing mask generation failed, proceeding without mask: %s", mask_err)
            mask_url = None

        logger.info(
            "Bailian try-on: model=%s function=%s category_bucket=%s mask=%s",
            model_id,
            function_name,
            bucket,
            "yes" if mask_url else "no",
        )

        # ── DashScope API 调用（优先 mask-edit，fallback 至 stylization_all）──
        resp = _call_dashscope(
            model_id=model_id,
            function_name=function_name,
            prompt_text=prompt_text,
            api_key=api_key,
            person_url=person_url,
            garment_url=garment_url,
            mask_url=mask_url,
        )

        # 若 description_edit_with_mask 返回参数错误（DashScope SDK 版本不支持 mask_image_url），
        # 自动降级到 stylization_all（身份保真较差但仍可用）。
        if (
            resp is not None
            and resp.status_code != 200
            and function_name == "description_edit_with_mask"
            and mask_url is not None
        ):
            fallback_fn = "stylization_all"
            logger.warning(
                "description_edit_with_mask failed (code=%s msg=%s), retrying with %s",
                getattr(resp, "status_code", "?"),
                getattr(resp, "message", ""),
                fallback_fn,
            )
            resp = _call_dashscope(
                model_id=model_id,
                function_name=fallback_fn,
                prompt_text=prompt_text,
                api_key=api_key,
                person_url=person_url,
                garment_url=garment_url,
                mask_url=None,  # stylization_all 不需要 mask
            )

        if resp is None:
            return {
                "result_image": None,
                "status": "error",
                "message": "百炼调用返回 None",
                "metadata": {"reason": "dashscope_none_response"},
            }

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
                "inputs": "data_url_jpeg_base64",
                "mask_used": mask_url is not None,
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


def _call_dashscope(
    *,
    model_id: str,
    function_name: str,
    prompt_text: str,
    api_key: str,
    person_url: str,
    garment_url: str,
    mask_url: Optional[str],
) -> Any:
    """Thin wrapper around ImageSynthesis.call with optional mask_image_url support."""
    kwargs: Dict[str, Any] = dict(
        model=model_id,
        prompt=prompt_text,
        api_key=api_key,
        base_image_url=person_url,
        ref_img=garment_url,
        images=[person_url, garment_url],
        function=function_name,
    )
    if mask_url is not None:
        kwargs["mask_image_url"] = mask_url
    return ImageSynthesis.call(**kwargs)  # type: ignore[union-attr]


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
