"""智能穿搭：天气 + 情绪 + 参考图，优先衣橱搭配。"""

import io
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.observability.dependency_metrics import (
    record_dependency_outcome,
    record_weather_exception,
    record_weather_success_payload,
)
from app.services.smart_outfit_generator import generate_smart_outfits, upload_reference_image
from app.services.subscription_billing import consume_usage
from app.services.weather_service import fetch_weather_by_city_name, fetch_weather_lat_lon

router = APIRouter(prefix="/smart-outfit", tags=["Smart Outfit"])


class SmartOutfitGenerateRequest(BaseModel):
    image_url: str = Field(..., description="参考衣物图片 URL（本账号 uploads 下）")
    location: str = Field("", description="完整定位地址（省市区街道），优先于 city")
    city: str = Field("", description="城市名或短地址（兼容旧字段）")
    address: Dict[str, str] = Field(
        default_factory=dict, description="结构化地址（province/city/district/street）"
    )
    weather: str = Field("", description="天气状况（晴/阴/雨等）")
    temperature: float = Field(20.0, description="气温 ℃")
    mood: str = Field("", max_length=120, description="情绪描述，可空")
    count: int = Field(3, ge=1, le=5, description="一次生成套数")
    regeneration_index: int = Field(0, ge=0, description="重新生成时递增，用于结果多样化")
    gender_expression: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="可选，覆盖画像中的性别表达指数（女）"
    )


class SmartOutfitGenerateResponse(BaseModel):
    outfits: List[Dict[str, Any]]
    city: str = ""
    address: Dict[str, str] = Field(default_factory=dict)
    weather: str = ""
    temperature: float = 20.0
    mood: str = ""
    message: str = "ok"
    weather_fallback: bool = False


@router.get("/weather")
async def get_weather_context(
    latitude: float = Query(..., description="纬度"),
    longitude: float = Query(..., description="经度"),
    current_user: User = Depends(get_current_user),
):
    """根据经纬度返回详细地址、气温、天气（逆地理与气象均基于经纬度，非 IP）。"""
    try:
        data = await fetch_weather_lat_lon(latitude, longitude)
        record_weather_success_payload(data)
        return {
            "city": data["city"],
            "address": {
                "province": data.get("province", ""),
                "city": data.get("addr_city", ""),
                "district": data.get("district", ""),
                "street": data.get("street", ""),
                "full_address": data.get("full_address", data.get("display_address", "")),
                "display_address": data.get("display_address", ""),
            },
            "latitude": data["latitude"],
            "longitude": data["longitude"],
            "temperature": data["temperature"],
            "weather": data["weather"],
            "weather_code": data["weather_code"],
            "geocode_source": data.get("geocode_source", ""),
            "geocode_error": data.get("geocode_error", ""),
            "weather_source": data.get("weather_source", "open_meteo"),
            "fallback": False,
        }
    except Exception as e:
        record_weather_exception(e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"weather unavailable: {e}",
        )


@router.get("/weather-by-city")
async def get_weather_by_city(
    name: str = Query(..., description="城市名，如 上海"),
    current_user: User = Depends(get_current_user),
):
    """按城市名查询天气（用于手动切换城市）。"""
    try:
        res = await fetch_weather_by_city_name(name)
        if not res:
            record_dependency_outcome("weather", "failure")
            raise HTTPException(status_code=404, detail="未找到该地区天气，请重试或换个地名")
        record_weather_success_payload(res)
        return {
            "city": res["city"],
            "address": {
                "province": res.get("province", ""),
                "city": res.get("addr_city", ""),
                "district": res.get("district", ""),
                "street": res.get("street", ""),
                "full_address": res.get("full_address", res.get("display_address", "")),
                "display_address": res.get("display_address", ""),
            },
            "latitude": res["latitude"],
            "longitude": res["longitude"],
            "temperature": res["temperature"],
            "weather": res["weather"],
            "weather_code": res["weather_code"],
            "geocode_source": res.get("geocode_source", ""),
            "geocode_error": res.get("geocode_error", ""),
            "weather_source": res.get("weather_source", "open_meteo"),
            "fallback": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        record_weather_exception(e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"weather unavailable: {e}",
        )


@router.post("/upload-reference")
async def post_upload_reference(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传参考衣物图，返回 image_url 供 /generate 使用。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        # Web multipart 可能传 application/octet-stream，按真实字节兜底验证。
        try:
            Image.open(io.BytesIO(raw)).verify()
        except Exception:
            raise HTTPException(status_code=400, detail="请上传图片文件")
    name = (file.filename or "ref.jpg").strip() or "ref.jpg"
    url = await upload_reference_image(str(current_user.user_id), raw, name)
    return {"image_url": url}


@router.post("/generate", response_model=SmartOutfitGenerateResponse)
async def post_generate_smart_outfit(
    body: SmartOutfitGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    智能穿搭生成：参考图 + 城市/天气/气温 + 可选情绪 → 多套衣橱搭配。
    与前端约定：`/api/v1/smart-outfit/generate`。
    """
    try:
        if getattr(settings, "USAGE_QUOTA_ENABLED", False):
            quota = consume_usage(
                db,
                current_user.user_id,
                "smart_outfit_generate",
                units=1,
            )
            if not quota.get("allowed"):
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "message": "smart outfit quota exceeded",
                        "error_code": "QUOTA_SMART_OUTFIT_EXCEEDED",
                        "requires_upgrade": True,
                        "remaining": quota.get("remaining", 0),
                        "limit": quota.get("limit", 0),
                    },
                )

        addr = body.address or {}
        place = (
            addr.get("full_address")
            or addr.get("display_address")
            or body.location
            or body.city
            or ""
        ).strip()
        out = await generate_smart_outfits(
            db=db,
            user_id=str(current_user.user_id),
            image_url=body.image_url,
            city=place,
            weather=body.weather or "晴",
            temperature=float(body.temperature),
            mood=body.mood or "",
            count=min(body.count, 5),
            regeneration_index=body.regeneration_index,
            gender_expression=body.gender_expression,
        )
        return SmartOutfitGenerateResponse(
            **out,
            address={
                "province": out.get("province", addr.get("province", "")),
                "city": out.get("addr_city", out.get("city", addr.get("city", ""))),
                "district": out.get("district", addr.get("district", "")),
                "street": out.get("street", addr.get("street", "")),
                "full_address": out.get("full_address", addr.get("full_address", "")),
                "display_address": out.get("display_address", addr.get("display_address", "")),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        # 勿用 404：易与「路由/Nginx 未反代」混淆。常见原因：更换 UPLOAD_DIR 后未迁移旧 uploads。
        raise HTTPException(
            status_code=400,
            detail=(
                "参考图在服务器上找不到（若刚迁移过上传目录，请把旧 backend/uploads 合并到新 UPLOAD_DIR，"
                "或重新上传参考图后再试）。"
                f" 原始错误: {e}"
            ),
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"generate failed: {e}")


@router.post("/generate-stream")
async def post_generate_smart_outfit_stream(
    body: SmartOutfitGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE 流式智能穿搭：每套搭配就绪后立即推送，前端可逐条渲染。

    事件格式::

        event: outfit
        data: {"index": 0, "outfit": {...}}

        event: done
        data: {"total": 3}
    """
    if getattr(settings, "USAGE_QUOTA_ENABLED", False):
        quota = consume_usage(
            db,
            current_user.user_id,
            "smart_outfit_generate",
            units=1,
        )
        if not quota.get("allowed"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": "smart outfit quota exceeded",
                    "error_code": "QUOTA_SMART_OUTFIT_EXCEEDED",
                    "requires_upgrade": True,
                    "remaining": quota.get("remaining", 0),
                    "limit": quota.get("limit", 0),
                },
            )

    addr = body.address or {}
    place = (
        addr.get("full_address") or addr.get("display_address") or body.location or body.city or ""
    ).strip()

    try:
        result = await generate_smart_outfits(
            db=db,
            user_id=str(current_user.user_id),
            image_url=body.image_url,
            city=place,
            weather=body.weather or "晴",
            temperature=float(body.temperature),
            mood=body.mood or "",
            count=min(body.count, 5),
            regeneration_index=body.regeneration_index,
            gender_expression=body.gender_expression,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=(
                "参考图在服务器上找不到（若刚迁移过上传目录，请把旧 backend/uploads 合并到新 UPLOAD_DIR，"
                "或重新上传参考图后再试）。"
                f" 原始错误: {e}"
            ),
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"generate failed: {e}")

    outfits = result.get("outfits", [])
    meta = {k: v for k, v in result.items() if k != "outfits"}

    async def event_stream():
        for idx, outfit in enumerate(outfits):
            payload = json.dumps(
                {"index": idx, "outfit": outfit, "meta": meta},
                ensure_ascii=False,
            )
            yield f"event: outfit\ndata: {payload}\n\n"
        done_payload = json.dumps({"total": len(outfits)}, ensure_ascii=False)
        yield f"event: done\ndata: {done_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
