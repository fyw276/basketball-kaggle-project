"""Virtual try-on tool: virtual_try_on."""

from pathlib import Path
from typing import Any, Dict

from PIL import Image
from sqlalchemy.orm import Session

from app.agent.tools.registry import register_tool
from app.core.config import settings
from app.services.storage import get_storage_service


def _resolve_upload_path(image_url: str, user_id: str) -> Path | None:
    """Resolve a same-user /uploads/... URL or relative upload path to disk."""
    raw = (image_url or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        marker = "/uploads/"
        if marker not in raw:
            return None
        raw = raw.split(marker, 1)[1]
    elif raw.startswith("/uploads/"):
        raw = raw[len("/uploads/") :]
    raw = raw.lstrip("/\\")
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    candidate = (upload_root / raw).resolve()
    try:
        candidate.relative_to(upload_root)
    except ValueError:
        return None
    parts = candidate.relative_to(upload_root).parts
    if not parts or parts[0] != str(user_id):
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


@register_tool(
    name="virtual_try_on",
    description=(
        "使用用户已上传的服装图和人物图生成虚拟试衣结果。"
        "输入必须是当前用户 /uploads/ 下的图片 URL。"
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "garment_image_url": {
                "type": "string",
                "description": "当前用户已上传的服装图片 URL，例如 /uploads/<user>/<file>.jpg",
            },
            "person_image_url": {
                "type": "string",
                "description": "当前用户已上传的人物图片 URL，例如 /uploads/<user>/<file>.jpg",
            },
            "prompt": {
                "type": "string",
                "description": "可选试衣提示词",
                "default": "",
            },
            "model_gender": {
                "type": "string",
                "description": "male / female / neutral",
                "default": "neutral",
            },
        },
        "required": ["garment_image_url", "person_image_url"],
    },
    mcp_name="virtual_try_on",
    category="tryon",
)
async def virtual_try_on(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.services.virtual_tryon import get_tryon_service, sanitize_tryon_prompt

    garment_url = kw.get("garment_image_url", "")
    person_url = kw.get("person_image_url", "")
    garment_path = _resolve_upload_path(garment_url, user_id)
    person_path = _resolve_upload_path(person_url, user_id)
    if garment_path is None:
        return {"error": "garment_image_url must point to an existing current-user upload"}
    if person_path is None:
        return {"error": "person_image_url must point to an existing current-user upload"}

    model_gender = (kw.get("model_gender") or "neutral").strip().lower()
    if model_gender not in {"male", "female", "neutral"}:
        model_gender = "neutral"

    with Image.open(garment_path) as garment_img, Image.open(person_path) as person_img:
        result = get_tryon_service().tryon_garment(
            garment_image=garment_img.convert("RGB"),
            person_image=person_img.convert("RGB"),
            prompt=sanitize_tryon_prompt(kw.get("prompt") or ""),
            model_gender=model_gender,
        )

    out_img = result.get("result_image") if isinstance(result, dict) else None
    result_url = ""
    if out_img is not None:
        storage = get_storage_service()
        key = Path(str(garment_path)).stem[:16]
        relative_path = f"{user_id}/agent_tryon/result_{key}.jpg"
        import io

        buf = io.BytesIO()
        out_img.save(buf, format="JPEG", quality=92)
        _, result_url = storage._save_bytes(buf.getvalue(), relative_path)

    return {
        "status": result.get("status", "unknown") if isinstance(result, dict) else "unknown",
        "message": result.get("message", "") if isinstance(result, dict) else "",
        "result_image_url": result_url,
        "metadata": result.get("metadata", {}) if isinstance(result, dict) else {},
    }
