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
            "严格按照参考图中服装的精确颜色（RGB值不变）、图案纹理、材质光泽、领口袖口款式，将 mask 白色区域内的上装完整替换为参考图中的服装；"
            "必须保持底图人物的脸部身份（五官比例、肤色、发型）、发型、表情、姿势、相机视角与背景完全不变；"
            "不要更换人物身份，不要更换场景，不要添加新道具或装饰，不要改变服装颜色、图案或款式，mask 区域以外保持像素级不变。"
        ),
        "bottom": (
            "严格按照参考图中服装的精确颜色（RGB值不变）、图案纹理、材质光泽、裤型款式，将 mask 白色区域内的下装完整替换为参考图中的服装；"
            "必须保持底图人物的脸部身份（五官比例、肤色、发型）、发型、表情、姿势、相机视角与背景完全不变；"
            "不要更换人物身份，不要更换场景，不要添加新道具或装饰，不要改变服装颜色、图案或款式，mask 区域以外保持像素级不变。"
        ),
        "skirt": (
            "严格按照参考图中服装的精确颜色（RGB值不变）、图案纹理、材质光泽、裙型款式，将 mask 白色区域内的裙装完整替换为参考图中的服装；"
            "必须保持底图人物的脸部身份（五官比例、肤色、发型）、发型、表情、姿势、相机视角与背景完全不变；"
            "不要更换人物身份，不要更换场景，不要添加新道具或装饰，不要改变服装颜色、图案或款式，mask 区域以外保持像素级不变。"
        ),
        "default": (
            "严格按照参考图中服装的精确颜色（RGB值不变）、图案纹理、材质光泽、款式版型，将 mask 白色区域内的服装完整替换为参考图中的服装；"
            "必须保持底图人物的脸部身份（五官比例、肤色、发型）、发型、表情、姿势、相机视角与背景完全不变；"
            "不要更换人物身份，不要更换场景，不要添加新道具或装饰，不要改变服装颜色、图案或款式，mask 区域以外保持像素级不变。"
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
            "message": "dashscope 未安装",
            "metadata": {
                "reason": "dashscope_missing",
                "error_type": "dependency_missing",
                "action_required": "pip install dashscope",
            },
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
            mask_cat = bucket if bucket in {"top", "bottom", "skirt"} else "outfit"
            # feather_radius=5: 5px Gaussian feathering on mask edges reduces boundary artifacts
            mask_img = make_clothing_mask(person_img, kpts, mask_cat, feather_radius=5)

            mask_buf = io.BytesIO()
            mask_img.convert("RGB").save(mask_buf, format="JPEG", quality=90)
            mask_url = _jpeg_data_url(mask_buf.getvalue())
            logger.info(
                "Bailian try-on: generated clothing mask "
                "(kpts=%s, face_protected=yes, feather=5px)",
                "yes" if kpts else "no",
            )
        except Exception as mask_err:
            logger.warning("Clothing mask generation failed, proceeding without mask: %s", mask_err)
            mask_url = None

        logger.info(
            "Bailian try-on: model=%s function=%s category_bucket=%s mask=%s prompt=%s",
            model_id,
            function_name,
            bucket,
            "yes" if mask_url else "no",
            prompt_text[:100] + "..." if len(prompt_text) > 100 else prompt_text,
        )

        # ── DashScope API 调用 ──
        strength = float(getattr(settings, "DASHSCOPE_TRYON_STRENGTH", 0.25) or 0.25)
        strength = max(0.05, min(1.0, strength))  # clamp to valid range
        resp = _call_dashscope(
            model_id=model_id,
            function_name=function_name,
            prompt_text=prompt_text,
            api_key=api_key,
            person_url=person_url,
            garment_url=garment_url,
            mask_url=mask_url,
            strength=strength,
        )

        # 如果 description_edit_with_mask 失败，不要降级到 stylization_all
        # stylization_all 是风格迁移，会改变人物身份和衣服颜色
        if resp is None:
            return {
                "result_image": None,
                "status": "error",
                "message": "百炼调用返回 None",
                "metadata": {
                    "reason": "dashscope_none_response",
                    "error_type": "api_error",
                },
            }

        if resp.status_code != 200:
            msg = (resp.message or resp.code or "DashScope error").strip()
            code = getattr(resp, "code", None)
            # 根据错误代码提供更具体的诊断信息
            specific_hint = ""
            if code:
                code_str = str(code).lower()
                if "invalid" in code_str or "auth" in code_str or "key" in code_str:
                    specific_hint = "API key 无效或已过期"
                elif "quota" in code_str or "limit" in code_str:
                    specific_hint = "API 额度不足或超出限制"
                elif "permission" in code_str or "access" in code_str:
                    specific_hint = "模型权限不足或未开通"
                elif "timeout" in code_str or "network" in code_str:
                    specific_hint = "网络超时或连接失败"

            return {
                "result_image": None,
                "status": "error",
                "message": msg or "百炼试衣调用失败",
                "metadata": {
                    "reason": "dashscope_http",
                    "error_type": "api_error",
                    "code": code,
                    "status_code": resp.status_code,
                    "model": model_id,
                    "specific_hint": specific_hint,
                },
            }

        out = resp.output
        if out is None:
            return {
                "result_image": None,
                "status": "error",
                "message": "百炼返回空输出",
                "metadata": {
                    "reason": "dashscope_empty_output",
                    "model": model_id,
                    "function": function_name,
                },
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
                    "function": function_name,
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
                "metadata": {
                    "reason": "dashscope_no_results",
                    "model": model_id,
                    "function": function_name,
                },
            }

        first = results[0]
        url = getattr(first, "url", None) or (first.get("url") if isinstance(first, dict) else None)
        if not url:
            return {
                "result_image": None,
                "status": "error",
                "message": "百炼结果缺少图片 URL",
                "metadata": {
                    "reason": "dashscope_no_url",
                    "model": model_id,
                    "function": function_name,
                },
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
        # 捕获异常类型以提供更具体的诊断信息
        error_type = type(e).__name__
        error_msg = str(e) or "百炼试衣异常"

        specific_hint = ""
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            specific_hint = "网络超时"
        elif "connection" in error_msg.lower() or "network" in error_msg.lower():
            specific_hint = "网络连接失败"
        elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
            specific_hint = "SSL证书验证失败"
        elif "key" in error_msg.lower() or "auth" in error_msg.lower():
            specific_hint = "API认证失败"

        return {
            "result_image": None,
            "status": "error",
            "message": error_msg,
            "metadata": {
                "reason": "dashscope_exception",
                "error_type": error_type,
                "exception_message": error_msg,
                "specific_hint": specific_hint,
            },
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
    strength: float = 0.25,
) -> Any:
    """
    Thin wrapper around ImageSynthesis.call with optional mask_image_url support.

    CRITICAL: For virtual try-on, we MUST use description_edit_with_mask with mask_image_url.
    - base_image_url: person image (底图)
    - ref_img: garment image (参考图/商品图)
    - mask_image_url: clothing mask (白色=编辑区域，黑色=保留区域)
    - images: [person_url, garment_url] for reference
    - strength: diffusion strength (0.0-1.0). Lower = more faithful to original.

    DO NOT use stylization_all - it is style transfer and will change
    person identity and garment colors!
    """
    kwargs: Dict[str, Any] = dict(
        model=model_id,
        prompt=prompt_text,
        api_key=api_key,
        base_image_url=person_url,
        ref_img=garment_url,
        images=[person_url, garment_url],
        function=function_name,
    )
    # Only pass strength if using stylization_all (not description_edit_with_mask
    # which doesn't support it). DashScope uses its own internal denoising strength.
    if mask_url is not None:
        kwargs["mask_image_url"] = mask_url

    logger.info(
        "DashScope API call: function=%s, has_mask=%s, prompt_chars=%d",
        function_name,
        mask_url is not None,
        len(prompt_text),
    )

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
