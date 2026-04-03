"""Open-Meteo + Nominatim 逆地理与天气（非 IP），供智能穿搭使用。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from app.core.logging import setup_logging

logger = setup_logging()

NOMINATIM_UA = "ClothingAssistant/1.1 (weather; +https://github.com)"


def wmo_to_cn(weather_code: int) -> str:
    """WMO code → 简短中文天气描述。"""
    if weather_code == 0:
        return "晴"
    if weather_code in (1, 2, 3):
        return "多云"
    if weather_code in (45, 48):
        return "雾"
    if weather_code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "雨"
    if weather_code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if weather_code in (95, 96, 99):
        return "雷雨"
    return "阴"


def _full_address_spaced(parts: List[str]) -> str:
    """省 市 区 街道：空格分隔，空段剔除。"""
    return " ".join(p.strip() for p in parts if p and str(p).strip())


def _structured_from_open_meteo(r: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Open-Meteo 单条 result → 省、市、区、街道/路。"""
    province = str(r.get("admin1") or "").strip()
    city = str(r.get("admin2") or "").strip()
    district = str(r.get("admin3") or "").strip()
    street = str(r.get("admin4") or "").strip()
    if not street:
        street = str(r.get("name") or "").strip()
    return province, city, district, street


async def _nominatim_reverse(
    client: httpx.AsyncClient, latitude: float, longitude: float
) -> Optional[Tuple[str, str, str, str, str]]:
    """
    Nominatim 逆地理，补全道路级地址。返回 (province, city, district, street, full_line)。
    """
    url = (
        "https://nominatim.openstreetmap.org/reverse"
        f"?lat={latitude}&lon={longitude}&format=json&accept-language=zh-CN"
    )
    try:
        res = await client.get(url, headers={"User-Agent": NOMINATIM_UA}, timeout=15.0)
        res.raise_for_status()
        data = res.json()
        addr = data.get("address") or {}
        province = str(
            addr.get("state") or addr.get("region") or addr.get("province") or ""
        ).strip()
        city = str(
            addr.get("city")
            or addr.get("town")
            or addr.get("county")
            or addr.get("municipality")
            or ""
        ).strip()
        district = str(
            addr.get("city_district")
            or addr.get("district")
            or addr.get("county")
            or addr.get("suburb")
            or ""
        ).strip()
        if district == city:
            district = str(addr.get("suburb") or addr.get("neighbourhood") or "").strip()
        street = str(
            addr.get("road")
            or addr.get("pedestrian")
            or addr.get("path")
            or addr.get("quarter")
            or ""
        ).strip()
        if not province and not city:
            dl = str(data.get("display_name") or "").strip()
            if dl:
                return ("", "", "", "", dl[:240])
            return None
        line = _full_address_spaced([province, city, district, street])
        return (province, city, district, street, line)
    except Exception as e:
        logger.warning(f"nominatim reverse failed: {e}")
        return None


async def fetch_weather_lat_lon(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    高精度经纬度：Open-Meteo 逆地理 + 必要时 Nominatim 补全；**不在展示字段中出现经纬度数字**。
    """
    async with httpx.AsyncClient(timeout=25.0) as client:
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/reverse"
            f"?latitude={latitude}&longitude={longitude}&language=zh&format=json"
        )
        city_short = "当前位置"
        r0: Dict[str, Any] = {}
        try:
            gr = await client.get(geo_url)
            gr.raise_for_status()
            gj = gr.json()
            results = gj.get("results") or []
            if results:
                r0 = results[0]
                city_short = str(r0.get("name") or city_short).strip() or city_short
        except Exception as e:
            logger.warning(f"open-meteo reverse failed: {e}")

        om_struct = _structured_from_open_meteo(r0) if r0 else ("", "", "", "")
        op, oc, od, os = om_struct
        line_om = _full_address_spaced([op, oc, od, os])
        p, c, d, s = op, oc, od, os
        full_line = line_om
        nom = await _nominatim_reverse(client, latitude, longitude)
        if nom:
            np, nc, nd, ns, nline = nom
            if np or nc or nd or ns:
                merged = _full_address_spaced([np or op, nc or oc, nd or od, ns or os])
                if len(nline) >= len(merged) and len(nline) >= len(line_om):
                    p, c, d, s = np or op, nc or oc, nd or od, ns or os
                    full_line = nline
                else:
                    p, c, d, s = np or op, nc or oc, nd or od, ns or os
                    full_line = merged or nline
            elif nline:
                full_line = nline
        if not full_line.strip():
            full_line = "未能解析详细地址，请点击「手动选择地址」"

        wx_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,weather_code&timezone=auto"
        )
        wr = await client.get(wx_url)
        wr.raise_for_status()
        wj = wr.json()
        cur = wj.get("current") or {}
        temp = float(cur.get("temperature_2m", 20.0))
        code = int(cur.get("weather_code", 0))
        wcn = wmo_to_cn(code)

        return {
            "city": city_short,
            "province": p,
            "addr_city": c,
            "district": d,
            "street": s,
            "full_address": full_line,
            "display_address": full_line,
            "latitude": latitude,
            "longitude": longitude,
            "temperature": temp,
            "weather": wcn,
            "weather_code": code,
        }


async def fetch_weather_by_city_name(name: str) -> Optional[Dict[str, Any]]:
    """按地名搜索，结构与 fetch_weather_lat_lon 一致。"""
    q = name.strip()
    if not q:
        return None
    async with httpx.AsyncClient(timeout=25.0) as client:
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={quote(q)}&count=1&language=zh&format=json"
        )
        try:
            gr = await client.get(geo_url)
            gr.raise_for_status()
            gj = gr.json()
            results = gj.get("results") or []
            if not results:
                return None
            r0 = results[0]
            lat = float(r0["latitude"])
            lon = float(r0["longitude"])
            cname = str(r0.get("name") or q).strip()
            om_struct = _structured_from_open_meteo(r0)
            op, oc, od, os = om_struct
            line_om = _full_address_spaced([op, oc, od, os])
            p, c, d, s = op, oc, od, os
            full_line = line_om or cname
            nom = await _nominatim_reverse(client, lat, lon)
            if nom:
                np, nc, nd, ns, nline = nom
                if np or nc or nd or ns:
                    merged = _full_address_spaced([np or op, nc or oc, nd or od, ns or os])
                    if len(nline) >= len(merged) and len(nline) >= len(line_om):
                        p, c, d, s = np or op, nc or oc, nd or od, ns or os
                        full_line = nline
                    else:
                        p, c, d, s = np or op, nc or oc, nd or od, ns or os
                        full_line = merged or nline
                elif nline:
                    full_line = nline
            if not full_line.strip():
                full_line = cname or "未能解析详细地址，请重新选择"
        except Exception as e:
            logger.warning(f"city geocode failed: {e}")
            return None

        wx_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,weather_code&timezone=auto"
        )
        wr = await client.get(wx_url)
        wr.raise_for_status()
        wj = wr.json()
        cur = wj.get("current") or {}
        temp = float(cur.get("temperature_2m", 20.0))
        code = int(cur.get("weather_code", 0))
        wcn = wmo_to_cn(code)

        return {
            "city": cname,
            "province": p,
            "addr_city": c,
            "district": d,
            "street": s,
            "full_address": full_line,
            "display_address": full_line,
            "latitude": lat,
            "longitude": lon,
            "temperature": temp,
            "weather": wcn,
            "weather_code": code,
        }
